import hashlib,json
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from .models import Site,Collector,Device,Incident,CheckResult
class MonitoringTests(TestCase):
    def setUp(self):
        self.collector=Collector.objects.create(name="Local",site=Site.objects.create(name="Matriz"),token_hash=hashlib.sha256(b"secret").hexdigest())
        self.device=Device.objects.create(name="Servidor",category="Servidor",collector=self.collector,host="192.168.1.2",port=443)
    def send(self,results,token="secret"):
        return self.client.post("/api/collector/results/",json.dumps({"results":results}),content_type="application/json",HTTP_AUTHORIZATION="Bearer "+token)
    def test_login_required(self): self.assertEqual(self.client.get("/").status_code,302)
    def test_auth(self): self.assertEqual(self.send([],"invalid").status_code,401)
    def test_incident_lifecycle(self):
        result={"id":self.device.id,"success":False}
        self.assertEqual(self.send([result]).status_code,200)
        self.send([result]);self.assertEqual(Incident.objects.count(),1)
        result["success"]=True;self.send([result])
        self.assertFalse(Incident.objects.filter(resolved_at__isnull=True).exists())
    def test_foreign_device_rejected_atomically(self):
        other=Collector.objects.create(name="Outra",site=self.collector.site,token_hash="x"*64)
        d=Device.objects.create(name="Outro",category="Servidor",collector=other,host="localhost")
        self.assertEqual(self.send([{"id":self.device.id,"success":True},{"id":d.id,"success":True}]).status_code,400)
        self.assertEqual(CheckResult.objects.count(),0)
    def test_duplicate_and_invalid_latency(self):
        result={"id":self.device.id,"success":True}
        self.assertEqual(self.send([result,result]).status_code,400)
        result["latency_ms"]=-1;self.assertEqual(self.send([result]).status_code,400)
    def test_stale_status(self):
        self.device.status="up";self.device.last_seen=timezone.now()-timedelta(minutes=4)
        self.assertEqual(self.device.current_status,"unknown")
