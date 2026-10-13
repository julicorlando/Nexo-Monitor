from django.db import transaction
from django.utils import timezone
from .models import Device,Incident,Notification,Collector

def reconcile_devices(collector, now):
    devices=list(Device.objects.select_related("parent").filter(collector=collector))
    for device in devices:
        if not device.last_seen or (now-device.last_seen).total_seconds()>collector.offline_after: continue
        maintenance=device.maintenance_until and device.maintenance_until>now
        parent_failed=device.parent and device.parent.current_status!="up"
        suppressed=maintenance or parent_failed
        opened=Incident.objects.filter(device=device,resolved_at__isnull=True)
        if device.status=="up" or not device.enabled or suppressed:
            changed=opened.update(resolved_at=now)
            if changed and not suppressed:
                Notification.objects.create(site=collector.site,device=device,event_kind="recovery",subject="Recuperado: "+device.name,body="Equipamento voltou a responder.")
        elif device.status=="down":
            incident,created=Incident.objects.get_or_create(device=device,resolved_at__isnull=True)
            if created:
                Notification.objects.create(site=collector.site,device=device,event_kind="offline",subject="Falha: "+device.name,body="Equipamento: "+device.name+" • Endereço: "+device.host+":"+str(device.port)+" • Verificação: "+device.check_type)

def inspect_collectors():
    now=timezone.now()
    for identifier in Collector.objects.filter(enabled=True).values_list("pk",flat=True):
        with transaction.atomic():
            collector=Collector.objects.select_for_update().get(pk=identifier)
            # Newly registered collectors alert only after their first contact.
            if not collector.last_seen: continue
            offline=(now-collector.last_seen).total_seconds()>collector.offline_after
            if offline!=collector.offline:
                collector.offline=offline;collector.save(update_fields=["offline"])
                Notification.objects.create(site=collector.site,collector=collector,event_kind="collector_offline" if offline else "collector_recovery",subject=("Coletor desconectado: " if offline else "Coletor recuperado: ")+collector.name,body="Verifique o link da unidade e o serviço coletor.")
            if not offline: reconcile_devices(collector,now)
