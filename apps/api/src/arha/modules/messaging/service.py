"""Transactional e-mail (F-NOT-01, F-NOT-02). SMTP in staging and production, local outbox in dev."""

from __future__ import annotations

import asyncio
import smtplib
import uuid
from dataclasses import dataclass, field
from email.message import EmailMessage
from pathlib import Path

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from arha.core.ids import uuid7
from arha.core.messages import t
from arha.core.security import keyed_hash
from arha.modules.messaging.models import MessageLog
from arha.settings import get_settings

log = structlog.get_logger()


@dataclass
class Mail:
    to: str
    subject: str
    text: str
    template: str
    attachments: list[tuple[str, bytes, str]] = field(default_factory=list)


OUTBOX: list[Mail] = []  # dev and test only


def _send_smtp(mail: Mail) -> None:
    s = get_settings()
    msg = EmailMessage()
    msg["From"] = s.mail_from
    msg["To"] = mail.to
    msg["Subject"] = mail.subject
    msg.set_content(mail.text)
    for name, data, mime in mail.attachments:
        maintype, subtype = mime.split("/", 1)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
    assert s.smtp_host
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
        smtp.starttls()
        if s.smtp_user and s.smtp_password:
            smtp.login(s.smtp_user, s.smtp_password.get_secret_value())
        smtp.send_message(msg)


async def send(mail: Mail, *, db: AsyncSession | None = None, org_id: uuid.UUID | None = None) -> None:
    s = get_settings()
    status = "sent"
    try:
        if s.smtp_host:
            await asyncio.to_thread(_send_smtp, mail)
        else:
            OUTBOX.append(mail)
            out = Path("/tmp/arha-mail")
            out.mkdir(exist_ok=True)
            (out / f"{uuid7()}.txt").write_text(f"To: {mail.to}\nSubject: {mail.subject}\n\n{mail.text}",
                                                encoding="utf-8")
    except (OSError, smtplib.SMTPException) as exc:
        status = "failed"
        log.warning("mail_failed", template=mail.template, error_type=type(exc).__name__)
    if db is not None and org_id is not None:
        db.add(MessageLog(organization_id=org_id, channel="email", template=mail.template,
                          to_hash=keyed_hash(mail.to.lower()), status=status))


def render(template: str, locale: str, **params: object) -> tuple[str, str]:
    return t(f"mail.{template}.subject", locale, **params), t(f"mail.{template}.body", locale, **params)
