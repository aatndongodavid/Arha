"""Invoice PDF (F-FAC-04): legal mentions and payment reference."""

from __future__ import annotations

import html
from typing import Any

from weasyprint import HTML

from arha.core.messages import t
from arha.core.money import fmt
from arha.modules.payments.documents import CSS


def render_invoice(inv: Any, org: Any, locale: str) -> bytes:
    lines = "".join(
        f'<tr><td>{html.escape(t("invoice.plan_line", locale, plan=li["plan"].capitalize(), period=t("period." + li["period"], locale)))}'
        f'</td><td style="text-align:right">{html.escape(fmt(int(li["amount"]), inv.currency, locale))}</td></tr>'
        for li in inv.lines)
    doc = (f'<html><head><meta charset="utf-8"><style>{CSS}</style></head><body><div class="brand">Arha</div>'
           f'<h1>{html.escape(t("invoice.title", locale))} {html.escape(inv.number)}</h1><table>'
           f'<tr><td class="k">{html.escape(t("invoice.issuer", locale))}</td><td>Arha</td></tr>'
           f'<tr><td class="k">{html.escape(t("invoice.billed_to", locale))}</td><td>{html.escape(org.name)}</td></tr>'
           f'<tr><td class="k">{html.escape(t("receipt.date", locale))}</td><td>{inv.issued_at:%d/%m/%Y}</td></tr>'
           f'</table><table><tr><td class="k">{html.escape(t("invoice.line", locale))}</td><td></td></tr>{lines}'
           f'<tr><td><b>{html.escape(t("invoice.total", locale))}</b></td><td style="text-align:right"><b>'
           f'{html.escape(fmt(inv.amount, inv.currency, locale))}</b></td></tr></table>'
           f'<div class="foot">{html.escape(t("invoice.paid", locale, date=f"{inv.issued_at:%d/%m/%Y}", ref=str(inv.payment_id)))}'
           f'<br>{html.escape(t("invoice.legal", locale))}</div></body></html>')
    return HTML(string=doc).write_pdf()  # type: ignore[no-any-return]
