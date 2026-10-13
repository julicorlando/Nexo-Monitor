import hashlib, json, math
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from .models import Collector, Device, CheckResult, Incident
@login_required
def dashboard(request):
    devices = list(Device.objects.select_related("collector__site").order_by("name"))
    counts = {x:sum(d.current_status==x for d in devices) for x in ["up", "down", "unknown", "paused"]}
    return render(request,"dashboard.html",{"devices":devices,"counts":counts,"incidents":Incident.objects.filter(resolved_at__isnull=True).select_related("device")})
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
    return JsonResponse({"devices":list(Device.objects.filter(collector=collector,enabled=True).values("id","host","port"))})
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
        for result in results:
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
                device.status="up" if result["success"] else "down"
                device.last_seen=now
                device.latency_ms=result.get("latency_ms")
                device.save(update_fields=["status","last_seen","latency_ms"])
                CheckResult.objects.create(device=device,success=result["success"],latency_ms=device.latency_ms)
                if result["success"]: Incident.objects.filter(device=device,resolved_at__isnull=True).update(resolved_at=now)
                else: Incident.objects.get_or_create(device=device,resolved_at__isnull=True)
            Collector.objects.filter(pk=collector.pk).update(last_seen=now)
    except (ValueError,KeyError,TypeError): return JsonResponse({"error":"Invalid results"},status=400)
    return JsonResponse({"accepted":len(results)})
