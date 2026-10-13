"""WAHA gateway: private transport, one server-controlled destination."""
import json,re,urllib.request,urllib.error
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from .models import WhatsAppSettings,Notification
class GatewayError(Exception):pass

def gateway(path,method="GET",payload=None,image=False):
    if not settings.WAHA_API_KEY:raise GatewayError("gateway_not_configured")
    headers={"X-Api-Key":settings.WAHA_API_KEY,"Accept":"image/png" if image else "application/json"}
    if payload is not None:headers["Content-Type"]="application/json"
    request=urllib.request.Request(settings.WAHA_URL.rstrip("/")+path,data=json.dumps(payload).encode() if payload is not None else None,headers=headers,method=method)
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args):return None
    try:
        with urllib.request.build_opener(NoRedirect).open(request,timeout=15) as response:
            raw=response.read(1024*1024+1)
            if len(raw)>1024*1024:raise GatewayError("gateway_response_too_large")
            if image:
                if not raw.startswith(b"\x89PNG\r\n\x1a\n"):raise GatewayError("invalid_qr_image")
                return raw
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:raise GatewayError("gateway_http_"+str(exc.code)) from None
    except (OSError,ValueError):raise GatewayError("gateway_unavailable") from None

def session_status():
    data=gateway("/api/sessions/default")
    if not isinstance(data,dict):raise GatewayError("invalid_session_response")
    return str(data.get("status","UNKNOWN"))[:50]
def start_session():
    try:state=session_status()
    except GatewayError as exc:
        if str(exc)!="gateway_http_404":raise
        return gateway("/api/sessions","POST",{"name":"default","start":True,"config":{"webhooks":[]}})
    if state=="STOPPED":return gateway("/api/sessions/default/start","POST",{})
    if state=="FAILED":return gateway("/api/sessions/default/restart","POST",{})
    return {"status":state}
def deliver(item_id):
    # Keep the singleton config locked while dispatching so changes cannot race with destination validation.
    with transaction.atomic():
        config=WhatsAppSettings.objects.select_for_update().filter(pk=1).first()
        if not config or not config.enabled:return False
        config.full_clean()
        item=Notification.objects.select_for_update().get(pk=item_id)
        now=timezone.now()
        kinds=["offline","collector_offline","test"]
        if config.include_recovery:kinds+=["recovery","collector_recovery"]
        if item.event_kind not in kinds or item.created_at<config.activated_at or item.whatsapp_sent_at or item.whatsapp_attempts>=6:return False
        if item.whatsapp_next_attempt and item.whatsapp_next_attempt>now:return False
        if item.whatsapp_recipient and item.whatsapp_recipient!=config.recipient:
            item.whatsapp_last_error="recipient_changed";item.save(update_fields=["whatsapp_last_error"]);return False
        resolved=False
        if item.event_kind=="offline" and item.device_id:
            device=item.device
            resolved=device.status=="up" or not device.enabled or (device.maintenance_until and device.maintenance_until>now) or (device.parent_id and device.parent.current_status!="up")
        if item.event_kind=="collector_offline" and item.collector_id:
            resolved=not item.collector.enabled or (item.collector.last_seen and (now-item.collector.last_seen).total_seconds()<=item.collector.offline_after)
        if resolved:
            item.whatsapp_last_error="event_resolved";item.save(update_fields=["whatsapp_last_error"]);return False
        item.whatsapp_recipient=config.recipient
        item.whatsapp_attempts+=1
        try:
            if session_status()!="WORKING":raise GatewayError("session_not_connected")
            # No chat ID, destination, phone or content is accepted from the browser.
            text="Nexo Monitor\n"+item.subject+"\nUnidade: "+str(item.site)+"\n"+item.body+"\nEvento: "+timezone.localtime(item.created_at).strftime("%d/%m/%Y %H:%M")+"\nID: "+str(item.pk)
            response=gateway("/api/sendText","POST",{"session":"default","chatId":config.recipient+"@c.us","text":text[:3500]})
            if not isinstance(response,dict) or not response.get("id"):raise GatewayError("send_not_confirmed")
            provider_id=response["id"]
            item.whatsapp_provider_id=(provider_id if isinstance(provider_id,str) else json.dumps(provider_id))[:200]
            item.whatsapp_sent_at=now;item.whatsapp_last_error="";item.whatsapp_next_attempt=None
        except GatewayError as exc:
            item.whatsapp_last_error=str(exc)
            item.whatsapp_next_attempt=now+timedelta(seconds=min(3600,60*2**(item.whatsapp_attempts-1)))
        item.save(update_fields=["whatsapp_recipient","whatsapp_attempts","whatsapp_sent_at","whatsapp_provider_id","whatsapp_last_error","whatsapp_next_attempt"])
        return bool(item.whatsapp_sent_at)

def dispatch():
    config=WhatsAppSettings.objects.filter(pk=1,enabled=True).first()
    if not config:return
    # Limit old queued notifications; do not burst-send historic incidents when enabling.
    from django.db.models import Q
    kinds=["offline","collector_offline","test"]
    if config.include_recovery:kinds.extend(["recovery","collector_recovery"])
    pending=Notification.objects.filter(created_at__gte=config.activated_at,whatsapp_sent_at__isnull=True,whatsapp_attempts__lt=6,event_kind__in=kinds).filter(Q(whatsapp_next_attempt__isnull=True)|Q(whatsapp_next_attempt__lte=timezone.now())).exclude(whatsapp_last_error__in=["recipient_changed","event_resolved"])
    for identifier in pending.order_by("id").values_list("id",flat=True)[:100]:
        deliver(identifier)
