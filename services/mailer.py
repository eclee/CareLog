import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

from models import get_setting


class MailNotConfigured(Exception):
    pass


def send_mail(subject, html_body, pdf_bytes=None, pdf_name="report.pdf"):
    """Send via Gmail SMTP (App Password). Raises on failure."""
    user = (get_setting("smtp_user") or "").strip()
    password = (get_setting("smtp_password") or "").strip()
    recipients = [r.strip() for r in (get_setting("recipients") or "").split(",") if r.strip()]
    if not user or not password or not recipients:
        raise MailNotConfigured("Gmail 帳號、應用程式密碼或收件人尚未設定")

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    if pdf_bytes:
        part = MIMEApplication(pdf_bytes, _subtype="pdf")
        part.add_header("Content-Disposition", "attachment", filename=pdf_name)
        msg.attach(part)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(user, password)
        smtp.sendmail(user, recipients, msg.as_string())
