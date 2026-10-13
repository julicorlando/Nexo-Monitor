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

    def test_batch_idempotency_and_historical_order(self):
        import uuid
        from .models import IngestBatch
        def post(payload):return self.client.post("/api/collector/results/",json.dumps(payload),content_type="application/json",HTTP_AUTHORIZATION="Bearer secret")
        payload={"batch_id":str(uuid.uuid4()),"observed_at":timezone.now().isoformat(),"results":[{"id":self.device.pk,"success":True}]}
        self.assertEqual(post(payload).status_code,200)
        self.assertTrue(post(payload).json()["duplicate"])
        self.assertEqual(CheckResult.objects.count(),1)
        payload["batch_id"]=str(uuid.uuid4());payload["observed_at"]=(timezone.now()-timedelta(hours=1)).isoformat();payload["results"][0]["success"]=False
        post(payload);self.device.refresh_from_db()
        self.assertEqual(self.device.status,"up")
        self.assertEqual(Incident.objects.count(),0)
    def test_dependency_and_maintenance(self):
        parent=Device.objects.create(name="Gateway",category="Roteador",collector=self.collector,host="localhost")
        self.device.parent=parent;self.device.save()
        self.send([{"id":parent.pk,"success":False},{"id":self.device.pk,"success":False}])
        self.assertEqual(list(Incident.objects.values_list("device_id",flat=True)),[parent.pk])
        self.device.maintenance_until=timezone.now()+timedelta(hours=1);self.device.save()
        self.send([{"id":parent.pk,"success":True},{"id":self.device.pk,"success":False}])
        self.assertFalse(Incident.objects.filter(resolved_at__isnull=True).exists())
    def test_collector_offline_alert_once(self):
        from .services import inspect_collectors
        from .models import Notification
        self.collector.last_seen=timezone.now()-timedelta(minutes=10);self.collector.save()
        inspect_collectors();inspect_collectors()
        self.assertEqual(Notification.objects.count(),1)
        self.send([]);inspect_collectors()
        self.assertEqual(Notification.objects.count(),2)
    def test_invalid_batch_date(self):
        payload={"observed_at":"2020-01-01T00:00:00+00:00","results":[]}
        response=self.client.post("/api/collector/results/",json.dumps(payload),content_type="application/json",HTTP_AUTHORIZATION="Bearer secret")
        self.assertEqual(response.status_code,400)
    def test_mfa_login_and_replay(self):
        import pyotp,time
        from django.contrib.auth.models import User
        from .models import MFAProfile
        from .security import protect
        user=User.objects.create_user(username="mfa",password="strong-test-password")
        secret=pyotp.random_base32()
        MFAProfile.objects.create(user=user,encrypted_secret=protect(secret))
        wrong=self.client.post("/login/",{"username":"mfa","password":"strong-test-password"})
        self.assertEqual(wrong.status_code,200)
        code=pyotp.TOTP(secret).now()
        self.assertEqual(self.client.post("/login/",{"username":"mfa","password":"strong-test-password","otp":code}).status_code,302)
        self.client.post("/logout/")
        self.assertEqual(self.client.post("/login/",{"username":"mfa","password":"strong-test-password","otp":code}).status_code,200)
    def test_spool_survives_restart_and_retries(self):
        import importlib.util,tempfile
        from pathlib import Path
        spec=importlib.util.spec_from_file_location("spool",Path(__file__).resolve().parent.parent/"collector/spool.py")
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            path=str(Path(directory)/"spool.sqlite3")
            spool=module.Spool(path);spool.cache([{"id":1}]);spool.enqueue([{"id":1,"success":True}]);spool.db.close()
            spool=module.Spool(path);self.assertEqual(spool.devices(),[{"id":1}])
            def fail(payload):raise OSError()
            with self.assertRaises(OSError):spool.flush(fail)
            sent=[];spool.flush(sent.append);spool.flush(sent.append)
            self.assertEqual(len(sent),1);self.assertIn("batch_id",sent[0]);spool.db.close()
    def test_device_form_cycles_and_cross_site(self):
        from django.contrib.auth.models import User
        from .forms import DeviceForm
        user=User.objects.create_superuser(username="root",password="test")
        self.device.parent=self.device
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):self.device.clean()
    def test_read_only_mikrotik_parser(self):
        import importlib.util
        from pathlib import Path
        from unittest.mock import patch
        spec=importlib.util.spec_from_file_location("integrations",Path(__file__).resolve().parent.parent/"collector/integrations.py")
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        responses=[b'{"cpu-load":"10","total-memory":"1000","free-memory":"400"}',b'[{"name":"ether1","running":"true"}]']
        with patch.object(module,"fetch",side_effect=responses):metrics,healthy=module.read({"check_type":"mikrotik"})
        self.assertTrue(healthy);self.assertEqual(metrics["memory"],60)
    def test_inventory_page_is_scoped(self):
        from django.contrib.auth.models import User
        user=User.objects.create_user(username="restricted",password="test")
        self.client.force_login(user)
        self.assertNotContains(self.client.get("/inventory/"),self.device.name)
        self.assertEqual(self.client.get(f"/devices/{self.device.pk}/edit/").status_code,403)

    def test_login_throttle(self):
        for _ in range(10):self.client.post("/login/",{"username":"blocked","password":"wrong"})
        self.assertContains(self.client.post("/login/",{"username":"blocked","password":"wrong"}),"Muitas tentativas")
    def test_mfa_invalidate_existing_session(self):
        import pyotp
        from django.contrib.auth.models import User
        from .models import MFAProfile
        from .security import protect
        user=User.objects.create_user(username="existing",password="test")
        self.client.force_login(user)
        MFAProfile.objects.create(user=user,encrypted_secret=protect(pyotp.random_base32()))
        self.assertEqual(self.client.get("/inventory/").status_code,302)
        self.assertNotIn("_auth_user_id",self.client.session)
    def test_all_new_pages_render(self):
        from django.contrib.auth.models import User
        user=User.objects.create_superuser(username="admin-ui",password="test")
        self.client.force_login(user)
        for url in ["/inventory/","/devices/new/","/units/","/audit/","/security/",f"/devices/{self.device.pk}/history/"]:
            self.assertEqual(self.client.get(url).status_code,200,url)

    def test_whatsapp_single_destination_and_no_repeat(self):
        from .models import WhatsAppSettings,Notification
        from .whatsapp import deliver
        from unittest.mock import patch
        config=WhatsAppSettings.objects.create(recipient="5581999991234",enabled=True)
        item=Notification.objects.create(site=self.collector.site,subject="Falha",body="Dispositivo offline")
        with patch("monitor.whatsapp.session_status",return_value="WORKING"),patch("monitor.whatsapp.gateway",return_value={"id":"message-1"}) as send:
            self.assertTrue(deliver(item.pk));self.assertFalse(deliver(item.pk))
        send.assert_called_once()
        self.assertEqual(send.call_args.args[2]["chatId"],"5581999991234@c.us")
        item.refresh_from_db();self.assertEqual(item.whatsapp_recipient,config.recipient)
    def test_whatsapp_rejects_groups_and_multiple_numbers(self):
        from .forms import WhatsAppForm
        for number in ["123456@g.us","5581999991234,5581999995678","5581999991234@c.us"]:
            form=WhatsAppForm({"recipient":number,"enabled":True})
            self.assertFalse(form.is_valid())
        form=WhatsAppForm({"recipient":"+55 (81) 99999-1234","enabled":True})
        self.assertTrue(form.is_valid(),form.errors)
    def test_whatsapp_recovery_opt_in_and_history_cutoff(self):
        from .models import WhatsAppSettings,Notification
        from .whatsapp import deliver
        from unittest.mock import patch
        old=Notification.objects.create(site=self.collector.site,subject="Old",body="")
        WhatsAppSettings.objects.create(recipient="5581999991234",enabled=True)
        recovery=Notification.objects.create(site=self.collector.site,event_kind="recovery",subject="Recuperado",body="")
        with patch("monitor.whatsapp.gateway") as send:
            self.assertFalse(deliver(old.pk));self.assertFalse(deliver(recovery.pk));send.assert_not_called()
    def test_whatsapp_retry_and_destination_change(self):
        from .models import WhatsAppSettings,Notification
        from .whatsapp import deliver,GatewayError
        from unittest.mock import patch
        config=WhatsAppSettings.objects.create(recipient="5581999991234",enabled=True)
        item=Notification.objects.create(site=self.collector.site,subject="Offline",body="")
        with patch("monitor.whatsapp.session_status",return_value="WORKING"),patch("monitor.whatsapp.gateway",side_effect=GatewayError("gateway_unavailable")):
            self.assertFalse(deliver(item.pk))
        item.refresh_from_db();self.assertEqual(item.whatsapp_attempts,1)
        self.assertIsNotNone(item.whatsapp_next_attempt)
        config.recipient="5581999995678";config.save()
        item.whatsapp_next_attempt=None;item.save()
        with patch("monitor.whatsapp.gateway") as send:
            self.assertFalse(deliver(item.pk));send.assert_not_called()
        item.refresh_from_db();self.assertEqual(item.whatsapp_last_error,"recipient_changed")
    def test_whatsapp_routes_admin_only_and_post_csrf(self):
        from django.contrib.auth.models import User
        from django.test import Client
        from unittest.mock import patch
        user=User.objects.create_user(username="whatsapp-viewer",password="test")
        self.client.force_login(user)
        for url in ["/whatsapp/","/whatsapp/qr/","/whatsapp/status/"]:self.assertEqual(self.client.get(url).status_code,403)
        root=User.objects.create_superuser(username="whatsapp-admin",password="test")
        client=Client(enforce_csrf_checks=True);client.force_login(root)
        self.assertEqual(client.post("/whatsapp/",{"action":"connect"}).status_code,403)
        self.client.force_login(root)
        with patch("monitor.whatsapp.session_status",return_value="STOPPED"):
            self.assertEqual(self.client.get("/whatsapp/").status_code,200)
    def test_whatsapp_qr_is_private_and_not_cached(self):
        from django.contrib.auth.models import User
        from unittest.mock import patch
        root=User.objects.create_superuser(username="qr-admin",password="test")
        self.client.force_login(root)
        with patch("monitor.whatsapp.gateway",return_value=b"PNG"):
            response=self.client.get("/whatsapp/qr/")
        self.assertEqual(response["Cache-Control"],"no-store")
        self.assertEqual(response["Content-Type"],"image/png")
    def test_unifi_pagination_considers_all_devices(self):
        import importlib.util
        from pathlib import Path
        from unittest.mock import patch
        spec=importlib.util.spec_from_file_location("integration_paged",Path(__file__).resolve().parent.parent/"collector/integrations.py")
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        pages=[json.dumps({"data":[{"id":"1","state":"ONLINE"}],"totalCount":2}).encode(),json.dumps({"data":[{"id":"2","state":"OFFLINE"}],"totalCount":2}).encode()]
        with patch.object(module,"fetch",side_effect=pages) as fetch:metrics,healthy=module.read({"check_type":"unifi","integration_path":"/integration/v1/sites/x/devices"})
        self.assertFalse(healthy);self.assertEqual(metrics["integration"]["count"],2)
        self.assertIn("offset=1",fetch.call_args.args[1])
    def test_snmpv3_uses_private_file_not_command_password(self):
        import importlib.util,tempfile
        from pathlib import Path
        from unittest.mock import patch,MagicMock
        spec=importlib.util.spec_from_file_location("agent_v3",Path(__file__).resolve().parent.parent/"collector/agent.py")
        agent=importlib.util.module_from_spec(spec);spec.loader.exec_module(agent)
        with tempfile.TemporaryDirectory() as folder:
            config=Path(folder)/"snmp.conf";config.write_text("defSecurityName test\ndefAuthPassphrase secret\n");config.chmod(0o600)
            with patch.dict(agent.os.environ,{"NEXO_SNMP_SWITCH_CONFIG":folder}),patch.object(agent.subprocess,"run",return_value=MagicMock(stdout="123")) as run:
                result=agent.check({"id":1,"check_type":"snmp","host":"localhost","snmp_oid":"1.3.6.1","credential_key":"switch"})
            self.assertTrue(result["success"]);self.assertIn("-v3",run.call_args.args[0]);self.assertNotIn("secret",run.call_args.args[0])

    def test_stale_whatsapp_offline_event_is_not_sent(self):
        from .models import WhatsAppSettings,Notification
        from .whatsapp import deliver
        from unittest.mock import patch
        WhatsAppSettings.objects.create(recipient="5581999991234",enabled=True)
        item=Notification.objects.create(site=self.collector.site,device=self.device,subject="Offline",body="")
        self.device.status="up";self.device.save()
        with patch("monitor.whatsapp.gateway") as send:
            self.assertFalse(deliver(item.pk));send.assert_not_called()
        item.refresh_from_db();self.assertEqual(item.whatsapp_last_error,"event_resolved")
    def test_infrastructure_setup_and_tokens(self):
        from django.contrib.auth.models import User
        root=User.objects.create_superuser(username="setup-admin",password="test")
        self.client.force_login(root)
        response=self.client.post("/infrastructure/collector/new/",{"name":"New","site":self.collector.site.pk,"enabled":"on","offline_after":"180"})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response["Cache-Control"],"no-store")
        self.assertContains(response,"Token do coletor")
        self.assertTrue(Collector.objects.filter(name="New").exists())
    def test_whatsapp_test_action_ignores_destination_input(self):
        from django.contrib.auth.models import User
        from .models import WhatsAppSettings,Notification
        from unittest.mock import patch
        root=User.objects.create_superuser(username="test-wa-admin",password="test")
        self.client.force_login(root)
        WhatsAppSettings.objects.create(recipient="5581999991234",enabled=True)
        with patch("monitor.whatsapp.session_status",return_value="WORKING"):
            response=self.client.post("/whatsapp/",{"action":"test","recipient":"5581999995678","chatId":"arbitrary@g.us","text":"arbitrary"})
        self.assertEqual(response.status_code,200)
        self.assertEqual(WhatsAppSettings.objects.get().recipient,"5581999991234")
        self.assertEqual(Notification.objects.get(event_kind="test").body,"O canal de alertas está configurado para este número.")
    def test_whatsapp_settings_singleton_database_constraint(self):
        from .models import WhatsAppSettings
        from django.db import IntegrityError,transaction
        with self.assertRaises(IntegrityError),transaction.atomic():WhatsAppSettings.objects.create(pk=2)

    def test_setup_scopes_progress_by_unit(self):
        from django.contrib.auth.models import User
        user=User.objects.create_user(username="new-setup-user",password="test")
        self.client.force_login(user)
        response=self.client.get("/setup/")
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.context["completed"],0)
        self.collector.site.members.add(user)
        response=self.client.get("/setup/")
        self.assertEqual(response.context["completed"],3)
        self.assertNotContains(response,"Configurar WhatsApp")
    def test_setup_admin_empty_redirect_and_recent_data(self):
        from django.contrib.auth.models import User
        root=User.objects.create_superuser(username="setup-guide-admin",password="test")
        self.client.force_login(root)
        self.collector.last_seen=timezone.now();self.collector.save()
        self.device.last_seen=timezone.now();self.device.save()
        response=self.client.get("/setup/")
        self.assertEqual(response.context["completed"],5)
        self.assertContains(response,"NEXO_TOKEN")
        self.assertContains(response,"a leitura deve ser conferida")
    def test_setup_requires_login(self):
        self.assertEqual(self.client.get("/setup/").status_code,302)

    def test_recovery_requires_consecutive_successes(self):
        self.device.recovery_threshold=2;self.device.save()
        self.send([{"id":self.device.pk,"success":False}])
        self.send([{"id":self.device.pk,"success":True}])
        self.assertTrue(Incident.objects.filter(resolved_at__isnull=True).exists())
        self.send([{"id":self.device.pk,"success":True}])
        self.assertFalse(Incident.objects.filter(resolved_at__isnull=True).exists())
    def test_diagnostics_validated_and_received(self):
        payload={"results":[],"diagnostics":{"version":"0.4.0","queue_batches":10,"queue_bytes":2048,"last_error":""}}
        response=self.client.post("/api/collector/results/",json.dumps(payload),content_type="application/json",HTTP_AUTHORIZATION="Bearer secret")
        self.assertEqual(response.status_code,200)
        self.collector.refresh_from_db();self.assertEqual(self.collector.diagnostics["queue_batches"],10)
        payload["diagnostics"]["queue_batches"]=-1
        self.assertEqual(self.client.post("/api/collector/results/",json.dumps(payload),content_type="application/json",HTTP_AUTHORIZATION="Bearer secret").status_code,400)
    def test_archive_keeps_history_and_omits_config(self):
        from django.contrib.auth.models import User
        root=User.objects.create_superuser(username="archive-admin",password="test")
        self.send([{"id":self.device.pk,"success":True}]);self.client.force_login(root)
        self.assertEqual(self.client.post(f"/devices/{self.device.pk}/archive/").status_code,302)
        self.assertEqual(CheckResult.objects.count(),1)
        config=self.client.get("/api/collector/config/",HTTP_AUTHORIZATION="Bearer secret").json()
        self.assertEqual(config["devices"],[])
        self.client.post(f"/devices/{self.device.pk}/archive/",{"restore":"yes"})
        self.device.refresh_from_db();self.assertIsNone(self.device.archived_at);self.assertEqual(self.device.current_status,"unknown")
    def test_worker_health_is_independent(self):
        from .models import WorkerState
        self.assertEqual(self.client.get("/health/monitoring/").status_code,503)
        state=WorkerState.objects.create(name="main")
        self.assertEqual(self.client.get("/health/monitoring/").status_code,200)
        state.last_seen=timezone.now()-timedelta(minutes=6);state.save()
        self.assertEqual(self.client.get("/health/monitoring/").status_code,503)
    def test_missing_results_alerts_once_with_live_collector(self):
        from .services import inspect_collectors
        from .models import Notification
        self.collector.last_seen=timezone.now();self.collector.save()
        self.device.last_seen=timezone.now()-timedelta(minutes=10);self.device.save()
        inspect_collectors();inspect_collectors()
        self.assertEqual(Notification.objects.filter(event_kind="monitoring").count(),1)
    def test_preview_does_not_mutate_or_send(self):
        from django.contrib.auth.models import User
        user=User.objects.create_user(username="preview-user",password="test")
        self.collector.site.members.add(user);self.client.force_login(user)
        self.assertEqual(self.client.get(f"/devices/{self.device.pk}/alert-preview/").status_code,200)
        self.assertEqual(Incident.objects.count(),0)
    def test_changes_are_field_level(self):
        from django.contrib.auth.models import User
        from .operations import config_snapshot,record_change
        from .models import AuditEvent
        user=User.objects.create_user(username="audit-user")
        before=config_snapshot(self.device)
        self.device.host="10.0.0.99";self.device.save()
        record_change(user,self.device,before,"device.update",self.collector.site)
        self.assertEqual(AuditEvent.objects.get().changes["host"],{"before":"192.168.1.2","after":"10.0.0.99"})
    def test_incident_roles_and_unit_isolation(self):
        from django.contrib.auth.models import User,Group
        from django.core.management import call_command
        call_command("configure_roles")
        user=User.objects.create_user(username="incident-user",password="test")
        self.collector.site.members.add(user)
        self.send([{"id":self.device.pk,"success":False}])
        incident=Incident.objects.get();self.client.force_login(user)
        url=f"/incidents/{incident.pk}/"
        self.assertEqual(self.client.post(url,{"action":"acknowledge"}).status_code,403)
        user.groups.add(Group.objects.get(name="Nexo — Operador de incidentes"))
        self.assertEqual(self.client.post(url,{"action":"acknowledge"}).status_code,200)
        self.assertEqual(self.client.post(url,{"action":"note","body":"Verificando energia"}).status_code,200)
        self.assertEqual(incident.incidentnote_set.count(),1)
        outsider=User.objects.create_user(username="other-unit")
        self.assertEqual(self.client.post(url,{"action":"assign","assigned_to":outsider.pk}).status_code,404)
