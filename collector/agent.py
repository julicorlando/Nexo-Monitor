"""Coletor TCP: conexão de saída HTTPS, sem portas abertas para receber comandos."""
import concurrent.futures, json, logging, os, socket, time, urllib.request, urllib.error, subprocess, platform, re
BASE=os.getenv("NEXO_URL", "https://localhost").rstrip("/")
TOKEN=os.getenv("NEXO_TOKEN", "")
if not BASE.startswith("https://"): raise RuntimeError("NEXO_URL deve usar HTTPS")
def api(path, data=None):
    body=json.dumps(data).encode() if data is not None else None
    request=urllib.request.Request(BASE+path,data=body,headers={"Authorization":"Bearer "+TOKEN,"Content-Type":"application/json"})
    with urllib.request.urlopen(request,timeout=20) as response: return json.load(response)
def check(device):
    start=time.monotonic()
    metrics={}
    try:
        kind=device.get("check_type","tcp")
        if kind=="tcp":
            with socket.create_connection((device["host"],device["port"]),timeout=3): pass
        elif kind=="http":
            # HTTPS only, no redirects or credentials received from central.
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self,*args): return None
            host=device["host"]
            if any(c in host for c in "/@?#\\"): raise ValueError("Invalid host")
            path=device.get("http_path","/")
            if not path.startswith("/") or path.startswith("//"): raise ValueError("Invalid path")
            try:
                with urllib.request.build_opener(NoRedirect).open("https://"+host+":"+str(device["port"])+path,timeout=5) as response: status=response.status
            except urllib.error.HTTPError as exc: status=exc.code
            if status!=device.get("expected_status",200): raise ValueError("Unexpected HTTP status")
        elif kind=="ping":
            host=device["host"]
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.:%_-]*",host): raise ValueError("Invalid host")
            flags=["-n","1","-w","3000"] if platform.system()=="Windows" else ["-c","1","-W","3"]
            subprocess.run(["ping",*flags,host],check=True,timeout=5,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        elif kind=="system":
            # Metrics belong to this collector machine, never to the configured remote host.
            import psutil
            metrics={"cpu":psutil.cpu_percent(interval=1),"memory":psutil.virtual_memory().percent,"disk":psutil.disk_usage(os.getenv("NEXO_DISK_PATH","/")).percent}
            if any(value>=device.get(key+"_limit",90) for key,value in metrics.items()): raise ValueError("Resource threshold exceeded")
        elif kind=="snmp":
            # net-snmp executable; community stored on collector, not in web database.
            host=device["host"];oid=device.get("snmp_oid","")
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.:%_-]*",host) or not re.fullmatch(r"[0-9.]+",oid): raise ValueError("Invalid SNMP target")
            key=device.get("credential_key","")
            if not re.fullmatch(r"[A-Za-z0-9_-]+",key): raise ValueError("Missing SNMP credential key")
            community=os.environ["NEXO_SNMP_"+key.upper().replace("-","_")]
            result=subprocess.run(["snmpget","-v2c","-c",community,"-t","2","-r","0","-Oqv",host,oid],capture_output=True,text=True,timeout=5,check=True)
            metrics={"snmp_value":result.stdout.strip()[:500]}
        else: raise ValueError("Unsupported check")
        return {"id":device["id"],"success":True,"latency_ms":round((time.monotonic()-start)*1000,2),"metrics":metrics}
    except Exception:
        return {"id":device["id"],"success":False,"latency_ms":None,"metrics":metrics}
def main():
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            devices=api("/api/collector/config/")["devices"]
            if not devices: api("/api/collector/results/",{"results":[]})
            with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor: results=list(executor.map(check,devices))
            for offset in range(0,len(results),500): api("/api/collector/results/",{"results":results[offset:offset+500]})
            logging.info("Verificados %d dispositivos",len(results))
        except Exception as exc: logging.warning("Falha na coleta: %s",type(exc).__name__)
        time.sleep(60)

if __name__=="__main__":
    if not TOKEN: raise RuntimeError("Configure NEXO_TOKEN")
    main()
