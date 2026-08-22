import re
import smtplib
import unicodedata
from email.header import Header
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from models import get_setting


class MailNotConfigured(Exception):
    pass


class MailConfigurationError(ValueError):
    """Raised when stored SMTP values cannot be used safely."""


def _normalize_copy_paste_text(value) -> str:
    """Normalize full-width and compatibility characters from copied text."""

    return unicodedata.normalize("NFKC", str(value or ""))


def _remove_invisible_spacing(value) -> str:
    """Remove spaces and invisible format marks commonly introduced by copy/paste.

    Google displays app passwords in grouped blocks. Copying those blocks can
    introduce U+00A0 (no-break space), U+202F (narrow no-break space), or a
    zero-width format mark. smtplib must encode SMTP authentication data as
    ASCII, so those invisible characters otherwise trigger a UnicodeEncodeError.
    """

    normalized = _normalize_copy_paste_text(value)
    return "".join(
        char
        for char in normalized
        if not char.isspace() and unicodedata.category(char) != "Cf"
    )


def _ascii_mailbox(value, *, label: str) -> str:
    address = _remove_invisible_spacing(value)
    if not address:
        return ""
    if address.count("@") != 1 or address.startswith("@") or address.endswith("@"):
        raise MailConfigurationError(f"{label}格式不正確：請只輸入完整 Email 地址")
    try:
        address.encode("ascii")
    except UnicodeEncodeError as exc:
        raise MailConfigurationError(
            f"{label}含有非 ASCII 字元；請重新貼上一般 Email 地址"
        ) from exc
    return address


def normalize_smtp_username(value) -> str:
    """Return a safe Gmail login address, removing copy/paste spacing."""

    return _ascii_mailbox(value, label="Gmail 帳號")


def normalize_smtp_password(value) -> str:
    """Return a Gmail app password without visual grouping spaces."""

    password = _remove_invisible_spacing(value)
    try:
        password.encode("ascii")
    except UnicodeEncodeError as exc:
        raise MailConfigurationError(
            "Gmail 應用程式密碼含有無法辨識的字元，請重新複製 16 碼密碼"
        ) from exc
    return password


def normalize_recipients(value) -> list[str]:
    """Parse comma/semicolon/newline-separated recipient addresses safely."""

    if isinstance(value, (list, tuple, set)):
        value = ",".join(str(item) for item in value)
    normalized = _normalize_copy_paste_text(value)
    recipients: list[str] = []
    seen: set[str] = set()
    for raw in re.split(r"[,;\n\r]+", normalized):
        address = _ascii_mailbox(raw, label="收件人")
        if not address:
            continue
        key = address.casefold()
        if key not in seen:
            recipients.append(address)
            seen.add(key)
    return recipients


def send_mail(subject, html_body, pdf_bytes=None, pdf_name="report.pdf"):
    """Send via Gmail SMTP using an app password. Raises on failure."""

    user = normalize_smtp_username(get_setting("smtp_user") or "")
    password = normalize_smtp_password(get_setting("smtp_password") or "")
    recipients = normalize_recipients(get_setting("recipients") or "")
    if not user or not password or not recipients:
        raise MailNotConfigured("Gmail 帳號、應用程式密碼或收件人尚未設定")

    msg = MIMEMultipart("mixed")
    msg["Subject"] = Header(str(subject), "utf-8")
    msg["From"] = user
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(str(html_body), "html", "utf-8"))
    if pdf_bytes:
        part = MIMEApplication(pdf_bytes, _subtype="pdf")
        part.add_header("Content-Disposition", "attachment", filename=pdf_name)
        msg.attach(part)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg, from_addr=user, to_addrs=recipients)
