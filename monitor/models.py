import hashlib, secrets
from django.db import models
from django.utils import timezone
class Site(models.Model):
    name = models.CharField(max_length=120)
    address = models.CharField(max_length=250, blank=True)
    def __str__(self): return self.name
class Collector(models.Model):
    name = models.CharField(max_length=120)
    site = models.ForeignKey(Site, on_delete=models.PROTECT)
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    enabled = models.BooleanField(default=True)
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
    model = models.CharField(max_length=120, blank=True)
    collector = models.ForeignKey(Collector, on_delete=models.PROTECT)
    host = models.CharField(max_length=253)
    port = models.PositiveIntegerField(default=443)
    enabled = models.BooleanField(default=True)
    status = models.CharField(max_length=12, default="unknown")
    last_seen = models.DateTimeField(null=True, blank=True)
    latency_ms = models.FloatField(null=True, blank=True)
    def __str__(self): return self.name
    @property
    def current_status(self):
        if not self.enabled: return "paused"
        if not self.last_seen or (timezone.now()-self.last_seen).total_seconds()>180: return "unknown"
        return self.status
class CheckResult(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    success = models.BooleanField()
    latency_ms = models.FloatField(null=True)
class Incident(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    opened_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["device"], condition=models.Q(resolved_at__isnull=True), name="one_open_incident")]
