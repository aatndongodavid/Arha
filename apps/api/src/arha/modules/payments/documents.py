"""Receipts (F-PAY-06), tickets with QR codes (F-PAY-07) and PDF rendering (WeasyPrint, segno)."""

from __future__ import annotations

import html
import io
from typing import Any

import segno
from weasyprint import HTML

from arha.core.crypto import sign_compact
from arha.core.messages import t
from arha.core.money import fmt
from arha.settings import get_settings

CSS = """
@page { size: A5; margin: 14mm; }
body { font-family: 'Inter', 'DejaVu Sans', sans-serif; color: #2A1F17; font-size: 10pt; }
h1 { font-family: 'Cormorant Garamond', serif; font-weight: 500; font-size: 22pt; margin: 0 0 4mm; }
.brand { color: #C9621B; letter-spacing: 3px; font-size: 8pt; text-transform: uppercase; }
table { width: 100%; border-collapse: collapse; margin-top: 6mm; }
td { padding: 2.2mm 0; border-bottom: 0.3pt solid #E6D8C0; vertical-align: top; }
td.k { color: #7A6A5A; width: 42%; }
.amount { font-size: 16pt; }
.qr { text-align: center; margin-top: 8mm; }
.foot { color: #7A6A5A; font-size: 7.5pt; margin-top: 8mm; }
.ticket { page-break-after: always; }
"""


def qr_svg(data: str, scale: int = 4) -> str:
    buf = io.BytesIO()
    segno.make(data, error="m").save(buf, kind="svg", scale=scale, dark="#2A1F17", xmldecl=False, svgns=True)
    return buf.getvalue().decode()


def receipt_verify_url(payment_id: str) -> str:
    token = sign_compact({"p": payment_id, "k": "verify"})
    return f"{get_settings().arha_site_url}/recu?token={token}"


def receipt_pdf(*, locale: str, org_name: str, form_title: str, payment: Any, channel_label: str) -> bytes:
    rows = [
        (t("receipt.number", locale), payment.receipt_number or ""),
        (t("receipt.organization", locale), org_name),
        (t("receipt.form", locale), form_title),
        (t("receipt.amount", locale), fmt(payment.amount, payment.currency, locale)),
        (t("receipt.date", locale), payment.updated_at.strftime("%d/%m/%Y %H:%M UTC")),
        (t("receipt.provider_ref", locale), payment.provider_ref or ""),
        (t("receipt.channel", locale), channel_label),
    ]
    body = "".join(f'<tr><td class="k">{html.escape(k)}</td><td>{html.escape(str(v))}</td></tr>' for k, v in rows)
    doc = (f'<html><head><meta charset="utf-8"><style>{CSS}</style></head><body>'
           f'<div class="brand">Arha</div><h1>{html.escape(t("receipt.title", locale))}</h1>'
           f'<div class="amount">{html.escape(fmt(payment.amount, payment.currency, locale))}</div>'
           f'<table>{body}</table><div class="qr">{qr_svg(receipt_verify_url(str(payment.id)))}'
           f'<div>{html.escape(t("receipt.verify", locale))}</div></div>'
           f'<div class="foot">{html.escape(t("receipt.footer", locale))}</div></body></html>')
    return HTML(string=doc).write_pdf()  # type: ignore[no-any-return]


def tickets_pdf(*, locale: str, org_name: str, form_title: str, tickets: list[dict[str, Any]]) -> bytes:
    pages = []
    for tk in tickets:
        pages.append(
            f'<div class="ticket"><div class="brand">{html.escape(org_name)}</div>'
            f'<h1>{html.escape(form_title)}</h1><table>'
            f'<tr><td class="k">{html.escape(t("ticket.category", locale))}</td><td>{html.escape(tk["category"])}</td></tr>'
            f'<tr><td class="k">{html.escape(t("ticket.serial", locale))}</td><td>{tk["serial"]}</td></tr></table>'
            f'<div class="qr">{qr_svg(tk["token"], scale=6)}</div></div>')
    doc = f'<html><head><meta charset="utf-8"><style>{CSS}</style></head><body>{"".join(pages)}</body></html>'
    return HTML(string=doc).write_pdf()  # type: ignore[no-any-return]
