from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from .models import MFAProfile,AuditEvent
@receiver(user_logged_in)
def login_event(sender,request,user,**kwargs):
    profile=MFAProfile.objects.filter(user=user).first()
    if profile:request.session["mfa_version"]=profile.encrypted_secret
    AuditEvent.objects.create(actor=user,action="login",object_label=user.username)
