from django.core.management.base import BaseCommand
from monitor.models import Collector
class Command(BaseCommand):
    help = "Gera ou rotaciona o token de um coletor. Exibido apenas nesta execução."
    def add_arguments(self, parser): parser.add_argument("collector_id", type=int)
    def handle(self, *args, **options):
        self.stdout.write(Collector.objects.get(pk=options["collector_id"]).issue_token())
