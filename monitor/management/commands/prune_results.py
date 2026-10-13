from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from monitor.models import CheckResult,IngestBatch,LoginThrottle
class Command(BaseCommand):
    def handle(self,*args,**kwargs):
        count,_=CheckResult.objects.filter(created_at__lt=timezone.now()-timedelta(days=30)).delete()
        IngestBatch.objects.filter(received_at__lt=timezone.now()-timedelta(days=8)).delete()
        LoginThrottle.objects.filter(started_at__lt=timezone.now()-timedelta(days=1)).delete()
        self.stdout.write(str(count))
