from django.contrib import admin
from .models import Site, Collector, Device, CheckResult, Incident, AlertRecipient, Notification
admin.site.site_header = "Nexo Monitor • Administração"
class PlatformAdmin(admin.ModelAdmin):
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
