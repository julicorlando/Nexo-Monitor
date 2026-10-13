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
        if kind in ("mikrotik","unifi","hikvision"):
            from integrations import read
            metrics,healthy=read(device)
            if not healthy:raise ValueError("Integration health check failed")
        elif kind=="service":
            import psutil
            name=device.get("service_name","")
            if not name:raise ValueError("Configure service/process name")
            if platform.system()=="Windows":
                if psutil.win_service_get(name).status()!="running":raise ValueError("Service stopped")
            else:
                names=[]
                for process in psutil.process_iter(["name"]):
                    try:names.append(process.info["name"])
                    except (psutil.NoSuchProcess,psutil.AccessDenied):continue
                if name not in names:raise ValueError("Process stopped")
        elif kind=="tcp":
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
        elif kind in ("snmp","snmpwalk"):
            # net-snmp executable; community stored on collector, not in web database.
            host=device["host"];oid=device.get("snmp_oid","")
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.:%_-]*",host) or not re.fullmatch(r"[0-9.]+",oid): raise ValueError("Invalid SNMP target")
            key=device.get("credential_key","")
            if not re.fullmatch(r"[A-Za-z0-9_-]+",key): raise ValueError("Missing SNMP credential key")
            community=os.environ["NEXO_SNMP_"+key.upper().replace("-","_")]
            result=subprocess.run(["snmpwalk" if kind=="snmpwalk" else "snmpget","-v2c","-c",community,"-t","2","-r","0","-Oqv",host,oid],capture_output=True,text=True,timeout=5,check=True)
            metrics={"integration":{"oid":oid,"values":result.stdout.strip().splitlines()[:50]}} if kind=="snmpwalk" else {"snmp_value":result.stdout.strip()[:500]}
        else: raise ValueError("Unsupported check")
        return {"id":device["id"],"success":True,"latency_ms":round((time.monotonic()-start)*1000,2),"metrics":metrics}
    except Exception:
        return {"id":device["id"],"success":False,"latency_ms":None,"metrics":metrics}
def main():
    from spool import Spool
    logging.basicConfig(level=logging.INFO)
    spool=Spool(os.getenv("NEXO_SPOOL_PATH","nexo-spool.sqlite3"))
    while True:
        try:
            devices=api("/api/collector/config/")["devices"]
            spool.cache(devices)
        except Exception as exc:
            logging.warning("Configuração indisponível, usando cache: %s",type(exc).__name__)
            devices=spool.devices()
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor: results=list(executor.map(check,devices))
        for offset in range(0,max(1,len(results)),100):
            evicted=spool.enqueue(results[offset:offset+100])
            if evicted: logging.warning("Fila cheia: %d lotes antigos removidos",evicted)
        try:
            spool.flush(lambda data:api("/api/collector/results/",data))
        except urllib.error.HTTPError as exc:
            # Permanently invalid batches (deleted/disabled devices, expired timestamps) do not block FIFO.
            if exc.code in (400,413):
                spool.db.execute("DELETE FROM batches WHERE id IN (SELECT id FROM batches ORDER BY created LIMIT 1)");spool.db.commit()
                logging.warning("Lote rejeitado descartado: HTTP %s",exc.code)
            else: logging.warning("Central indisponível: HTTP %s",exc.code)
        except Exception as exc: logging.warning("Resultados preservados na fila: %s",type(exc).__name__)
        time.sleep(60)

if __name__=="__main__":
    if not TOKEN: raise RuntimeError("Configure NEXO_TOKEN")
    main()
