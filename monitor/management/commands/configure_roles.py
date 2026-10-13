from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group,Permission
class Command(BaseCommand):
    help="Cria papéis; não associa usuários ou unidades automaticamente."
    def handle(self,*args,**kwargs):
        roles={"Nexo — Visualizador":["view_device","view_incident"],"Nexo — Configurador":["view_device","view_incident","add_device","change_device"],"Nexo — Operador de incidentes":["view_device","view_incident","manage_incidents"]}
        for name,codes in roles.items():
            group,_=Group.objects.get_or_create(name=name)
            group.permissions.set(Permission.objects.filter(content_type__app_label="monitor",codename__in=codes))
        self.stdout.write("Papéis configurados. Associe usuários a grupos e a unidades.")
