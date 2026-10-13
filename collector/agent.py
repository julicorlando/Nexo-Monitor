"""Coletor TCP: conexão de saída HTTPS, sem portas abertas para receber comandos."""
import concurrent.futures, json, logging, os, socket, time, urllib.request
BASE=os.environ["NEXO_URL"].rstrip("/")
TOKEN=os.environ["NEXO_TOKEN"]
if not BASE.startswith("https://"): raise RuntimeError("NEXO_URL deve usar HTTPS")
def api(path, data=None):
    body=json.dumps(data).encode() if data is not None else None
    request=urllib.request.Request(BASE+path,data=body,headers={"Authorization":"Bearer "+TOKEN,"Content-Type":"application/json"})
    with urllib.request.urlopen(request,timeout=20) as response: return json.load(response)
def check(device):
    start=time.monotonic()
    try:
        with socket.create_connection((device["host"],device["port"]),timeout=3): pass
        return {"id":device["id"],"success":True,"latency_ms":round((time.monotonic()-start)*1000,2)}
    except OSError: return {"id":device["id"],"success":False,"latency_ms":None}
logging.basicConfig(level=logging.INFO)
while True:
    try:
        devices=api("/api/collector/config/")["devices"]
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor: results=list(executor.map(check,devices))
        for offset in range(0,len(results),500): api("/api/collector/results/",{"results":results[offset:offset+500]})
        logging.info("Verificados %d dispositivos",len(results))
    except Exception as exc: logging.warning("Falha na coleta: %s",type(exc).__name__)
    time.sleep(60)
