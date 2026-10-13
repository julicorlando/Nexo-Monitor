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
        fields=["name","category","model","collector","host","port","check_type","http_path","expected_status","credential_key","snmp_oid","integration_path","service_name","serial_number","location","parent","failure_threshold","recovery_threshold","cpu_limit","memory_limit","disk_limit","maintenance_until","enabled","notes"]
        widgets={"maintenance_until":forms.DateTimeInput(attrs={"type":"datetime-local"})}
    def __init__(self,*args,user,**kwargs):
        from .models import Collector
        super().__init__(*args,**kwargs)
        labels={"name":"Nome do equipamento","category":"Categoria","model":"Modelo","collector":"Coletor responsável","host":"IP ou nome na rede","port":"Porta do serviço","check_type":"Tipo de verificação","http_path":"Caminho HTTPS","expected_status":"Código HTTP esperado","credential_key":"Nome da credencial no coletor","snmp_oid":"OID SNMP","integration_path":"Caminho da API da integração","service_name":"Nome do serviço ou processo local","serial_number":"Número de série","location":"Localização dentro da unidade","parent":"Equipamento do qual depende","failure_threshold":"Falhas consecutivas antes de alertar","recovery_threshold":"Sucessos consecutivos para confirmar recuperação","cpu_limit":"Limite de CPU (%)","memory_limit":"Limite de memória (%)","disk_limit":"Limite de disco (%)","maintenance_until":"Silenciar alertas até","enabled":"Ativar monitoramento","notes":"Observações"}
        hints={"host":"Ex.: 10.0.0.20. Use o endereço alcançável pelo coletor, não pelo navegador.","port":"TCP/HTTPS usam esta porta. Ping não usa porta. Ex.: 443 para HTTPS, se habilitado no equipamento.","collector":"Escolha o coletor instalado na mesma rede do equipamento.","credential_key":"Somente o nome da configuração. Senhas ficam nas variáveis locais do coletor.","parent":"Ex.: switch ou roteador. Alertas do dependente são suprimidos quando o pai não está disponível.","failure_threshold":"1 alerta na primeira falha; 3 aguarda três falhas consecutivas.","check_type":"Comece com ping ou TCP. Integrações exigem API/SNMP habilitados e credenciais de leitura.","maintenance_until":"A coleta continua, mas alertas são silenciados até esta data.","service_name":"Exige coletor instalado na própria máquina. Não consulta serviços de outro computador."}
        self.fields["check_type"].choices=[("tcp","Conexão a uma porta (TCP)"),("ping","Resposta na rede (ping)"),("http","Página ou API HTTPS"),("system","CPU, memória e disco da máquina do coletor"),("service","Serviço/processo na máquina do coletor"),("snmp","Consulta de um OID SNMP"),("snmpwalk","Consulta de uma subárvore SNMP"),("mikrotik","MikroTik — API de leitura"),("unifi","UniFi — lista de dispositivos"),("hikvision","Hikvision — estado dos discos compatíveis")]
        hints["recovery_threshold"]="Ex.: 3 exige três testes bem-sucedidos antes de fechar um incidente. Evita avisos de recuperação por um sucesso isolado."
        for key,label in labels.items():self.fields[key].label=label
        for key,hint in hints.items():self.fields[key].help_text=hint
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
        labels={"name":"Nome da unidade","address":"Endereço","latitude":"Latitude (opcional)","longitude":"Longitude (opcional)","members":"Usuários autorizados a visualizar esta unidade"}
        help_texts={"name":"Ex.: Matriz ou Filial 01.","members":"Administradores gerais já têm acesso. Selecione usuários comuns apenas quando necessário."}
class CollectorForm(forms.ModelForm):
    class Meta:
        from .models import Collector
        model=Collector
        fields=["name","site","enabled","offline_after"]
        labels={"name":"Nome do coletor","site":"Unidade","enabled":"Ativar coletor","offline_after":"Tempo sem contato para alertar (segundos)"}
        help_texts={"name":"Ex.: Coletor da Matriz. O cadastro não instala o programa.","offline_after":"180 segundos = 3 minutos. Depois de salvo, copie o token e configure o programa na máquina local."}
class EmailRecipientForm(forms.ModelForm):
    class Meta:
        from .models import AlertRecipient
        model=AlertRecipient
        fields=["site","email","enabled"]
        labels={"site":"Unidade","email":"E-mail de destino","enabled":"Ativar destinatário"}
        help_texts={"email":"O envio depende das variáveis SMTP configuradas no Coolify."}
