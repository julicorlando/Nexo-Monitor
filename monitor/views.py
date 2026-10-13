import hashlib, json, math
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q, Avg, Count
from datetime import timedelta
from django.shortcuts import get_object_or_404
from .models import Site, Notification
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from .models import Collector, Device, CheckResult, Incident
def visible_devices(user):
    qs=Device.objects.select_related("collector__site")
    return qs if user.is_superuser else qs.filter(collector__site__members=user)
@login_required
def dashboard(request):
    qs=visible_devices(request.user)
    if request.GET.get("q"): qs=qs.filter(Q(name__icontains=request.GET["q"])|Q(host__icontains=request.GET["q"]))
    if request.GET.get("site", "").isdigit(): qs=qs.filter(collector__site_id=request.GET["site"])
    devices=list(qs.order_by("name"))
    counts = {x:sum(d.current_status==x for d in devices) for x in ["up", "down", "unknown", "paused"]}
    return render(request,"dashboard.html",{"devices":devices,"counts":counts,"incidents":Incident.objects.filter(resolved_at__isnull=True,device__in=devices).select_related("device")})
@require_GET
def health(request):
    from django.db import connection,DatabaseError
    try:
        with connection.cursor() as cursor:cursor.execute("SELECT 1")
    except DatabaseError:return JsonResponse({"status":"database_unavailable"},status=503)
    return JsonResponse({"status":"ok"})
def authenticated_collector(request):
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "): return None
    return Collector.objects.filter(token_hash=hashlib.sha256(header[7:].encode()).hexdigest(), enabled=True).first()
@require_GET
def collector_config(request):
    collector = authenticated_collector(request)
    if not collector: return JsonResponse({"error":"Unauthorized"},status=401)
    return JsonResponse({"devices":list(Device.objects.filter(collector=collector,enabled=True).values("id","host","port","check_type","http_path","expected_status","snmp_oid","credential_key","cpu_limit","memory_limit","disk_limit","integration_path","service_name"))})
@csrf_exempt
@require_POST
def ingest(request):
    import uuid
    from django.utils.dateparse import parse_datetime
    from .models import IngestBatch
    from .services import reconcile_devices
    collector=authenticated_collector(request)
    if not collector: return JsonResponse({"error":"Unauthorized"},status=401)
    if len(request.body)>262144: return JsonResponse({"error":"Payload too large"},status=413)
    try:
        data=json.loads(request.body)
        if not isinstance(data,dict): raise ValueError()
        results=data["results"]
        batch_id=uuid.UUID(data["batch_id"]) if data.get("batch_id") else None
        now=timezone.now()
        observed=parse_datetime(data["observed_at"]) if data.get("observed_at") else now
        if not observed or timezone.is_naive(observed) or observed>now+timedelta(minutes=2) or observed<now-timedelta(days=7): raise ValueError()
        if not isinstance(results,list) or len(results)>500: raise ValueError()
        ids=set()
        for result in results:
            if not isinstance(result,dict): raise ValueError()
            if type(result["id"]) is not int or type(result["success"]) is not bool or result["id"] in ids: raise ValueError()
            ids.add(result["id"])
            latency=result.get("latency_ms")
            if latency is not None and (type(latency) not in [int,float] or not math.isfinite(latency) or not 0<=latency<=60000): raise ValueError()
            metrics=result.get("metrics",{})
            if not isinstance(metrics,dict) or len(json.dumps(metrics))>16000: raise ValueError()
            allowed={"cpu","memory","disk","snmp_value","integration"}
            if set(metrics)-allowed: raise ValueError()
            for key,value in metrics.items():
                if key=="integration":
                    if not isinstance(value,dict): raise ValueError()
                elif key=="snmp_value":
                    if not isinstance(value,str) or len(value)>500: raise ValueError()
                elif type(value) not in [int,float] or not math.isfinite(value) or not 0<=value<=100: raise ValueError()
        with transaction.atomic():
            collector=Collector.objects.select_for_update().get(pk=collector.pk)
            if batch_id and IngestBatch.objects.filter(collector=collector,batch_id=batch_id).exists():
                collector.last_seen=now;collector.save(update_fields=["last_seen"])
                return JsonResponse({"accepted":0,"duplicate":True})
            devices={d.id:d for d in Device.objects.select_for_update().filter(collector=collector,enabled=True,id__in=ids)}
            if set(devices)!=ids: raise ValueError()
            if batch_id: IngestBatch.objects.create(collector=collector,batch_id=batch_id)
            for result in results:
                device=devices[result["id"]]
                CheckResult.objects.create(device=device,success=result["success"],latency_ms=result.get("latency_ms"),metrics=result.get("metrics",{}),observed_at=observed)
                if device.last_seen and observed<=device.last_seen: continue
                device.consecutive_failures=0 if result["success"] else device.consecutive_failures+1
                device.status="up" if result["success"] else ("down" if device.consecutive_failures>=device.failure_threshold else "unknown")
                device.metrics=result.get("metrics",{});device.last_seen=observed;device.latency_ms=result.get("latency_ms")
                device.save(update_fields=["status","last_seen","latency_ms","metrics","consecutive_failures"])
            collector.last_seen=now
            collector.save(update_fields=["last_seen"])
            reconcile_devices(collector,now)
    except (ValueError,KeyError,TypeError,AttributeError): return JsonResponse({"error":"Invalid results"},status=400)
    return JsonResponse({"accepted":len(results)})

