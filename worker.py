import os,time,logging
os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings")
import django
django.setup()
from django.core.management import call_command
logging.basicConfig(level=logging.INFO)
last_cleanup=0
while True:
    try:
        from monitor.services import inspect_collectors
        inspect_collectors()
        call_command("send_notifications")
        from monitor.whatsapp import dispatch
        dispatch()
        if time.monotonic()-last_cleanup>86400:
            call_command("prune_results")
            last_cleanup=time.monotonic()
    except Exception as exc: logging.warning("Worker error: %s",type(exc).__name__)
    time.sleep(60)
