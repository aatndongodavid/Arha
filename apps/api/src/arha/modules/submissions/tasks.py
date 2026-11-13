"""Submission side effects: owner notifications and respondent confirmation (F-NOT-01, F-NOT-02)."""

from __future__ import annotations

import uuid

from arha.core.features import has_feature
from arha.core.jobs import job
from arha.db.session import app_tx
from arha.modules.messaging import service as mail
from arha.settings import get_settings


@job("submissions.completed")
async def submission_completed(org_id: str, submission_id: str) -> None:
    from arha.modules.forms.models import Form, FormVersion
    from arha.modules.integrations.service import emit_event
    from arha.modules.orgs.service import get_org, owners_emails
    from arha.modules.submissions.models import Submission

    oid = uuid.UUID(org_id)
    async with app_tx(org_id=oid) as db:
        sub = await db.get(Submission, uuid.UUID(submission_id))
        if sub is None:
            return
        form = await db.get(Form, sub.form_id)
        version = await db.get(FormVersion, sub.form_version_id)
        org = await get_org(db, oid)
        assert form and version
        link = f"{get_settings().arha_app_url}/orgs/{org_id}/forms/{form.id}/responses/{sub.id}"
        for email, locale in await owners_emails(db, only_notify=True):
            subject, body = mail.render("new_response", locale, form=form.title, link=link)
            await mail.send(mail.Mail(to=email, subject=subject, text=body, template="new_response"), db=db, org_id=oid)
        settings = version.schema.get("settings") or {}
        field = settings.get("respondentEmailField")
        to = (sub.answers or {}).get(field) if field else None
        if to and has_feature(org, "respondent_emails"):
            loc = sub.locale
            message = ((settings.get("confirmationMessage") or settings.get("ending") or {}).get("message") or {})
            text_msg = message.get(loc) if isinstance(message, dict) else None
            subject, body = mail.render("confirmation", loc, form=form.title,
                                        message=text_msg or mail.render("confirmation", loc, form=form.title,
                                                                        message="")[0])
            await mail.send(mail.Mail(to=str(to), subject=subject, text=body, template="confirmation"), db=db,
                            org_id=oid)
        await emit_event(db, "submission.completed", form_id=form.id, submission=sub)


@job("submissions.scan_file")
async def scan_file(org_id: str, key: str) -> None:
    """ClamAV asynchronous scan (S-10). Without a ClamAV daemon configured the file is marked skipped."""
    import os

    from sqlalchemy import update

    from arha.modules.trust.models import StoredFile

    status = "skipped"
    host = os.environ.get("CLAMAV_HOST")
    if host:
        import asyncio

        from arha.core.storage import storage

        data = storage().get(key)
        reader, writer = await asyncio.open_connection(host, 3310)
        writer.write(b"zINSTREAM\0")
        for i in range(0, len(data), 8192):
            chunk = data[i:i + 8192]
            writer.write(len(chunk).to_bytes(4, "big") + chunk)
        writer.write((0).to_bytes(4, "big"))
        await writer.drain()
        answer = (await reader.read(4096)).decode(errors="ignore")
        writer.close()
        status = "clean" if answer.strip("\0").endswith("OK") else "infected"
        if status == "infected":
            storage().delete(key)
    async with app_tx(org_id=uuid.UUID(org_id)) as db:
        await db.execute(update(StoredFile).where(StoredFile.key == key).values(scan_status=status))
