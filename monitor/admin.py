from django.contrib import admin
from .models import Site, Collector, Device, CheckResult, Incident, AlertRecipient, Notification, AuditEvent
admin.site.site_header = "Nexo Monitor • Administração"
class PlatformAdmin(admin.ModelAdmin):
    def save_model(self,request,obj,form,change):
        from .operations import config_snapshot,record_change
        previous=type(obj).objects.filter(pk=obj.pk).first() if change else None
        before=config_snapshot(previous) if previous else {}
        super().save_model(request,obj,form,change)
        site=getattr(obj,"site",None)
        if isinstance(obj,Device):site=obj.collector.site
        if isinstance(obj,Site):site=obj
        record_change(request.user,obj,before,"admin.update" if change else "admin.create",site)
    def delete_model(self,request,obj):
        AuditEvent.objects.create(actor=request.user,action="admin.delete",object_label=f"{obj._meta.label}:{obj.pk}")
        super().delete_model(request,obj)
    actions=None
    # Global administration is restricted to platform administrators.
    def has_module_permission(self,request): return request.user.is_superuser
    def has_view_permission(self,request,obj=None): return request.user.is_superuser
    def has_add_permission(self,request): return request.user.is_superuser
    def has_change_permission(self,request,obj=None): return request.user.is_superuser
    def has_delete_permission(self,request,obj=None): return request.user.is_superuser
@admin.register(Device)
class DeviceAdmin(PlatformAdmin):
    list_display=["name","category","collector","host","check_type","status"]
    search_fields=["name","host","serial_number"]
    list_filter=["category","check_type","collector__site"]
for model in [Site, Collector, CheckResult, Incident, AlertRecipient, Notification]: admin.site.register(model,PlatformAdmin)
