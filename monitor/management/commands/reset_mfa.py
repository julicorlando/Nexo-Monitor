from django.core.management.base import BaseCommand,CommandError
from django.contrib.auth.models import User
from monitor.models import MFAProfile,AuditEvent
class Command(BaseCommand):
    help="Recuperação administrativa: remove MFA do usuário, exige acesso ao terminal do servidor."
    def add_arguments(self,parser):parser.add_argument("username")
    def handle(self,*args,**options):
        try:user=User.objects.get(username=options["username"])
        except User.DoesNotExist:raise CommandError("Usuário inexistente")
        MFAProfile.objects.filter(user=user).delete()
        AuditEvent.objects.create(actor=user,action="mfa.emergency_reset",object_label=user.username)
        self.stdout.write("MFA removido. Revise o evento de auditoria e reative após recuperação.")
