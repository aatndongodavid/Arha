"""The twelve launch templates (F-EDI-07). Bilingual, no emoji, plain sentences."""

from __future__ import annotations

import copy
from typing import Any


def _t(fr: str, en: str) -> dict[str, str]:
    return {"fr": fr, "en": en}


def _opt(oid: str, fr: str, en: str, code: int, **extra: Any) -> dict[str, Any]:
    return {"id": oid, "label": _t(fr, en), "code": code, **extra}


def _b(bid: str, kind: str, fr: str, en: str, required: bool = False, **extra: Any) -> dict[str, Any]:
    block: dict[str, Any] = {"id": bid, "type": kind, "label": _t(fr, en), "required": required}
    block.update(extra)
    return block


def _identity(prefix: str = "") -> list[dict[str, Any]]:
    return [
        _b(f"{prefix}full_name", "short_text", "Nom et prénom", "Full name", True, identifying=True,
           variableName="nom"),
        _b(f"{prefix}phone", "phone", "Numéro de téléphone", "Phone number", True, identifying=True,
           validation={"defaultCountry": "CM"}, variableName="telephone"),
        _b(f"{prefix}email", "email", "Adresse e-mail", "Email address", False, identifying=True,
           variableName="email"),
    ]


def _consent() -> dict[str, Any]:
    return {"id": "consent", "type": "consent", "required": True,
            "label": _t("J'accepte que mes réponses soient traitées par l'organisateur pour cette demande.",
                        "I agree that the organizer processes my answers for this request.")}


def _form(title_fr: str, title_en: str, pages: list[dict[str, Any]], *, payments: bool = False,
          variables: list[dict[str, Any]] | None = None, rules: list[dict[str, Any]] | None = None,
          ending_fr: str = "Merci, votre réponse a bien été enregistrée.",
          ending_en: str = "Thank you, your response has been recorded.") -> dict[str, Any]:
    return {
        "schemaVersion": 1, "defaultLocale": "fr", "locales": ["fr", "en"],
        "description": _t(title_fr, title_en),
        "settings": {
            "theme": {"primary": "#C9621B", "background": "#FCF9F4", "font": "system", "logoKey": None,
                      "coverKey": None},
            "closing": {"closesAt": None, "maxResponses": None,
                        "message": _t("Ce formulaire est fermé.", "This form is closed.")},
            "ending": {"message": _t(ending_fr, ending_en), "redirectUrl": None},
            "payments": {"enabled": payments, "currency": "XAF", "feeBearer": "org", "provider": "notchpay"},
            "consent": {"required": True, "textVersion": "2026-11"},
            "saveAndResume": True, "showProgress": True, "respondentEmailField": "email",
        },
        "variables": variables or [], "pages": pages, "rules": rules or [],
    }


