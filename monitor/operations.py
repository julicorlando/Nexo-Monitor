from django.utils import timezone
from .models import AuditEvent

def config_snapshot(obj):
    fields={"monitor.Device":["name","category","collector_id","host","port","check_type","enabled","parent_id","failure_threshold","recovery_threshold","cpu_limit","memory_limit","disk_limit","maintenance_until","archived_at","model","serial_number","location","notes","http_path","expected_status","snmp_oid","integration_path","service_name","credential_key"],"monitor.Collector":["name","site_id","enabled","offline_after"],"monitor.Site":["name","address","latitude","longitude"],"monitor.AlertRecipient":["site_id","email","enabled"]}
    result={}
    for key in fields.get(obj._meta.label,[]):
        value=getattr(obj,key)
        result[key]=value.isoformat() if hasattr(value,"isoformat") else value
    if obj._meta.label=="monitor.Site" and obj.pk:result["members"]=list(obj.members.order_by("pk").values_list("pk",flat=True))
    return result

def record_change(user,obj,before,action,site=None):
    after=config_snapshot(obj)
    changes={key:{"before":before.get(key),"after":value} for key,value in after.items() if before.get(key)!=value}
    AuditEvent.objects.create(actor=user,site=site,action=action,object_label=f"{obj._meta.label}:{obj.pk}",changes=changes)

def alert_decision(device,now=None):
    now=now or timezone.now()
    if device.archived_at:return "Arquivado: não coleta e não alerta."
    if not device.enabled:return "Pausado: não coleta e não alerta."
    if device.maintenance_until and device.maintenance_until>now:return "Silenciado por manutenção."
    if device.parent_id and device.parent.current_status!="up":return "Silenciado pela dependência sem disponibilidade confirmada."
    if not device.last_seen:return "Aguardando primeira coleta."
    if (now-device.last_seen).total_seconds()>device.collector.offline_after:return "Sem coleta recente: verificar coletor e atraso de resultados."
    if device.status=="down":return "Falha confirmada: incidente aberto; recuperação exige sucessos consecutivos."
    if device.consecutive_failures:return f"Confirmando falha: {device.consecutive_failures}/{device.failure_threshold}."
    return f"Teste disponível. Alerta após {device.failure_threshold} falhas; recuperação após {device.recovery_threshold} sucessos."


def touch_worker():
    import os
    from .models import WorkerState
    if os.getenv("NEXO_WORKER_ACTIVE")=="1":
        WorkerState.objects.update_or_create(name="main",defaults={"last_seen":timezone.now(),"last_error":""})
