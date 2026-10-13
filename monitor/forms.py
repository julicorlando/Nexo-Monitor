import csv, io
from django import forms
from .models import Device
class InventoryImport(forms.Form):
    file=forms.FileField(label="CSV UTF-8")
    def clean_file(self):
        upload=self.cleaned_data["file"]
        if upload.size>1024*1024: raise forms.ValidationError("Limite de 1 MB.")
        try:
            rows=list(csv.DictReader(io.StringIO(upload.read().decode("utf-8-sig"))))
            if not rows or len(rows)>1000: raise ValueError()
            self.devices=[]
            for row in rows:
                allowed={k:v for k,v in row.items() if k in ["name","category","host","port","model","serial_number","location","check_type"] and v}
                device=Device(**allowed)
                device.full_clean(exclude=["collector"])
                self.devices.append(device)
        except Exception as exc: raise forms.ValidationError("CSV inválido: confira campos, categorias e portas.") from exc
        return upload

class DeviceForm(forms.ModelForm):
    class Meta:
        model=Device
        fields=["name","category","model","collector","host","port","check_type","http_path","expected_status","credential_key","snmp_oid","integration_path","service_name","serial_number","location","parent","failure_threshold","cpu_limit","memory_limit","disk_limit","maintenance_until","enabled","notes"]
        widgets={"maintenance_until":forms.DateTimeInput(attrs={"type":"datetime-local"})}
    def __init__(self,*args,user,**kwargs):
        from .models import Collector
        super().__init__(*args,**kwargs)
        self.fields["collector"].queryset=Collector.objects.all() if user.is_superuser else Collector.objects.filter(site__members=user)
        self.fields["parent"].queryset=Device.objects.all() if user.is_superuser else Device.objects.filter(collector__site__members=user)
    def clean(self):
        cleaned=super().clean();parent=cleaned.get("parent");collector=cleaned.get("collector")
        if parent and collector and parent.collector.site_id!=collector.site_id:raise forms.ValidationError("Dependência deve pertencer à mesma unidade.")
        seen=set();node=parent
        while node:
            if node.pk==self.instance.pk or node.pk in seen:raise forms.ValidationError("Dependência circular não permitida.")
            seen.add(node.pk);node=node.parent
        return cleaned

class WhatsAppForm(forms.ModelForm):
    recipient=forms.CharField(label="Único número autorizado (país + DDD + número)",required=False,max_length=40)
    class Meta:
        from .models import WhatsAppSettings
        model=WhatsAppSettings
        fields=["recipient","enabled","include_recovery"]
        labels={"recipient":"Único número autorizado (país + DDD + número)","enabled":"Ativar alertas de WhatsApp","include_recovery":"Avisar também quando recuperar"}
    def clean_recipient(self):
        import re
        value=re.sub(r"[\s()+-]","",self.cleaned_data["recipient"])
        if value and not re.fullmatch(r"[1-9][0-9]{10,14}",value):raise forms.ValidationError("Use país, DDD e número. Não são permitidos grupos ou listas.")
        return value

class SiteForm(forms.ModelForm):
    class Meta:
        from .models import Site
        model=Site
        fields=["name","address","latitude","longitude","members"]
class CollectorForm(forms.ModelForm):
    class Meta:
        from .models import Collector
        model=Collector
        fields=["name","site","enabled","offline_after"]
class EmailRecipientForm(forms.ModelForm):
    class Meta:
        from .models import AlertRecipient
        model=AlertRecipient
        fields=["site","email","enabled"]
