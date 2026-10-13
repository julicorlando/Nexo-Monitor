import hashlib, secrets
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
class Site(models.Model):
    name = models.CharField(max_length=120)
    members = models.ManyToManyField(User, blank=True)
    latitude = models.FloatField(null=True,blank=True,validators=[MinValueValidator(-90),MaxValueValidator(90)])
    longitude = models.FloatField(null=True,blank=True,validators=[MinValueValidator(-180),MaxValueValidator(180)])
    address = models.CharField(max_length=250, blank=True)
    def __str__(self): return self.name
def lambda_token_hash():
    return hashlib.sha256(secrets.token_bytes(32)).hexdigest()
class Collector(models.Model):
    name = models.CharField(max_length=120)
    site = models.ForeignKey(Site, on_delete=models.PROTECT)
    token_hash = models.CharField(max_length=64, unique=True, editable=False, default=lambda_token_hash)
    enabled = models.BooleanField(default=True)
    diagnostics_alerted = models.BooleanField(default=False)
    diagnostics = models.JSONField(default=dict,blank=True)
    offline = models.BooleanField(default=False)
    offline_after = models.PositiveIntegerField(default=180, validators=[MinValueValidator(60),MaxValueValidator(3600)])
    last_seen = models.DateTimeField(null=True, blank=True)
    def issue_token(self):
        token = secrets.token_urlsafe(32)
        self.token_hash = hashlib.sha256(token.encode()).hexdigest()
        self.save()
        return token
    def __str__(self): return self.name
class Device(models.Model):
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=40, choices=[(x,x) for x in ["Switch", "Roteador", "AP", "Servidor", "Desktop", "Notebook", "Câmera", "NVR", "REP", "Impressora", "Caixa", "Autoatendimento", "Estacionamento", "Outro"]])
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)
    maintenance_until = models.DateTimeField(null=True, blank=True)
    model = models.CharField(max_length=120, blank=True)
    collector = models.ForeignKey(Collector, on_delete=models.PROTECT)
    host = models.CharField(max_length=253)
    port = models.PositiveIntegerField(default=443, validators=[MinValueValidator(1), MaxValueValidator(65535)])
    check_type = models.CharField(max_length=12, choices=[(x,x) for x in ["tcp","http","ping","system","snmp","mikrotik","unifi","hikvision","snmpwalk","service"]], default="tcp")
    http_path = models.CharField(max_length=200, default="/")
    expected_status = models.PositiveIntegerField(default=200, validators=[MinValueValidator(100),MaxValueValidator(599)])
    integration_path = models.CharField(max_length=300, blank=True)
    service_name = models.CharField(max_length=120, blank=True)
    snmp_oid = models.CharField(max_length=200, default="1.3.6.1.2.1.1.3.0")
    credential_key = models.SlugField(blank=True, help_text="Nome da variável local de credencial SNMP no coletor")
    serial_number = models.CharField(max_length=120, blank=True)
    location = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    cpu_limit = models.PositiveIntegerField(default=90, validators=[MaxValueValidator(100)])
    memory_limit = models.PositiveIntegerField(default=90, validators=[MaxValueValidator(100)])
    disk_limit = models.PositiveIntegerField(default=90, validators=[MaxValueValidator(100)])
    failure_threshold = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1),MaxValueValidator(20)])
    created_at = models.DateTimeField(default=timezone.now)
    archived_at = models.DateTimeField(null=True,blank=True)
    stale_alerted = models.BooleanField(default=False)
    recovery_threshold = models.PositiveIntegerField(default=1,validators=[MinValueValidator(1),MaxValueValidator(20)])
    consecutive_successes = models.PositiveIntegerField(default=0)
    consecutive_failures = models.PositiveIntegerField(default=0)
    metrics = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)
    status = models.CharField(max_length=12, default="unknown")
    last_seen = models.DateTimeField(null=True, blank=True)
    latency_ms = models.FloatField(null=True, blank=True)
    def clean(self):
        from django.core.exceptions import ValidationError
        if self.parent_id:
            node=self.parent;seen=set()
            while node:
                if node.pk==self.pk or node.pk in seen:raise ValidationError("Dependência circular não permitida.")
                if self.collector_id and node.collector.site_id!=self.collector.site_id:raise ValidationError("Dependência precisa estar na mesma unidade.")
                seen.add(node.pk);node=node.parent
    def __str__(self): return self.name
    @property
    def current_status(self):
        if not self.enabled: return "paused"
        if not self.last_seen or (timezone.now()-self.last_seen).total_seconds()>self.collector.offline_after: return "unknown"
        return self.status
