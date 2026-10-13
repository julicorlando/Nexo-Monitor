import base64,hashlib,time
from cryptography.fernet import Fernet
import pyotp
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django import forms
from django.db import transaction
from .models import MFAProfile

def cipher():
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest()))
def protect(secret): return cipher().encrypt(secret.encode()).decode()
def reveal(secret): return cipher().decrypt(secret.encode()).decode()
def verify(user,code):
    with transaction.atomic():
        profile=MFAProfile.objects.select_for_update().filter(user=user).first()
        if not profile: return True
        totp=pyotp.TOTP(reveal(profile.encrypted_secret));counter=int(time.time())//30
        for value in range(counter-1,counter+2):
            if value>profile.last_counter and pyotp.utils.strings_equal(totp.at(value*30),str(code)):
                profile.last_counter=value;profile.save(update_fields=["last_counter"]);return True
        return False
class SecureAuthenticationForm(AuthenticationForm):
    otp=forms.CharField(label="Código do autenticador (se ativado)",required=False,max_length=6)
    def clean(self):
        from django.utils import timezone
        from datetime import timedelta
        from .models import LoginThrottle
        key=hashlib.sha256((str(self.request.META.get("REMOTE_ADDR",""))+"|"+str(self.cleaned_data.get("username","")).lower()).encode()).hexdigest()
        now=timezone.now()
        failure=None
        with transaction.atomic():
            record,_=LoginThrottle.objects.select_for_update().get_or_create(key=key)
            if now-record.started_at>timedelta(minutes=15):record.failures=0;record.started_at=now
            if record.failures>=10:
                failure=forms.ValidationError("Muitas tentativas. Aguarde 15 minutos.")
            else:
                try:result=super().clean()
                except forms.ValidationError as exc:
                    record.failures+=1;failure=exc
                else:record.failures=0
            record.save()
        if failure:raise failure
        return result
    def confirm_login_allowed(self,user):
        super().confirm_login_allowed(user)
        if not verify(user,self.cleaned_data.get("otp","")):
            raise forms.ValidationError("Código do autenticador inválido ou já utilizado.")
class MFAGate:
    def __init__(self,get_response):self.get_response=get_response
    def __call__(self,request):
        from django.shortcuts import redirect
        profile=MFAProfile.objects.filter(user=request.user).first() if request.user.is_authenticated else None
        if profile and request.session.get("mfa_version")!=profile.encrypted_secret:
            if request.path not in ["/login/","/logout/","/security/"]:
                from django.contrib.auth import logout
                logout(request)
                return redirect("/login/")
        response=self.get_response(request)
        if request.path in ["/security/","/login/","/admin/login/"]:response["Cache-Control"]="no-store"
        return response