TEMPLATES: dict[str, dict[str, Any]] = {
    "paid_event": {
        "category": "events",
        "title": _t("Inscription payante à un événement", "Paid event registration"),
        "description": _t("Billets par catégorie, quotas et code QR.", "Tickets by category, quotas and QR code."),
        "schema": _form("Inscription à l'événement", "Event registration", [
            {"id": "p1", "title": _t("Vos informations", "Your details"), "blocks": _identity()},
            {"id": "p2", "title": _t("Vos billets", "Your tickets"), "blocks": [
                _b("tickets", "ticket_choice", "Choisissez vos billets", "Choose your tickets", True, options=[
                    _opt("standard", "Standard", "Standard", 1, price=5000, quota=150, maxQuantity=5),
                    _opt("vip", "VIP", "VIP", 2, price=15000, quota=30, maxQuantity=2),
                ]),
                _consent(),
            ]},
        ], payments=True, ending_fr="Merci. Vos billets vous sont envoyés par e-mail.",
            ending_en="Thank you. Your tickets are sent by email."),
    },
    "school_preregistration": {
        "category": "schools",
        "title": _t("Préinscription scolaire", "School pre-registration"),
        "description": _t("Dossier de l'élève, frais de dossier et pièces jointes.",
                          "Student file, application fee and attachments."),
        "schema": _form("Préinscription", "Pre-registration", [
            {"id": "p1", "title": _t("L'élève", "The student"), "blocks": [
                _b("student_name", "short_text", "Nom et prénom de l'élève", "Student full name", True,
                   identifying=True),
                _b("birth_date", "date", "Date de naissance", "Date of birth", True, identifying=True),
                _b("level", "dropdown", "Classe demandée", "Requested class", True, options=[
                    _opt("sil", "SIL", "SIL", 1), _opt("cp", "CP", "CP", 2), _opt("ce1", "CE1", "CE1", 3),
                    _opt("ce2", "CE2", "CE2", 4), _opt("cm1", "CM1", "CM1", 5), _opt("cm2", "CM2", "CM2", 6),
                    _opt("sixieme", "Sixième", "Form 1", 7)]),
                _b("report", "file_upload", "Dernier bulletin", "Latest school report", False,
                   validation={"maxFiles": 2, "accept": ["pdf", "image"]}),
            ]},
            {"id": "p2", "title": _t("Le parent ou tuteur", "Parent or guardian"), "blocks": [
                *_identity("parent_"),
                _b("fee", "payment_fixed", "Frais de dossier", "Application fee", amount=10000),
                _consent(),
            ]},
        ], payments=True),
    },
    "membership": {
        "category": "associations",
        "title": _t("Adhésion à une association", "Association membership"),
        "description": _t("Cotisation annuelle par catégorie de membre.", "Yearly fee by member category."),
        "schema": _form("Adhésion", "Membership", [
            {"id": "p1", "blocks": [
                *_identity(),
                _b("category", "single_choice", "Catégorie de membre", "Member category", True, options=[
                    _opt("student", "Étudiant", "Student", 1), _opt("active", "Membre actif", "Active member", 2),
                    _opt("benefactor", "Membre bienfaiteur", "Benefactor", 3)]),
                _b("pay", "payment_computed", "Cotisation", "Membership fee", variable="fee"),
                _consent(),
            ]},
        ], payments=True, variables=[{"id": "fee", "type": "number", "formula": {"op": "if", "args": [
            {"op": "eq", "args": [{"ref": "category"}, {"str": "student"}]}, {"num": 5000},
            {"op": "if", "args": [{"op": "eq", "args": [{"ref": "category"}, {"str": "active"}]}, {"num": 15000},
                                  {"num": 50000}]}]}}]),
    },
    "order": {
        "category": "commerce",
        "title": _t("Bon de commande", "Order form"),
        "description": _t("Produits, quantités et paiement Mobile Money.", "Products, quantities and Mobile Money."),
        "schema": _form("Commande", "Order", [
            {"id": "p1", "blocks": [
                _b("products", "product_choice", "Vos articles", "Your items", True, options=[
                    _opt("item_a", "Article A", "Item A", 1, price=2500, maxQuantity=10),
                    _opt("item_b", "Article B", "Item B", 2, price=7500, maxQuantity=10)]),
                _b("delivery", "yes_no", "Souhaitez-vous une livraison ?", "Do you want delivery?", True),
                _b("address", "long_text", "Adresse de livraison", "Delivery address", False),
                _b("delivery_fee", "payment_fixed", "Frais de livraison", "Delivery fee", amount=1500),
                *_identity(),
                _consent(),
            ]},
        ], payments=True, rules=[{"id": "r_delivery", "when": {"field": "delivery", "op": "eq", "value": True},
                                  "then": [{"action": "show", "target": "address"},
                                           {"action": "require", "target": "address"},
                                           {"action": "show", "target": "delivery_fee"}]}]),
    },
    "satisfaction": {
        "category": "feedback",
        "title": _t("Enquête de satisfaction", "Satisfaction survey"),
        "description": _t("Note, NPS et commentaires.", "Rating, NPS and comments."),
        "schema": _form("Votre avis", "Your feedback", [
            {"id": "p1", "blocks": [
                _b("rating", "rating", "Quelle note donnez-vous à notre service ?", "How do you rate our service?",
                   True, scale={"max": 5}),
                _b("nps", "nps", "Recommanderiez-vous nos services à un proche ?",
                   "Would you recommend our services to a friend?", True),
                _b("why_low", "long_text", "Que devons-nous améliorer ?", "What should we improve?"),
                _b("comment", "long_text", "Un dernier mot ?", "Any final words?"),
            ]},
        ], rules=[{"id": "r_low", "when": {"field": "rating", "op": "lte", "value": 3},
                   "then": [{"action": "show", "target": "why_low"}]}]),
    },
    "job_application": {
        "category": "hr",
        "title": _t("Candidature", "Job application"),
        "description": _t("CV, lettre de motivation et disponibilité.", "Resume, cover letter and availability."),
        "schema": _form("Candidature", "Application", [
            {"id": "p1", "blocks": [
                *_identity(),
                _b("position", "dropdown", "Poste visé", "Position", True, options=[
                    _opt("dev", "Développeur", "Developer", 1), _opt("sales", "Commercial", "Sales", 2),
                    _opt("admin", "Assistant administratif", "Administrative assistant", 3)]),
                _b("cv", "file_upload", "Votre CV", "Your resume", True, validation={"maxFiles": 1, "accept": ["pdf"]}),
                _b("motivation", "long_text", "Pourquoi ce poste ?", "Why this position?", True,
                   validation={"maxLength": 3000}),
                _b("start", "date", "Date de disponibilité", "Available from", True),
                _consent(),
            ]},
        ]),
    },
    "paid_training": {
        "category": "training",
        "title": _t("Inscription à une formation", "Training registration"),
        "description": _t("Tarif dégressif selon le nombre de participants.", "Volume pricing per participant."),
        "schema": _form("Inscription à la formation", "Training registration", [
            {"id": "p1", "blocks": [
                *_identity(),
                _b("company", "short_text", "Entreprise", "Company"),
                _b("participants", "number", "Nombre de participants", "Number of participants", True,
                   validation={"min": 1, "max": 50, "integer": True}),
                _b("total_display", "computed_display", "Montant total", "Total amount", variable="total"),
                _b("pay", "payment_computed", "Paiement", "Payment", variable="total"),
                _consent(),
            ]},
        ], payments=True, variables=[{"id": "total", "type": "number", "formula": {"op": "if", "args": [
            {"op": "gte", "args": [{"ref": "participants"}, {"num": 10}]},
            {"op": "mul", "args": [{"ref": "participants"}, {"num": 4500}]},
            {"op": "mul", "args": [{"ref": "participants"}, {"num": 5000}]}]}}]),
    },
    "poll": {
        "category": "feedback",
        "title": _t("Sondage rapide", "Quick poll"),
        "description": _t("Une question à choix et un commentaire.", "One choice question and a comment."),
        "schema": _form("Sondage", "Poll", [
            {"id": "p1", "blocks": [
                _b("choice", "single_choice", "Quelle option préférez-vous ?", "Which option do you prefer?", True,
                   options=[_opt("a", "Option A", "Option A", 1), _opt("b", "Option B", "Option B", 2),
                            _opt("c", "Option C", "Option C", 3)]),
                _b("comment", "long_text", "Commentaire", "Comment"),
            ]},
        ]),
    },
    "contact": {
        "category": "general",
        "title": _t("Formulaire de contact", "Contact form"),
        "description": _t("Nom, coordonnées et message.", "Name, contact details and message."),
        "schema": _form("Contact", "Contact", [
            {"id": "p1", "blocks": [
                *_identity(),
                _b("subject", "short_text", "Objet", "Subject", True),
                _b("message", "long_text", "Votre message", "Your message", True, validation={"maxLength": 3000}),
                _consent(),
            ]},
        ]),
    },
    "booking": {
        "category": "services",
        "title": _t("Réservation", "Booking"),
        "description": _t("Date, créneau horaire et acompte.", "Date, time slot and deposit."),
        "schema": _form("Réservation", "Booking", [
            {"id": "p1", "blocks": [
                *_identity(),
                _b("date", "date", "Date souhaitée", "Preferred date", True),
                _b("time", "time", "Heure souhaitée", "Preferred time", True),
                _b("people", "number", "Nombre de personnes", "Number of people", True,
                   validation={"min": 1, "max": 20, "integer": True}),
                _b("deposit", "payment_fixed", "Acompte", "Deposit", amount=5000),
                _consent(),
            ]},
        ], payments=True),
    },
    "donation": {
        "category": "associations",
        "title": _t("Collecte de dons", "Donation drive"),
        "description": _t("Montant libre avec minimum.", "Open amount with a minimum."),
        "schema": _form("Faire un don", "Make a donation", [
            {"id": "p1", "blocks": [
                _b("amount", "payment_open", "Montant de votre don", "Your donation amount", True,
                   minAmount=500, maxAmount=5000000),
                _b("anonymous", "yes_no", "Souhaitez-vous rester anonyme ?", "Do you want to stay anonymous?", True),
                *_identity(),
                _consent(),
            ]},
        ], payments=True),
    },
    "field_survey": {
        "category": "research",
        "title": _t("Enquête de terrain", "Field survey"),
        "description": _t("Questionnaire structuré prêt pour SPSS et Stata.",
                          "Structured questionnaire ready for SPSS and Stata."),
        "schema": _form("Enquête ménage", "Household survey", [
            {"id": "p1", "title": _t("Ménage", "Household"), "blocks": [
                _b("region", "dropdown", "Région", "Region", True, variableName="region", options=[
                    _opt("littoral", "Littoral", "Littoral", 1), _opt("centre", "Centre", "Centre", 2),
                    _opt("ouest", "Ouest", "West", 3), _opt("nord", "Nord", "North", 4)]),
                _b("size", "number", "Taille du ménage", "Household size", True, variableName="taille",
                   validation={"min": 1, "max": 40, "integer": True}),
                _b("water", "single_choice", "Source principale d'eau", "Main water source", True,
                   variableName="eau", options=[
                       _opt("tap", "Robinet", "Tap", 1), _opt("well", "Puits", "Well", 2),
                       _opt("river", "Rivière", "River", 3), _opt("other", "Autre", "Other", 9)]),
                _b("income", "linear_scale", "Satisfaction vis-à-vis du revenu", "Income satisfaction", True,
                   variableName="revenu", scale={"min": 1, "max": 5}),
            ]},
        ]),
    },
}


def list_templates() -> list[dict[str, Any]]:
    return [{"code": code, **{k: v for k, v in tpl.items() if k != "schema"}, "schema": tpl["schema"]}
            for code, tpl in TEMPLATES.items()]


def template_schema(code: str) -> dict[str, Any] | None:
    tpl = TEMPLATES.get(code)
    return copy.deepcopy(tpl["schema"]) if tpl else None
