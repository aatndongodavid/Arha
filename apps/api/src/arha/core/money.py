"""Money formatting per locale (NF-11): the CFA franc displays as `10 000 FCFA`."""

from __future__ import annotations

from babel.numbers import format_decimal

LABELS = {"XAF": "FCFA", "XOF": "FCFA", "NGN": "NGN", "GHS": "GHS", "KES": "KES"}


def fmt(amount: int, currency: str = "XAF", locale: str = "fr") -> str:
    number = format_decimal(amount, locale="fr_FR" if locale == "fr" else "en_US", group_separator=True)
    if locale == "fr":
        number = number.replace(" ", " ").replace("\xa0", " ")
    return f"{number} {LABELS.get(currency, currency)}"
