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

    def test_invalid_metrics_rejected(self):
        self.assertEqual(self.send([{"id":self.device.id,"success":True,"metrics":{"cpu":101}}]).status_code,400)
    def test_failure_threshold_and_notifications(self):
        from .models import Notification
        self.device.failure_threshold=2;self.device.save()
        result={"id":self.device.id,"success":False}
        self.send([result]);self.assertEqual(Incident.objects.count(),0)
        self.send([result]);self.send([result]);self.assertEqual(Notification.objects.count(),1)
        result["success"]=True;self.send([result]);self.assertEqual(Notification.objects.count(),2)
    def test_site_membership(self):
        from django.contrib.auth.models import User
        user=User.objects.create_user(username="viewer",password="test-password")
        self.client.force_login(user)
        self.assertEqual(self.client.get(f"/devices/{self.device.pk}/history/").status_code,404)
        self.collector.site.members.add(user)
        self.assertEqual(self.client.get(f"/devices/{self.device.pk}/history/").status_code,200)
    def test_csv_validation(self):
        from .forms import InventoryImport
        from django.core.files.uploadedfile import SimpleUploadedFile
        form=InventoryImport(files={"file":SimpleUploadedFile("inventory.csv",b"name,category,host,port\nServer,Servidor,localhost,443\n")})
        self.assertTrue(form.is_valid(),form.errors)
        form=InventoryImport(files={"file":SimpleUploadedFile("inventory.csv",b"name,category,host,port\nServer,Servidor,localhost,99999\n")})
        self.assertFalse(form.is_valid())
    def test_email_worker(self):
        from django.core import mail
        from django.core.management import call_command
        from django.test import override_settings
        from .models import AlertRecipient,Notification
        AlertRecipient.objects.create(site=self.collector.site,email="ops@example.com")
        item=Notification.objects.create(site=self.collector.site,subject="Test",body="Failure")
        with override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            call_command("send_notifications");call_command("send_notifications")
        self.assertEqual(len(mail.outbox),1)
        item.refresh_from_db();self.assertIsNotNone(item.sent_at)

    def test_collector_checks(self):
        import importlib.util
        from pathlib import Path
        from unittest.mock import patch, MagicMock
        spec=importlib.util.spec_from_file_location("agent",Path(__file__).resolve().parent.parent/"collector/agent.py")
        agent=importlib.util.module_from_spec(spec);spec.loader.exec_module(agent)
        with patch.object(agent.socket,"create_connection") as connect:
            result=agent.check({"id":1,"host":"localhost","port":443})
            self.assertTrue(result["success"])
            connect.side_effect=OSError()
            self.assertFalse(agent.check({"id":1,"host":"localhost","port":443})["success"])
        with patch.object(agent.subprocess,"run") as run:
            self.assertFalse(agent.check({"id":1,"check_type":"ping","host":"-malicious"})["success"])
            run.assert_not_called()
            run.return_value=MagicMock(stdout="123")
            with patch.dict(agent.os.environ,{"NEXO_SNMP_SWITCH":"private"}):
                result=agent.check({"id":1,"check_type":"snmp","host":"localhost","snmp_oid":"1.3.6.1","credential_key":"switch"})
            self.assertEqual(result["metrics"],{"snmp_value":"123"})
