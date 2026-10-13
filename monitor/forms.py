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
