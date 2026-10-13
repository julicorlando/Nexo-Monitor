import os,time,logging
os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings")
import django
django.setup()
os.environ["NEXO_WORKER_ACTIVE"]="1"
from django.core.management import call_command
logging.basicConfig(level=logging.INFO)
last_cleanup=0
while True:
    try:
        from monitor.models import WorkerState
        from django.utils import timezone
        WorkerState.objects.update_or_create(name="main",defaults={"last_seen":timezone.now(),"last_error":""})
        from monitor.services import inspect_collectors
        inspect_collectors()
        call_command("send_notifications")
        from monitor.whatsapp import dispatch
        dispatch()
        if time.monotonic()-last_cleanup>86400:
            call_command("prune_results")
            last_cleanup=time.monotonic()
    except Exception as exc:
        logging.warning("Worker error: %s",type(exc).__name__)
        try:WorkerState.objects.update_or_create(name="main",defaults={"last_seen":timezone.now(),"last_error":type(exc).__name__})
        except Exception:pass
    time.sleep(60)
