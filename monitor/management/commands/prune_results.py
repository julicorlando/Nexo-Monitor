from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from monitor.models import CheckResult
class Command(BaseCommand):
    def handle(self,*args,**kwargs):
        count,_=CheckResult.objects.filter(created_at__lt=timezone.now()-timedelta(days=30)).delete()
        self.stdout.write(str(count))