@login_required
@require_GET
def history(request, device_id):
    device=get_object_or_404(visible_devices(request.user),pk=device_id)
    results=device.checkresult_set.filter(observed_at__gte=timezone.now()-timedelta(hours=24)).order_by("-observed_at")[:1000]
    stats=device.checkresult_set.filter(observed_at__gte=timezone.now()-timedelta(hours=24)).aggregate(total=Count("id"),latency=Avg("latency_ms"))
    total=stats["total"]
    good=device.checkresult_set.filter(observed_at__gte=timezone.now()-timedelta(hours=24),success=True).count()
    ordered=list(reversed(results))
    points=" ".join(f"{index*800/max(1,len(ordered)-1):.1f},{150-min(150,(r.latency_ms or 0)/1000*150):.1f}" for index,r in enumerate(ordered))
    return render(request,"history.html",{"points":points,"device":device,"results":results,"availability":round(good/total*100,2) if total else None,"average":stats["latency"]})

@login_required
@permission_required("monitor.add_device",raise_exception=True)
def import_inventory(request,collector_id):
    from .forms import InventoryImport
    collectors=Collector.objects.all() if request.user.is_superuser else Collector.objects.filter(site__members=request.user)
    collector=get_object_or_404(collectors,pk=collector_id)
    form=InventoryImport(request.POST or None,request.FILES or None)
    count=None
    if request.method=="POST" and form.is_valid():
        with transaction.atomic():
            for device in form.devices:
                device.collector=collector
                device.save()
        from .models import AuditEvent
        AuditEvent.objects.create(actor=request.user,site=collector.site,action="inventory.import",object_label=str(len(form.devices))+" devices")
        count=len(form.devices)
    return render(request,"import.html",{"form":form,"collector":collector,"count":count})

@login_required
def inventory(request):
    return render(request,"inventory.html",{"devices":visible_devices(request.user).order_by("name")})
@login_required
def device_edit(request,device_id=None):
    from .forms import DeviceForm
    from .models import AuditEvent
    from django.shortcuts import redirect
    permission="monitor.change_device" if device_id else "monitor.add_device"
    if not request.user.has_perm(permission):return JsonResponse({"error":"Forbidden"},status=403)
    device=get_object_or_404(visible_devices(request.user),pk=device_id) if device_id else None
    form=DeviceForm(request.POST or None,instance=device,user=request.user)
    if request.method=="POST" and form.is_valid():
        with transaction.atomic():
            obj=form.save()
            AuditEvent.objects.create(actor=request.user,site=obj.collector.site,action="device.update" if device else "device.create",object_label=obj.name)
        return redirect("/inventory/")
    return render(request,"device_form.html",{"form":form})
@login_required
def units(request):
    sites=Site.objects.all() if request.user.is_superuser else Site.objects.filter(members=request.user)
    collectors=Collector.objects.filter(site__in=sites).select_related("site")
    return render(request,"units.html",{"sites":sites,"collectors":collectors})
