"""Read-only adapters. TLS verification mandatory; credentials exist only on collector."""
import os,re,requests
from requests.auth import HTTPDigestAuth
from defusedxml import ElementTree

def prefix(device):
    key=device.get("credential_key","")
    if not re.fullmatch(r"[A-Za-z0-9_-]+",key):raise ValueError("Configure credential key")
    return "NEXO_"+key.upper().replace("-","_")
def fetch(device,path,digest=False,api_key=False):
    host=device["host"]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.:-]*",host):raise ValueError("Invalid host")
    if not path.startswith("/") or path.startswith("//"):raise ValueError("Invalid path")
    key=prefix(device);headers={}
    auth=None
    if api_key:headers["X-API-Key"]=os.environ[key+"_API_KEY"]
    else:
        credentials=(os.environ[key+"_USER"],os.environ[key+"_PASSWORD"])
        auth=HTTPDigestAuth(*credentials) if digest else credentials
    with requests.get("https://"+host+":"+str(device["port"])+path,auth=auth,headers=headers,verify=os.getenv(key+"_CA") or True,timeout=(3,8),allow_redirects=False,stream=True) as response:
        if response.status_code!=200:raise ValueError("Integration HTTP status")
        content=bytearray()
        for chunk in response.iter_content(8192):
            content.extend(chunk)
            if len(content)>1024*1024:raise ValueError("Integration response too large")
        return bytes(content)
def read(device):
    import json
    kind=device["check_type"]
    if kind=="mikrotik":
        resources=json.loads(fetch(device,"/rest/system/resource"))
        if isinstance(resources,list):resources=resources[0]
        cpu=float(resources["cpu-load"])
        total=float(resources["total-memory"]);free=float(resources["free-memory"])
        memory=round((total-free)/total*100,2)
        interfaces=json.loads(fetch(device,"/rest/interface"))
        data={"board":str(resources.get("board-name",""))[:100],"uptime":str(resources.get("uptime",""))[:100],"interfaces":[{"name":str(i.get("name",""))[:100],"running":i.get("running"),"rx_bytes":i.get("rx-byte"),"tx_bytes":i.get("tx-byte")} for i in interfaces[:50]]}
        return {"cpu":cpu,"memory":memory,"integration":data},cpu<device.get("cpu_limit",90) and memory<device.get("memory_limit",90)
    if kind=="unifi":
        # Endpoint is explicitly configured for the installed controller/API version.
        path=device.get("integration_path")
        if not path:raise ValueError("Configure UniFi read-only API endpoint")
        data=json.loads(fetch(device,path,api_key=True))
        devices=data.get("data")
        if not isinstance(devices,list):raise ValueError("Unsupported UniFi response")
        states=[{"name":str(i.get("name",""))[:100],"id":str(i.get("id",""))[:100],"state":str(i.get("state","UNKNOWN"))[:50],"ip":str(i.get("ipAddress",""))[:100]} for i in devices[:50]]
        return {"integration":{"devices":states,"count":len(devices),"scope":"API page only"}},all(i["state"]=="ONLINE" for i in states) and bool(states)
    if kind=="hikvision":
        path=device.get("integration_path") or "/ISAPI/ContentMgmt/Storage"
        root=ElementTree.fromstring(fetch(device,path,digest=True))
        disks=[]
        for node in root.iter():
            if node.tag.rsplit("}",1)[-1] in ("hdd","HDD"):
                item={child.tag.rsplit("}",1)[-1]:(child.text or "")[:100] for child in node}
                disks.append({k:v for k,v in item.items() if k in ["id","hddName","status","capacity","freeSpace"]})
        if not disks:raise ValueError("No supported HDD status in response")
        return {"integration":{"disks":disks[:16],"recording_verified":False}},all(d.get("status","").lower() in ("ok","normal") for d in disks)
    raise ValueError("Unsupported integration")
