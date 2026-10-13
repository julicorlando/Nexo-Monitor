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
def health(request): return JsonResponse({"status":"ok"})
def authenticated_collector(request):
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "): return None
    return Collector.objects.filter(token_hash=hashlib.sha256(header[7:].encode()).hexdigest(), enabled=True).first()
@require_GET
def collector_config(request):
    collector = authenticated_collector(request)
    if not collector: return JsonResponse({"error":"Unauthorized"},status=401)
    return JsonResponse({"devices":list(Device.objects.filter(collector=collector,enabled=True).values("id","host","port","check_type","http_path","expected_status","snmp_oid","credential_key","cpu_limit","memory_limit","disk_limit"))})
@csrf_exempt
@require_POST
def ingest(request):
    collector = authenticated_collector(request)
    if not collector: return JsonResponse({"error":"Unauthorized"},status=401)
    if len(request.body)>65536: return JsonResponse({"error":"Payload too large"},status=413)
    try:
        data=json.loads(request.body)
        results=data["results"]
        if not isinstance(results,list) or len(results)>500: raise ValueError()
        ids=set()
        if not isinstance(data,dict): raise ValueError()
        for result in results:
            if not isinstance(result,dict): raise ValueError()
            metrics=result.get("metrics",{})
            if not isinstance(metrics,dict) or set(metrics)-{"cpu","memory","disk","snmp_value"}: raise ValueError()
            for key,value in metrics.items():
                if key=="snmp_value":
                    if not isinstance(value,str) or len(value)>500: raise ValueError()
                elif type(value) not in [int,float] or not math.isfinite(value) or not 0<=value<=100: raise ValueError()
            if type(result["id"]) is not int or type(result["success"]) is not bool or result["id"] in ids: raise ValueError()
            ids.add(result["id"])
            latency=result.get("latency_ms")
            if latency is not None and (type(latency) not in [int,float] or not math.isfinite(latency) or not 0<=latency<=60000): raise ValueError()
        with transaction.atomic():
            devices={d.id:d for d in Device.objects.select_for_update().filter(collector=collector,enabled=True,id__in=ids)}
            if set(devices)!=ids: raise ValueError()
            now=timezone.now()
            for result in results:
                device=devices[result["id"]]
                device.consecutive_failures=0 if result["success"] else device.consecutive_failures+1
                device.status="up" if result["success"] else ("down" if device.consecutive_failures>=device.failure_threshold else "unknown")
                device.metrics=result.get("metrics",{})
                device.last_seen=now
                device.latency_ms=result.get("latency_ms")
                device.save(update_fields=["status","last_seen","latency_ms","metrics","consecutive_failures"])
                CheckResult.objects.create(device=device,success=result["success"],latency_ms=device.latency_ms,metrics=device.metrics)
                if result["success"]:
                    changed=Incident.objects.filter(device=device,resolved_at__isnull=True).update(resolved_at=now)
                    if changed: Notification.objects.create(site=collector.site,subject="Recuperado: "+device.name,body="O equipamento voltou a responder.")
                elif device.status=="down":
                    incident,created=Incident.objects.get_or_create(device=device,resolved_at__isnull=True)
                    if created: Notification.objects.create(site=collector.site,subject="Falha: "+device.name,body="Falha no teste "+device.check_type+". Unidade: "+str(collector.site))
            Collector.objects.filter(pk=collector.pk).update(last_seen=now)
    except (ValueError,KeyError,TypeError,AttributeError): return JsonResponse({"error":"Invalid results"},status=400)
    return JsonResponse({"accepted":len(results)})

@login_required
@require_GET
def history(request, device_id):
    device=get_object_or_404(visible_devices(request.user),pk=device_id)
    results=device.checkresult_set.filter(created_at__gte=timezone.now()-timedelta(hours=24)).order_by("-created_at")[:1000]
    stats=device.checkresult_set.filter(created_at__gte=timezone.now()-timedelta(hours=24)).aggregate(total=Count("id"),latency=Avg("latency_ms"))
    total=stats["total"]
    good=device.checkresult_set.filter(created_at__gte=timezone.now()-timedelta(hours=24),success=True).count()
    return render(request,"history.html",{"device":device,"results":results,"availability":round(good/total*100,2) if total else None,"average":stats["latency"]})

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
        count=len(form.devices)
    return render(request,"import.html",{"form":form,"collector":collector,"count":count})