@login_required
def audit(request):
    from .models import AuditEvent
    events=AuditEvent.objects.select_related("actor","site")
    if not request.user.is_superuser:events=events.filter(Q(site__members=request.user)|Q(actor=request.user))
    return render(request,"audit.html",{"events":events.distinct().order_by("-created_at")[:500]})
@login_required
def security(request):
    import pyotp,time
    from .models import MFAProfile,AuditEvent
    from .security import protect,verify
    profile=MFAProfile.objects.filter(user=request.user).first()
    message=""
    if not profile and not request.session.get("pending_mfa"):request.session["pending_mfa"]=pyotp.random_base32()
    if request.method=="POST":
        password=request.POST.get("password","");code=request.POST.get("code","")
        if not request.user.check_password(password):message="Senha incorreta."
        elif profile and request.POST.get("action")=="disable":
            if verify(request.user,code):
                profile.delete();profile=None;request.session.pop("mfa_version",None)
                AuditEvent.objects.create(actor=request.user,action="mfa.disable",object_label=request.user.username)
                message="Autenticador desativado."
            else:message="Código inválido."
        elif not profile:
            secret=request.session.get("pending_mfa")
            if secret and pyotp.TOTP(secret).verify(code):
                profile=MFAProfile.objects.create(user=request.user,encrypted_secret=protect(secret),last_counter=int(time.time())//30)
                request.session["mfa_version"]=profile.encrypted_secret;request.session.pop("pending_mfa",None)
                AuditEvent.objects.create(actor=request.user,action="mfa.enable",object_label=request.user.username)
                message="Autenticador ativado."
            else:message="Código inválido."
    secret=request.session.get("pending_mfa","") if not profile else ""
    return render(request,"security.html",{"enabled":bool(profile),"secret":secret,"message":message})

@login_required
def whatsapp_settings(request):
    from .models import WhatsAppSettings,AuditEvent
    from .forms import WhatsAppForm
    from .whatsapp import gateway,start_session,session_status,GatewayError
    if not request.user.is_superuser:return JsonResponse({"error":"Forbidden"},status=403)
    config,_=WhatsAppSettings.objects.get_or_create(pk=1)
    message="";state="UNKNOWN"
    form=WhatsAppForm(instance=config)
    if request.method=="POST":
        action=request.POST.get("action","save")
        try:
            if action=="save":
                form=WhatsAppForm(request.POST,instance=config)
                if form.is_valid():
                    with transaction.atomic():
                        locked=WhatsAppSettings.objects.select_for_update().get(pk=1)
                        changed=locked.recipient!=form.cleaned_data["recipient"] or (not locked.enabled and form.cleaned_data["enabled"])
                        locked.recipient=form.cleaned_data["recipient"];locked.enabled=form.cleaned_data["enabled"];locked.include_recovery=form.cleaned_data["include_recovery"]
                        if changed:locked.activated_at=timezone.now()
                        locked.full_clean();locked.save()
                        AuditEvent.objects.create(actor=request.user,action="whatsapp.configure",object_label="Global recipient ***"+locked.recipient[-4:])
                    message="Configuração salva. Os envios usam somente este número."
            elif action=="test":
                config=WhatsAppSettings.objects.get(pk=1)
                site=Site.objects.order_by("id").first()
                if not config.enabled or not config.recipient:message="Ative o canal e salve o destinatário antes do teste."
                elif not site:message="Cadastre uma unidade antes do teste."
                elif Notification.objects.filter(event_kind="test",created_at__gte=timezone.now()-timedelta(minutes=1)).exists():message="Teste já agendado. Aguarde um minuto."
                else:
                    Notification.objects.create(site=site,event_kind="test",subject="Teste de alerta",body="O canal de alertas está configurado para este número.")
                    AuditEvent.objects.create(actor=request.user,action="whatsapp.test",object_label="registered recipient")
                    message="Teste agendado somente para o destinatário cadastrado."
            elif action=="retry":
                config=WhatsAppSettings.objects.get(pk=1)
                item=Notification.objects.filter(pk=int(request.POST.get("notification_id")) if request.POST.get("notification_id","").isdigit() else 0,whatsapp_sent_at__isnull=True,created_at__gte=config.activated_at,whatsapp_recipient=config.recipient).first()
                if item and config.enabled:
                    item.whatsapp_attempts=0;item.whatsapp_next_attempt=None;item.whatsapp_last_error="";item.save(update_fields=["whatsapp_attempts","whatsapp_next_attempt","whatsapp_last_error"])
                    AuditEvent.objects.create(actor=request.user,action="whatsapp.retry",object_label=str(item.pk))
                    message="Nova tentativa agendada para o mesmo número."
                else:message="Evento não elegível para nova tentativa."
            elif action=="connect":
                start_session();message="Conexão iniciada. Aguarde o QR code."
                AuditEvent.objects.create(actor=request.user,action="whatsapp.connect",object_label="default")
            elif action=="stop":
                gateway("/api/sessions/default/stop","POST",{});message="Sessão pausada."
                AuditEvent.objects.create(actor=request.user,action="whatsapp.stop",object_label="default")
        except GatewayError as exc:message="Não foi possível acessar o WhatsApp: "+str(exc)
    try:state=session_status()
    except GatewayError as exc:state=str(exc)
    logs=Notification.objects.exclude(whatsapp_attempts=0).order_by("-id")[:30]
    response=render(request,"whatsapp.html",{"form":form,"message":message,"state":state,"logs":logs})
    response["Cache-Control"]="no-store"
    return response
@login_required
@require_GET
def whatsapp_qr(request):
    from django.http import HttpResponse
    from .whatsapp import gateway,GatewayError
    if not request.user.is_superuser:return JsonResponse({"error":"Forbidden"},status=403)
    try:data=gateway("/api/default/auth/qr",image=True)
    except GatewayError:return JsonResponse({"error":"QR indisponível. Inicie a conexão ou aguarde nova tentativa."},status=503)
    response=HttpResponse(data,content_type="image/png");response["Cache-Control"]="no-store";return response
@login_required
@require_GET
def whatsapp_status(request):
    from .whatsapp import session_status,GatewayError
    if not request.user.is_superuser:return JsonResponse({"error":"Forbidden"},status=403)
    try:state=session_status()
    except GatewayError as exc:state=str(exc)
    response=JsonResponse({"state":state});response["Cache-Control"]="no-store";return response

@login_required
def infrastructure_edit(request,kind,object_id=None):
    from .forms import SiteForm,CollectorForm,EmailRecipientForm
    from .models import AlertRecipient,AuditEvent
    if not request.user.is_superuser:return JsonResponse({"error":"Forbidden"},status=403)
    models={"site":(Site,SiteForm),"collector":(Collector,CollectorForm),"email":(AlertRecipient,EmailRecipientForm)}
    if kind not in models:return JsonResponse({"error":"Not found"},status=404)
    model,form_class=models[kind]
    instance=get_object_or_404(model,pk=object_id) if object_id else None
    form=form_class(request.POST or None,instance=instance)
    token=None;message=""
    if request.method=="POST" and form.is_valid():
        with transaction.atomic():
            obj=form.save()
            if kind=="collector" and (not instance or request.POST.get("rotate_token")=="yes"):token=obj.issue_token()
            site=obj if kind=="site" else obj.site
            AuditEvent.objects.create(actor=request.user,site=site,action=kind+".update" if instance else kind+".create",object_label=str(obj.pk))
            if token:AuditEvent.objects.create(actor=request.user,site=site,action="collector.token.rotate",object_label=str(obj.pk))
        message="Configuração salva."
    response=render(request,"infrastructure_form.html",{"form":form,"kind":kind,"token":token,"message":message})
    response["Cache-Control"]="no-store";return response
@login_required
def notifications(request):
    from .models import AlertRecipient
    sites=Site.objects.all() if request.user.is_superuser else Site.objects.filter(members=request.user)
    return render(request,"notifications.html",{"events":Notification.objects.filter(site__in=sites).order_by("-id")[:200],"recipients":AlertRecipient.objects.filter(site__in=sites)})
