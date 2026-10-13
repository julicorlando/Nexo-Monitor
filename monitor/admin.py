from django.contrib import admin
from .models import Site, Collector, Device, CheckResult, Incident
admin.site.site_header = "Nexo Monitor • Administração"
for model in [Site, Collector, Device, CheckResult, Incident]: admin.site.register(model)
