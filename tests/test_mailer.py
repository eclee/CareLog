from __future__ import annotations

import pytest

from services import mailer


def test_send_mail_normalizes_copy_pasted_gmail_app_password(monkeypatch):
    settings = {
        "smtp_user": " sender@gmail.com\u00a0",
        "smtp_password": "abcd\u00a0efgh\u202fijkl\u200bmnop",
        "recipients": " first@example.com\u00a0,\u202fsecond@example.com ",
    }
    captured = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            captured["connection"] = (host, port, timeout)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def login(self, username, password):
            username.encode("ascii")
            password.encode("ascii")
            captured["login"] = (username, password)

        def send_message(self, message, *, from_addr, to_addrs):
            captured["message"] = message
            captured["envelope"] = (from_addr, list(to_addrs))

    monkeypatch.setattr(mailer, "get_setting", settings.get)
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", FakeSMTP)

    mailer.send_mail("測試郵件", "<p>郵件內容</p>")

    assert captured["login"] == ("sender@gmail.com", "abcdefghijklmnop")
    assert captured["envelope"] == (
        "sender@gmail.com",
        ["first@example.com", "second@example.com"],
    )
    assert captured["connection"] == ("smtp.gmail.com", 465, 30)


def test_mailer_rejects_non_ascii_mailbox_with_actionable_message():
    with pytest.raises(mailer.MailConfigurationError, match="非 ASCII"):
        mailer.normalize_smtp_username("測試@gmail.com")
