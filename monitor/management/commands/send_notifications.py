from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.utils import timezone
from monitor.models import Notification, AlertRecipient
class Command(BaseCommand):
    help="Envie em um único worker agendado. Entrega pelo menos uma vez; SMTP não permite garantia de envio único."
    def handle(self,*args,**kwargs):
        for item in Notification.objects.filter(sent_at__isnull=True,attempts__lt=5).order_by("id")[:100]:
            from monitor.operations import touch_worker
            touch_worker()
            recipients=list(AlertRecipient.objects.filter(site=item.site,enabled=True).values_list("email",flat=True))
            if not recipients: continue
            item.attempts+=1
            try:
                send_mail(item.subject,item.body,None,recipients,fail_silently=False)
                item.sent_at=timezone.now();item.last_error=""
            except Exception as exc: item.last_error=type(exc).__name__
            item.save()