class CheckResult(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    observed_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    metrics = models.JSONField(default=dict, blank=True)
    success = models.BooleanField()
    latency_ms = models.FloatField(null=True)
class Incident(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    acknowledged_at = models.DateTimeField(null=True,blank=True)
    assigned_to = models.ForeignKey(User,null=True,blank=True,on_delete=models.SET_NULL)
    opened_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["device"], condition=models.Q(resolved_at__isnull=True), name="one_open_incident")]

class Notification(models.Model):
    site = models.ForeignKey(Site, on_delete=models.CASCADE)
    device = models.ForeignKey(Device,null=True,blank=True,on_delete=models.SET_NULL)
    collector = models.ForeignKey(Collector,null=True,blank=True,on_delete=models.SET_NULL)
    event_kind = models.CharField(max_length=30,default="offline")
    whatsapp_sent_at = models.DateTimeField(null=True,blank=True)
    whatsapp_attempts = models.PositiveIntegerField(default=0)
    whatsapp_next_attempt = models.DateTimeField(null=True,blank=True)
    whatsapp_last_error = models.CharField(max_length=120,blank=True)
    whatsapp_recipient = models.CharField(max_length=15,blank=True)
    whatsapp_provider_id = models.CharField(max_length=200,blank=True)
    subject = models.CharField(max_length=200)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=200, blank=True)
class AlertRecipient(models.Model):
    site = models.ForeignKey(Site, on_delete=models.CASCADE)
    email = models.EmailField()
    enabled = models.BooleanField(default=True)

class IngestBatch(models.Model):
    collector = models.ForeignKey(Collector,on_delete=models.CASCADE)
    batch_id = models.UUIDField()
    received_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=["collector","batch_id"],name="unique_collector_batch")]
class AuditEvent(models.Model):
    actor = models.ForeignKey(User,null=True,on_delete=models.SET_NULL)
    site = models.ForeignKey(Site,null=True,on_delete=models.SET_NULL)
    action = models.CharField(max_length=50)
    changes = models.JSONField(default=dict,blank=True)
    object_label = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
class MFAProfile(models.Model):
    user = models.OneToOneField(User,on_delete=models.CASCADE)
    encrypted_secret = models.TextField()
    last_counter = models.BigIntegerField(default=-1)

class LoginThrottle(models.Model):
    key = models.CharField(max_length=64,primary_key=True)
    failures = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(default=timezone.now)

class WhatsAppSettings(models.Model):
    # Single global recipient. No per-request destination is accepted by the sender.
    id = models.PositiveSmallIntegerField(primary_key=True,default=1,editable=False)
    recipient = models.CharField(max_length=15,blank=True)
    enabled = models.BooleanField(default=False)
    include_recovery = models.BooleanField(default=False)
    activated_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    def clean(self):
        from django.core.exceptions import ValidationError
        import re
        if self.pk!=1:raise ValidationError("Somente uma configuração de WhatsApp é permitida.")
        if self.recipient and not re.fullmatch(r"[1-9][0-9]{10,14}",self.recipient):raise ValidationError("Use país, DDD e número; somente dígitos.")
        if self.enabled and not self.recipient:raise ValidationError("Cadastre o destinatário antes de ativar.")
    class Meta:
        constraints=[models.CheckConstraint(condition=models.Q(id=1),name="singleton_whatsapp")]

class WorkerState(models.Model):
    name=models.CharField(max_length=30,primary_key=True,default="main")
    last_seen=models.DateTimeField(default=timezone.now)
    last_error=models.CharField(max_length=120,blank=True)
class IncidentNote(models.Model):
    incident=models.ForeignKey(Incident,on_delete=models.CASCADE)
    actor=models.ForeignKey(User,null=True,on_delete=models.SET_NULL)
    body=models.TextField(max_length=2000)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        permissions=[("manage_incidents","Reconhecer e acompanhar incidentes")]
