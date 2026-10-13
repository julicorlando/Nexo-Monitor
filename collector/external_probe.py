"""Execute em servidor independente da matriz. Exige URL HTTPS e SMTP locais."""
import os,time,smtplib,urllib.request
from email.message import EmailMessage
from datetime import datetime,timezone

def run():
    url=os.environ["NEXO_EXTERNAL_URL"]
    if not url.startswith("https://"):raise RuntimeError("HTTPS obrigatório")
    previous=None
    while True:
        try:
            with urllib.request.urlopen(url,timeout=10) as response:healthy=response.status==200
        except Exception:healthy=False
        if healthy!=previous:
            message=EmailMessage();message["Subject"]="Nexo Monitor: "+("central disponível" if healthy else "central indisponível")
            message["From"]=os.environ["SMTP_FROM"];message["To"]=os.environ["SMTP_TO"]
            message.set_content("Estado verificado em "+datetime.now(timezone.utc).isoformat())
            try:
                with smtplib.SMTP(os.environ["SMTP_HOST"],int(os.getenv("SMTP_PORT","587")),timeout=15) as smtp:
                    smtp.starttls();smtp.login(os.environ["SMTP_USER"],os.environ["SMTP_PASSWORD"]);smtp.send_message(message)
                previous=healthy
            except Exception:pass
        time.sleep(60)
if __name__=="__main__":run()
