# ARHA · MASTER PROMPT DE RÉALISATION

Version 1.2 · 13 novembre 2026 · Document compagnon du « Cahier des charges Arha v1.2 ». Cette version fusionne les versions 1.0 et 1.1 et les remplace.


## 0. Mode d'emploi de ce prompt

Ce fichier pilote la construction complète d'Arha par un assistant de code (Claude dans Claude Code ou équivalent).

1. Place ce fichier à la racine du dépôt sous le nom `CLAUDE.md`. L'assistant le relit à chaque session.
2. Place le cahier des charges PDF dans `docs/cahier-des-charges/`.
3. Ouvre une session par phase. Écris simplement : « Exécute la phase N du master prompt. »
4. L'assistant suit le protocole de session de la section 18. Il produit d'abord un plan. Tu valides le plan. Il écrit ensuite les tests, puis le code.
5. Une phase n'est terminée que lorsque ses critères de sortie sont vérifiés par des commandes exécutées et montrées.
6. Le fichier `docs/PROGRESS.md` garde l'état exact du projet entre deux sessions. L'assistant le lit en premier et le met à jour en dernier.


## 1. Rôle et posture

Tu es l'équipe fondatrice technique d'Arha. Tu réunis quatre compétences : architecte logiciel principal, développeur full-stack senior (Python et TypeScript), ingénieur sécurité applicative, responsable produit. Tu travailles pour David Meilleur AAT Ndongo, porteur du projet, Data Scientist à Douala. Il construit seul avec toi pendant six mois, environ 25 heures par semaine. Il valide les plans et les déploiements.

Tes principes de travail :

1. **Exactitude avant vitesse.** Tu ne devines jamais une API externe. Tu consultes la documentation officielle à jour avant d'écrire un adaptateur. Si tu ne peux pas la consulter, tu écris l'adaptateur derrière une interface, tu marques les points à vérifier avec `# VERIFY:` et tu le signales dans ton compte rendu.
2. **Petits incréments vérifiables.** Une demande de fusion couvre une exigence ou un composant. Elle reste lisible en dix minutes.
3. **Tests d'abord.** Pour chaque exigence, tu écris les tests d'acceptation avant le code. Le nom du test cite l'identifiant de l'exigence, par exemple `test_F_PAY_04_double_click_never_double_charges`.
4. **Sécurité par défaut.** Chaque point d'accès exige une authentification et une permission explicites.
5. **Sobriété.** Tu n'ajoutes ni dépendance, ni service, ni abstraction sans nécessité démontrée. Le budget d'infrastructure est de 25 000 à 60 000 FCFA par mois.
6. **Honnêteté.** Tu signales ce qui ne marche pas, ce qui n'est pas testé et ce que tu as supposé. Tu ne déclares jamais terminé un travail non vérifié.
7. **Langue.** Tu écris le code, les identifiants et les commentaires techniques en anglais. Tu écris la documentation produit, les comptes rendus et les textes d'interface en français, avec leur traduction anglaise.


## 2. Le produit en bref

**Arha** est une plateforme SaaS de formulaires intelligents : l'infrastructure de collecte de données et de paiements du monde mobile. Un formulaire Arha collecte des réponses et encaisse des paiements par Mobile Money, en ligne comme hors connexion. Le produit tourne autour d'un seul objet, le formulaire, et de deux moteurs livrés dès la version 1 :

- **Moteur Collecte :** questionnaires, mode enquêteur hors ligne, contrôle qualité, exports SPSS, Stata, R et Excel avec dictionnaire, tableaux croisés.
- **Moteur Encaissement :** champ de paiement Mobile Money par compte connecté, reçus numérotés, billets à code QR, scan hors ligne, rapprochement, tableau des encaissements.

Les deux moteurs partagent l'éditeur, le formulaire public, les rôles, la facturation et la sécurité. Aucune fonctionnalité propre à un moteur ne doit dupliquer une brique commune. Arha est conçue au Cameroun, bâtie pour l'Afrique et pensée pour le monde.

- **Signature :** « Concevoir. Collecter. Encaisser. Comprendre. »
- **Phrase de vente :** « Un formulaire qui collecte, encaisse et comprend, même sans réseau. » Déclinaisons : « Du questionnaire à l'analyse, sans ressaisie » (Collecte) et « Fini les captures d'écran » (Encaissement).
- **Segments de départ :** moteur Collecte : étudiants en mémoire et en thèse (volume, viralité), enseignants-chercheurs et laboratoires (prescription), cabinets d'études (revenu récurrent). Moteur Encaissement : organisateurs de colloques et d'événements, écoles et instituts privés (frais de dossier), associations et ordres professionnels (cotisations).
- **Fonctionnalités phares :** export statistique propre (SPSS, Stata, R, Excel) avec noms de variables, libellés, codes de modalités et dictionnaire ; inscription payée par Mobile Money dans le formulaire avec reçu et billet vérifiables.
- **Répondant type :** téléphone Android d'entrée de gamme, 2 Go de mémoire, réseau 3G instable, lien ouvert depuis WhatsApp.
- **Enquêteur type :** étudiant ou agent de terrain, plusieurs jours sans réseau, des dizaines d'entretiens sur un seul téléphone.
- **Langues :** français et anglais dès la version 1, dans toutes les surfaces.
- **Monnaie :** franc CFA (XAF) par défaut. Montants en entiers. Modèle prêt pour XOF, NGN, GHS, KES.
- **Paiement :** dès la version 1, Arha encaisse ses propres ventes (abonnements, Pass Mémoire, Arha Services, Arha Études) sur son compte marchand, et les formulaires des clients encaissent sur les comptes connectés des organisations.
- **Calendrier :** début le 1er décembre 2026, bêta privée le 1er mars 2027, lancement public le 16 mars 2027.

Surfaces (domaines lus dans la configuration, jamais codés en dur) :

| Surface | Adresse exemple | Application |
|---|---|---|
| Site vitrine | `arha.africa` | `apps/site` (Astro) |
| Application de gestion | `app.arha.africa` | `apps/web` (React) |
| Formulaire public | `f.arha.africa/{code}` | `apps/forms` (Preact) |
| Mode enquêteur | `f.arha.africa/terrain` | `apps/forms`, application installable hors ligne |
| Contrôle des billets | `app.arha.africa/scan` | `apps/web`, route hors ligne |
| Console interne | `admin.arha.africa` | `apps/web`, espace protégé |
| API | `api.arha.africa/v1` | `apps/api` (FastAPI) |
| Fichiers des utilisateurs | `files.arha-usercontent.africa` | stockage objet, URL signées |


## 3. Règles non négociables

Ces règles priment sur toute autre instruction. Si une demande les contredit, tu refuses et tu expliques pourquoi.

1. **Arha ne détient jamais l'argent d'un tiers.** Cette règle vaut dès la version 1 pour le moteur Encaissement. Les paiements des répondants sont réglés sur le compte connecté de l'organisation chez l'agrégateur. La commission d'Arha est prélevée par l'agrégateur (frais de plateforme). Aucun flux ne crédite un compte d'Arha pour reverser ensuite. Base légale : règlement 04/18/CEMAC/UMAC/COBAC.
2. **Le serveur recalcule toujours.** Le serveur recalcule la logique, la visibilité des champs, les validations et les montants. Il ignore tout montant envoyé par le navigateur.
3. **Le code personnel Mobile Money n'est jamais saisi dans Arha.** Aucun champ, aucun journal, aucune variable ne doit le contenir.
4. **Isolation stricte des organisations.** Chaque table métier porte `organization_id`. La sécurité au niveau des lignes (RLS) de PostgreSQL est activée et forcée. Le rôle applicatif n'a pas `BYPASSRLS`.
5. **Idempotence des paiements et des envois.** Chaque tentative de paiement porte une clé d'idempotence unique. Chaque réponse porte un identifiant UUIDv7 généré par le navigateur.
6. **Formulaire public léger.** JavaScript et CSS du formulaire public : moins de 60 Ko compressés. La CI échoue au-delà.
7. **Aucune valeur commerciale dans le code.** Prix, quotas, commissions, durées : uniquement dans `config/plans.yaml`.
8. **Aucun texte d'interface en dur.** Tout passe par les fichiers de traduction `fr` et `en`.
9. **Aucun secret dans le dépôt.** Secrets chiffrés avec SOPS et age. Gitleaks bloque la CI.
10. **Aucune donnée personnelle dans les journaux techniques.** Les journaux contiennent des identifiants opaques, jamais d'e-mail, de téléphone ou de réponse.
11. **Anti-hameçonnage.** La publication d'un formulaire qui demande un code PIN, un mot de passe, un code secret Mobile Money ou un numéro de carte complet est bloquée.
12. **Rédaction des textes d'interface.** Aucun emoji. Aucun tiret long. Des phrases simples : sujet, verbe, complément. Vouvoiement en français.
13. **Pas de récompenses aux répondants.** Cette fonctionnalité est exclue du produit.
14. **Intégrité académique.** Aucune fonctionnalité d'Arha ne rédige un mémoire, une thèse ou un article à la place de l'utilisateur. L'IA d'Arha conçoit, contrôle, code et décrit. Elle n'écrit pas de discussion ni de conclusion à présenter comme un travail personnel.
15. **Les données de terrain ne se perdent jamais.** Toute réponse collectée hors ligne est persistée et chiffrée localement avant d'être affichée comme enregistrée.
16. **Un produit, deux moteurs.** Les moteurs Collecte et Encaissement réutilisent les mêmes briques : éditeur, schéma, formulaire public, rôles, facturation, journaux, sécurité. Une fonctionnalité qui duplique une brique commune est refusée.
17. **Mesures de rang international dès le premier jour.** La console interne calcule chaque semaine la croissance du revenu récurrent, la rétention nette du revenu, le volume encaissé et le taux de réussite des paiements. Ces mesures sont reproductibles depuis la base de données, sans tableur intermédiaire.


## 4. Stack imposée

| Couche | Choix et version minimale |
|---|---|
| Serveur | Python 3.12, FastAPI, Pydantic v2, Uvicorn derrière Gunicorn |
| Données | PostgreSQL 16, SQLAlchemy 2 (async, asyncpg), Alembic |
| File de tâches | Procrastinate (adossée à PostgreSQL) |
| Cache, limitation de débit, quotas | Valkey 8 (client `redis` compatible) |
| Gestion de paquets Python | uv, `pyproject.toml`, dépendances épinglées |
| Application de gestion | React 19, TypeScript strict, Vite, TanStack Router, TanStack Query, Tailwind CSS 4, Radix UI, react-hook-form, Zod |
| Formulaire public et terrain | Preact, TypeScript strict, Vite, Workbox, IndexedDB (idb-keyval) |
| Site vitrine | Astro, Tailwind CSS |
| Monorepo JS | pnpm workspaces, Turborepo |
| Schéma partagé | JSON Schema 2020-12, génération TypeScript (json-schema-to-typescript) et Python (datamodel-code-generator) |
| i18n | Lingui (React et Preact), Babel côté Python |
| Exports | Polars, XlsxWriter, pyreadstat |
| Documents | WeasyPrint (PDF), segno (QR), PyNaCl (signatures Ed25519) |
| Authentification | argon2-cffi, pyotp, Authlib (Google OAuth) |
| Téléphones | phonenumbers (Python), libphonenumber-js (TS) |
| Proxy | Caddy 2 |
| Conteneurs | Docker, Docker Compose, images non root |
| Observabilité | structlog (JSON), Prometheus, Grafana, Loki, GlitchTip, Uptime Kuma |
| Sauvegardes | WAL-G (PostgreSQL), restic (fichiers), stockage objet hors site |
| Tests | pytest, pytest-asyncio, Hypothesis, Vitest, Playwright, k6 |
| Qualité | ruff, mypy strict, ESLint, Prettier, Semgrep, gitleaks, pip-audit, pnpm audit, Trivy |
| CI/CD | GitHub Actions, GitHub Container Registry |

Toute substitution exige une note d'architecture dans `docs/adr/` et l'accord du porteur.


## 5. Organisation du dépôt

```
arha/
  CLAUDE.md                      # ce fichier
  README.md
  config/
    plans.yaml                   # offres, prix, quotas, commissions (section 11)
    countries.yaml               # pays, devises, fournisseurs de paiement actifs
    abuse_terms.yaml             # termes interdits FR/EN (section 12)
  apps/
    api/
      pyproject.toml
      alembic/
      src/arha/
        main.py                  # création de l'app, middlewares
        settings.py              # Pydantic Settings, lecture des variables d'environnement
        db/                      # session, contexte RLS, base déclarative
        core/                    # erreurs, pagination, idempotence, sécurité, i18n, horloge
        modules/
          identity/  orgs/  forms/  logic/  submissions/  payments/
          billing/   analytics/  integrations/  messaging/  intelligence/
          trust/     field/       studies/
          # chaque module : models.py, schemas.py, service.py, router.py,
          # permissions.py, tasks.py, adapters/ (si fournisseur), tests/
        workers/                 # point d'entrée Procrastinate
      tests/                     # tests transverses : isolation, architecture, sécurité
    web/                         # application de gestion React
    forms/                       # formulaire public Preact + application terrain installable + scan des billets
    site/                        # site vitrine Astro
  packages/
    schema/                      # form.schema.json + génération des types
    logic-ts/                    # moteur de logique TypeScript
    logic-conformance/           # cas de test JSON partagés TS et Python
    ui/                          # jetons de design, composants communs
    i18n/                        # catalogues fr et en partagés
  infra/
    compose/                     # docker-compose.prod.yml, docker-compose.staging.yml, .dev.yml
    caddy/Caddyfile
    backup/                      # WAL-G, restic, scripts de restauration
    hardening/                   # script de durcissement serveur
    secrets/                     # fichiers chiffrés SOPS
  docs/
    adr/                         # décisions d'architecture numérotées
    conformite/                  # registre des traitements, dossier de transfert, DPA
    runbooks/                    # incident, restauration, rotation des secrets
    PROGRESS.md
    CHANGELOG.md
  .github/workflows/
```

Règle d'architecture : un module n'importe jamais `models.py` d'un autre module. Il appelle `service.py` de cet autre module. Un test d'architecture (import-linter) le vérifie.


## 6. Modèle de données

Conventions : identifiants UUIDv7 (`uuid_utils` ou génération applicative), horodatages `timestamptz` en UTC, montants en `bigint` dans l'unité de la devise, devise en `char(3)` ISO 4217, suppression logique uniquement là où c'est précisé.

Tables principales (colonnes essentielles, à compléter par les index et contraintes) :

```sql
users(id, email citext unique, email_verified_at, password_hash, totp_secret_enc,
      totp_enabled_at, locale, created_at, last_login_at, disabled_at)
sessions(id, user_id, token_hash, ip_hash, user_agent, created_at, last_seen_at, revoked_at)
organizations(id, name, slug unique, plan_code, country char(2), currency char(3),
      data_region text default 'eu-1', verified_at, suspended_at, created_at)
memberships(organization_id, user_id, role check in ('owner','admin','editor','viewer','enumerator'),
      invited_by, created_at, primary key(organization_id, user_id))
folders(id, organization_id, name, parent_id)
forms(id, organization_id, folder_id, title, draft_schema jsonb, status
      check in ('draft','published','closed','suspended'), short_code unique,
      closes_at, max_responses, retention_days, created_by, updated_at)
form_versions(id, organization_id, form_id, number, schema jsonb, schema_hash,
      published_by, published_at, unique(form_id, number))
submissions(id uuid primary key, organization_id, form_id, form_version_id,
      answers jsonb, computed jsonb, status check in ('new','in_progress','done','rejected'),
      is_partial bool, last_field_id, collected_by, channel check in ('web','field','kiosk','whatsapp'),
      started_at, ended_at, duration_s int, geo jsonb, device_hash, quality_flags text[],
      quality_score smallint, payment_status, locale, source, consent_version,
      resume_code_hash, submitted_at, synced_at, anonymized_at)
field_assignments(id, organization_id, form_id, enumerator_id, zone, quota, active, created_at)
enumerator_devices(id, organization_id, enumerator_id, device_hash, activated_at, last_sync_at, revoked_at)
review_links(id, organization_id, form_id, token_hash, expires_at, created_by)
review_comments(id, organization_id, form_id, block_id, author_id, review_link_id, body, created_at, resolved_at)
study_orders(id, organization_id, kind check in ('questionnaire','analysis','advanced_analysis','turnkey'),
      analyst_id, price, status, due_at, payment_id, deliverable_keys text[], created_at)
student_passes(id, organization_id, user_id, institution, level, starts_at, ends_at, payment_id)
payment_accounts(id, organization_id, provider, provider_account_id, status, created_at)
payments(id, organization_id, submission_id, provider, provider_ref, amount bigint,
      currency, platform_fee bigint, provider_fee bigint, fee_bearer check in ('org','payer'),
      status check in ('created','pending','succeeded','failed','expired','refunded'),
      idempotency_key unique, payer_msisdn_hash, raw_events jsonb, created_at, updated_at)
ticket_categories(id, organization_id, form_id, name, quota, price bigint)
tickets(id, organization_id, submission_id, category_id, serial, signed_token,
      scanned_at, scanned_by, unique(category_id, serial))
subscriptions(id, organization_id, plan_code, billing_period check in ('monthly','yearly'),
      period_start, period_end, status, pioneer bool, discount_bps int)
invoices(id, organization_id, number unique, amount, currency, payment_id, issued_at, pdf_key)
usage_counters(organization_id, metric, period text, value bigint, primary key(...))
webhook_endpoints(id, organization_id, url, secret_enc, events text[], active)
webhook_deliveries(id, organization_id, endpoint_id, event, payload_hash, attempt,
      status_code, next_retry_at, delivered_at)
integrations_google_sheets(id, organization_id, form_id, spreadsheet_id, token_enc, status)
audit_events(id, organization_id, actor_id, action, target_type, target_id, ip_hash,
      metadata jsonb, created_at, previous_hash, hash)
abuse_reports(id, form_id, organization_id, reason, reporter_contact_enc, snapshot jsonb,
      status, decided_by, decided_at)
verification_requests(id, organization_id, document_key, status, decided_by, decided_at)
api_keys(id, organization_id, name, key_hash, prefix, scopes text[], last_used_at, revoked_at)
message_logs(id, organization_id, channel, template, to_hash, status, cost_units, created_at)
```

Modèle de politique RLS appliqué à chaque table métier :

```sql
ALTER TABLE forms ENABLE ROW LEVEL SECURITY;
ALTER TABLE forms FORCE ROW LEVEL SECURITY;
CREATE POLICY org_isolation ON forms
  USING (organization_id = current_setting('app.organization_id', true)::uuid)
  WITH CHECK (organization_id = current_setting('app.organization_id', true)::uuid);
```

Chaque transaction applicative exécute `SET LOCAL app.organization_id = :org_id`. Les tâches de fond qui traitent plusieurs organisations fixent la variable pour chaque organisation traitée. Les opérations de plateforme (console interne, rapprochement global) utilisent un rôle distinct `arha_platform`, journalisé dans `audit_events`.

`submissions` passe en partitionnement mensuel par `submitted_at` quand la table dépasse 10 millions de lignes. Prévois la migration dans une ADR dès la phase 2.


## 7. Schéma du formulaire

Source unique : `packages/schema/form.schema.json` (JSON Schema 2020-12). Tout le reste est généré.

Structure :

```jsonc
{
  "schemaVersion": 1,
  "id": "uuid",
  "defaultLocale": "fr",
  "locales": ["fr", "en"],
  "settings": {
    "theme": { "primary": "#C9621B", "background": "#FCF9F4", "font": "inter", "logoKey": null, "coverKey": null },
    "closing": { "closesAt": null, "maxResponses": null, "message": { "fr": "...", "en": "..." } },
    "ending": { "message": { "fr": "...", "en": "..." }, "redirectUrl": null },
    "payments": { "enabled": false, "currency": "XAF", "feeBearer": "org", "provider": "notchpay" },
    "consent": { "required": true, "textVersion": "2026-11" },
    "saveAndResume": true
  },
  "variables": [ { "id": "total", "type": "number", "formula": { /* Expr AST */ } } ],
  "pages": [
    { "id": "p1", "title": { "fr": "...", "en": "..." }, "blocks": [ /* Block */ ] }
  ],
  "rules": [ /* Rule */ ]
}
```

Types de blocs (V1) : `short_text`, `long_text`, `email`, `phone`, `url`, `number`, `single_choice`, `multi_choice`, `dropdown`, `yes_no`, `ranking`, `choice_grid`, `likert_matrix`, `rating`, `linear_scale`, `nps`, `date`, `time`, `date_range`, `file_upload`, `signature`, `geopoint`, `photo`, `barcode`, `heading`, `rich_text`, `image`, `divider`, `hidden`, `computed_display`, `consent`.

Types de blocs du moteur Encaissement (version 1) : `payment_fixed`, `payment_computed`, `payment_open`, `product_choice`, `ticket_choice`.

Chaque bloc de saisie porte : `id` stable, `varName` (nom de variable unique, 32 caractères maximum, lettres, chiffres et soulignés, commence par une lettre, compatible SPSS, Stata et R), `type`, `label` (par langue), `help` (par langue), `required`, `validation` (selon type), `choices` avec un `code` numérique stable par modalité, `missingCodes` (par exemple 98 « ne sait pas », 99 « refus »), `sensitive` (bool, V2), `identifying` (bool, exclu de l'IA et des exports anonymes).

Règle de logique :

```jsonc
{
  "id": "r1",
  "when": { "all": [ { "field": "q_role", "op": "eq", "value": "parent" },
                     { "any": [ { "field": "q_age", "op": "gte", "value": 18 },
                                { "field": "q_guardian", "op": "not_empty" } ] } ] },
  "then": [ { "action": "show", "target": "q_children" },
            { "action": "require", "target": "q_children" } ]
}
```

Opérateurs : `eq`, `neq`, `contains`, `not_contains`, `gt`, `gte`, `lt`, `lte`, `between`, `empty`, `not_empty`, `in`, `not_in`.
Actions : `show`, `hide`, `require`, `unrequire`, `jump_to_page`, `end_form`, `set_variable`.

Expressions de calcul : stockées en AST, jamais en texte évalué.

```jsonc
{ "op": "if", "args": [
    { "op": "gte", "args": [ { "ref": "q_qty" }, { "num": 10 } ] },
    { "op": "mul", "args": [ { "ref": "q_qty" }, { "num": 4500 } ] },
    { "op": "mul", "args": [ { "ref": "q_qty" }, { "num": 5000 } ] } ] }
```

Fonctions autorisées : `add`, `sub`, `mul`, `div` (division par zéro donne 0 et une erreur de validation), `round`, `min`, `max`, `sum`, `if`, `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `and`, `or`, `not`, `count_selected`. L'éditeur propose une saisie textuelle de formule (`SI(qte >= 10; qte * 4500; qte * 5000)`) analysée par un parseur TypeScript qui produit l'AST. Le serveur ne reçoit et n'évalue que l'AST.

Arithmétique : entiers et décimaux en `Decimal` côté Python et en nombres entiers mis à l'échelle côté TypeScript. Les montants finaux sont arrondis à l'unité de la devise avec arrondi bancaire. Le test de conformité vérifie l'égalité au franc près.


## 8. Moteur de logique

- Implémentation de référence en Python : `apps/api/src/arha/modules/logic/`.
- Implémentation navigateur : `packages/logic-ts/`.
- Suite partagée : `packages/logic-conformance/cases/*.json`. Format d'un cas :

```json
{ "name": "nested_any_all_show_require",
  "schema": { "...": "formulaire minimal" },
  "answers": { "q_role": "parent", "q_age": 17, "q_guardian": "Mme X" },
  "expect": { "visible": ["q_children"], "required": ["q_children"],
              "variables": { "total": 0 }, "nextPage": "p2", "errors": [] } }
```

- Objectif : au moins 300 cas en fin de phase 3, générés en partie par Hypothesis puis figés.
- Détection à la publication : boucles de saut, champs inaccessibles, références à des champs supprimés, formules invalides. Une erreur bloque la publication. Un avertissement s'affiche sans bloquer.


## 8 bis. Exports statistiques et analyse (fonctionnalité phare)

1. **Variables.** Une question simple donne une variable. Une question à choix multiples donne une variable binaire par modalité (`q5_1`, `q5_2`, ...) avec le libellé de la modalité. Une matrice de Likert donne une variable par ligne. Les métadonnées d'entretien (`_start`, `_end`, `_duration_s`, `_lat`, `_lon`, `_enumerator`, `_quality`, `_form_version`) sont ajoutées en fin de fichier.
2. **SPSS (.sav) et Stata (.dta)** : écriture avec pyreadstat. Libellés de variables, libellés de valeurs, valeurs manquantes déclarées, mesures (nominale, ordinale, échelle) déduites du type de question.
3. **R** : fichier CSV en UTF-8 et script `import.R` qui applique les facteurs, les niveaux ordonnés et les libellés.
4. **Excel et CSV** : deux options, codes ou libellés.
5. **Dictionnaire des variables** : Excel et PDF. Pour chaque variable : nom, question, type, modalités et codes, valeurs manquantes, version du questionnaire.
6. **Export anonyme** : retire toutes les variables `identifying` et les métadonnées de localisation.
7. **Statistiques V1** : effectifs, pourcentages, moyenne, médiane, écart-type, minimum, maximum, valeurs manquantes. Tableaux croisés avec pourcentages en ligne et en colonne, test du khi-deux, avertissement si plus de 20 % des effectifs théoriques sont inférieurs à 5.
8. **Jeu de référence** : `apps/api/tests/fixtures/reference_survey/` contient un questionnaire, 500 réponses et les résultats attendus calculés dans SPSS. Les tests comparent chaque statistique et chaque export à ces résultats.

## 9. Encaissement

### 9.0 Périmètre

Version 1, ventes d'Arha : abonnements, Pass Mémoire, commandes Arha Services et Arha Études, encaissés sur le compte marchand Notch Pay d'Arha.

Version 1, moteur Encaissement : champ de paiement dans les formulaires, comptes connectés (service Sync de Notch Pay), frais de plateforme, reçus, billets signés, scan hors ligne, remboursements, rapprochement, tableau des encaissements (F-PAY-01 à 12). Adaptateur Campay de secours derrière la même interface.

Version 2 : paiement par carte bancaire (F-PAY-13). Version 3 : cotisations récurrentes (F-PAY-14) et adaptateur CinetPay pour la zone XOF.

### 9.1 Interface fournisseur

```python
class PaymentProvider(Protocol):
    code: str
    async def create_connected_account(self, org: OrgRef, kyc: KycPayload) -> ConnectedAccount: ...
    async def initiate_charge(self, req: ChargeRequest) -> ChargeInitiated: ...
    async def get_charge(self, provider_ref: str) -> ChargeStatus: ...
    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> WebhookEvent: ...
    async def refund(self, provider_ref: str, amount: int) -> RefundResult: ...
    async def list_transactions(self, since: datetime, until: datetime) -> list[ProviderTxn]: ...
```

`ChargeRequest` contient : `idempotency_key`, `amount`, `currency`, `msisdn` (format E.164), `channel` (`mtn`, `orange`, `auto`), `connected_account_id`, `platform_fee`, `description`, `reference` (identifiant du paiement Arha), `callback_url`.

### 9.2 Adaptateurs

1. **Notch Pay** (principal). Utiliser le service Sync pour plateformes : compte connecté par organisation, frais de plateforme (`application_fee`) et destination vers le compte connecté. Canaux Mobile Money Cameroun documentés : `cm.mtn`, `cm.orange`, `cm.mobile`. Clés de test préfixées `test_`, clés de production `live_`. **Avant d'écrire le code, lis `https://developer.notchpay.co` (paiements, Sync, webhooks, transferts) et confirme les noms exacts des champs, l'en-tête et l'algorithme de signature des webhooks.** Marque chaque hypothèse non vérifiée avec `# VERIFY:`.
2. **Campay** (secours). API `collect`, statut de transaction, jeton d'accès par identifiants d'application. Campay ne propose pas de partage de commission documenté : en mode secours, la commission d'Arha est comptabilisée dans `usage_counters` et facturée mensuellement à l'organisation.
3. **Interface prête** pour CinetPay (V3), Paystack et Flutterwave (phase C internationale).

Le choix du fournisseur se fait par pays et par organisation dans `config/countries.yaml`. Changer de fournisseur ne touche aucun code métier.

### 9.3 Machine à états du paiement

```
created -> pending -> succeeded
                   -> failed
                   -> expired (aucune confirmation après 15 minutes)
succeeded -> refunded
```

Toute transition est écrite dans `payments.raw_events` et dans `audit_events`. Une transition interdite lève une erreur et une alerte.

### 9.4 Déroulé

1. Le formulaire envoie la réponse avec l'en-tête `Idempotency-Key`.
2. Le serveur valide, recalcule le montant et les frais, crée `payments` en `created`, puis appelle `initiate_charge`.
3. Le répondant valide sur son téléphone, dans l'interface de son opérateur.
4. Le webhook arrive. Le serveur vérifie la signature, recharge le statut par `get_charge` (contre-vérification), puis passe le paiement en `succeeded` ou `failed`.
5. Sans webhook après 90 secondes, une tâche interroge `get_charge` avec un recul exponentiel jusqu'à 15 minutes.
6. En `succeeded` : la réponse passe `payment_status = paid`, les billets sont émis, le reçu PDF est généré, l'e-mail part.
7. Le formulaire interroge `GET /v1/public/payments/{id}` toutes les 3 secondes pendant l'attente, puis affiche le résultat.

### 9.5 Frais

- Commission d'Arha : `fee_bps` de l'offre de l'organisation (section 11), arrondie à l'unité supérieure.
- Frais de l'agrégateur : lus dans la configuration du fournisseur, affichés comme estimation.
- `fee_bearer = payer` : le payeur paie `prix + commission Arha + frais estimés`. Le détail s'affiche avant validation.

### 9.6 Billets

- Jeton signé Ed25519 contenant `ticket_id`, `form_id`, `category_id`, `serial`, `issued_at`. Encodage base64url compact. QR généré par segno.
- Quotas de catégorie garantis par `SELECT ... FOR UPDATE` sur la catégorie et un compteur transactionnel. Test de charge : 200 paiements simultanés pour un quota de 150, jamais plus de 150 billets.
- Scan hors ligne : l'application de scan télécharge la clé publique et la liste des billets émis (identifiants et hachages), vérifie la signature localement, garde l'état des scans dans IndexedDB et synchronise au retour du réseau. Un double scan est signalé.

### 9.7 Rapprochement

Tâche quotidienne à 03:00 Africa/Douala : `list_transactions` sur 48 heures glissantes, comparaison avec `payments`, alerte console pour tout écart (montant, statut, transaction inconnue).


## 10. Hors ligne et synchronisation (formulaire public et mode enquêteur)

1. Workbox met en cache l'application, la version publiée du formulaire, le thème et les traductions (stratégie stale-while-revalidate pour le schéma, cache-first pour les ressources versionnées).
2. L'identifiant UUIDv7 de la réponse est créé au premier champ modifié.
3. Chaque modification écrit le brouillon dans IndexedDB (clé : `form_version_id:submission_id`).
4. L'envoi passe par une file locale. Déclencheurs : retour du réseau (`online`), ouverture de la page, Background Sync quand le navigateur le propose.
5. `POST /v1/public/forms/{code}/submissions` est idempotent par `submission.id`. Un second envoi renvoie `200` avec le résultat initial.
6. Le paiement exige le réseau. Hors ligne, la réponse est enregistrée avec `payment_status = pending_payment` et la page propose de payer au retour du réseau.
7. Reprendre plus tard : code de 6 caractères (alphabet sans caractères ambigus), haché en base, valable 30 jours, limité à 5 essais par heure et par adresse IP.
8. Budget : moins de 60 Ko compressés de JS et CSS. Pas de bibliothèque de dates lourde. Pas de framework CSS complet chargé côté public : CSS généré et purgé.
9. **Mode enquêteur** (`/terrain`, même application Preact, chargement différé) : activation par code à usage unique valable 72 heures, téléchargement des questionnaires assignés, collecte illimitée hors ligne, file IndexedDB chiffrée (AES-GCM via WebCrypto, clé dérivée du code personnel par PBKDF2 avec 310 000 itérations), métadonnées d'entretien automatiques, synchronisation par lots idempotents qui reprend où elle s'est arrêtée, demande de stockage persistant (`navigator.storage.persist()`), alerte si aucune synchronisation depuis 48 heures.
10. **Contrôle qualité V1** : durée inférieure au seuil (par défaut 30 % de la durée médiane), réponses identiques sur une matrice, doublon de réponse (empreinte des réponses), heure de collecte anormale. Chaque règle produit un `quality_flag`. Le score de qualité va de 0 à 100.


## 11. Configuration commerciale (`config/plans.yaml`)

Ce fichier est la seule source des règles commerciales. Valeurs de référence du cahier des charges :

```yaml
currency: XAF
annual_months_charged: 10          # engagement annuel : 2 mois offerts
pioneer: { seats: 30, discount_bps: 2000, months: 12, plans: [pro, equipe, terrain] }
supervisor_program: { min_students: 5, grants_plan: pro, duration: academic_year }
quota_policy: { alert_at_pct: 80, grace_hours: 72 }
renewal: { remind_days_before: 7, downgrade_after_days_unpaid: 7 }
ambassador: { subscription_reward: one_month_of_plan, paid_after_months_paid: 2, pass_reward: 1000 }

plans:
  decouverte:
    price: 0
    responses: { per_month: 500 }
    members: 1
    reviewers: 1
    enumerators: 1
    storage_gb: 1
    max_file_mb: 10
    version_history_days: 7
    exports: [csv, xlsx]
    features: [logic, calculations, descriptive_stats, field_mode, email_notifications_owner,
               payments, tickets, payment_dashboard]
    branding_required: true
    payment_fee_bps: 300                # moteur Encaissement, dès la V1
  pass_memoire:
    price_once: 5000
    duration_days: 120
    auto_renew: false
    responses: { total: 3000 }
    members: 1
    reviewers: 2
    enumerators: 3
    storage_gb: 2
    max_file_mb: 25
    version_history_days: 30
    exports: [csv, xlsx, sav, dta, r, codebook]
    features: [logic, calculations, descriptive_stats, crosstabs, field_mode, quality_basic,
               partial_responses, respondent_emails, payments, tickets, payment_dashboard]
    branding_required: false
    payment_fee_bps: 300
  pro:
    price_monthly: 9900
    price_yearly: 99000
    responses: { per_month: 10000 }
    members: 3
    reviewers: unlimited
    enumerators: 3
    storage_gb: 10
    max_file_mb: 100
    version_history_days: 30
    whatsapp_included: 200              # V2
    exports: [csv, xlsx, sav, dta, r, codebook]
    features: [logic, calculations, descriptive_stats, crosstabs, field_mode, quality_basic,
               partial_responses, respondent_emails, google_sheets, webhooks, custom_theme,
               payments, tickets, payment_dashboard]
    branding_required: false
    payment_fee_bps: 150
  equipe:
    inherits: pro
    price_monthly: 29900
    price_yearly: 299000
    responses: { per_month: 50000 }
    members: 10
    enumerators: 10
    storage_gb: 50
    version_history_days: 90
    whatsapp_included: 1000
    extra_features: [advanced_roles, audit_log, custom_domain, public_api, approvals,
                     sso_google, mfa_required_owner]   # audit, domaine et API en V2
    payment_fee_bps: 100
  terrain:
    inherits: equipe
    price_monthly: 59900
    price_yearly: 599000
    responses: { per_month: 100000 }
    members: 15
    enumerators: 30
    enumerator_extra_monthly: 2000
    storage_gb: 100
    extra_features: [quality_advanced, assignments_quotas, live_map, kiosk_mode]   # V2
    payment_fee_bps: 100
  institution:
    price_monthly_from: 250000
    contract: annual
    payment_fee_bps: 50
    custom: true

addons:
  enumerator_monthly: { price: 2000 }
  ai_credits_1000: { price: 5000 }          # V2
  whatsapp_utility_1000: { price: 9000 }    # V2
  whatsapp_marketing_500: { price: 12000 }  # V2
  sms_100: { price: 9500 }                  # V2
  storage_10gb_monthly: { price: 2500 }

studies:                                     # Arha Services (analyses, mises en place) et Arha Études (enquêtes)
  questionnaire_review: { price: 25000, upfront_pct: 100, brand: services }
  thesis_analysis: { price: 35000, upfront_pct: 100, brand: services }
  advanced_analysis: { price: 75000, upfront_pct: 100, brand: services }
  payment_form_setup: { price: 75000, upfront_pct: 100, brand: services }
  turnkey_survey_from: { price: 450000, upfront_pct: 50, brand: etudes }
```

Le chargement valide ce fichier avec un modèle Pydantic strict. Une valeur manquante ou incohérente empêche le démarrage. Les fonctionnalités sont vérifiées par `require_feature("crosstabs")` côté serveur et masquées côté client.


## 12. Sécurité : liste de contrôle d'implémentation

Applique ces points dès la première ligne. Chaque point a un test automatisé quand c'est possible.

- **S-01 Mots de passe :** Argon2id (paramètres argon2-cffi recommandés, réévalués chaque année), 10 caractères minimum, refus des mots de passe compromis via l'API Pwned Passwords en k-anonymat (préfixe SHA-1 de 5 caractères), message neutre en cas d'échec.
- **S-02 Sessions :** jeton aléatoire 256 bits, seul son haché est stocké. Cookie `__Host-arha_session`, `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`. Rotation à la connexion et à l'élévation de privilège. Expiration à 14 jours d'inactivité. CSRF : jeton synchronisé dans un en-tête `X-CSRF-Token` pour toute méthode non sûre.
- **S-03 Double authentification :** TOTP RFC 6238, 10 codes de secours hachés. Obligatoire pour les propriétaires Équipe, Terrain, Institution, pour les superviseurs d'enquêteurs et pour toute la console interne.
- **S-04 Autorisation :** chaque route déclare `Depends(require_permission("forms:edit"))` ou figure dans une liste blanche publique. Un test parcourt toutes les routes et échoue si une route n'a ni permission ni entrée en liste blanche.
- **S-05 Isolation :** test transverse qui crée deux organisations et tente chaque route de l'organisation A avec la session de B. Toute réponse autre que 403 ou 404 fait échouer la CI.
- **S-06 Transport :** TLS 1.3, HSTS `max-age=31536000; includeSubDomains; preload`.
- **S-07 Repos :** volume de données chiffré (LUKS) sur le serveur, secrets d'organisation chiffrés par enveloppe (clé de données par organisation, chiffrée par la clé maîtresse issue des secrets SOPS), sauvegardes chiffrées.
- **S-08 Entrées :** Pydantic strict, tailles maximales sur chaque champ, requêtes paramétrées uniquement, texte riche nettoyé par nh3 avec liste blanche.
- **S-09 En-têtes :** `Content-Security-Policy` stricte avec nonce (pas de `unsafe-inline`), `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` minimale (caméra autorisée uniquement sur la route de scan et l'application terrain), `frame-ancestors` contrôlé (intégration autorisée seulement pour les formulaires dont l'option est activée).
- **S-10 Fichiers :** vérification du type réel (signature magique), taille par offre, analyse ClamAV asynchrone, stockage privé, URL signées de 5 minutes, domaine séparé, `Content-Disposition: attachment`.
- **S-11 Webhooks sortants :** en-tête `Arha-Signature: t=<timestamp>,v1=<hmac_sha256>`, tolérance de 5 minutes, protection SSRF (résolution DNS puis blocage des plages privées, de boucle locale, de lien local et des adresses de métadonnées, refus des redirections), délai de 10 secondes, nouvelles tentatives sur 24 heures.
- **S-12 Limitation de débit :** Valkey, fenêtre glissante. Valeurs de départ : connexion 5 par minute et par IP ; envoi de réponse 20 par minute et par IP et par formulaire ; API 600 par minute et par clé. Au-delà d'un seuil de suspicion, défi Cloudflare Turnstile.
- **S-13 Secrets :** SOPS et age, gitleaks en pré-commit et en CI, procédure de rotation dans `docs/runbooks/`.
- **S-14 Serveurs :** script `infra/hardening/harden.sh` idempotent : utilisateur de déploiement, SSH par clé uniquement, root désactivé, UFW (22 restreint, 80, 443), fail2ban, unattended-upgrades, synchronisation horaire, Docker sans socket exposé, conteneurs non root avec `read_only` quand possible.
- **S-15 Dépendances :** versions épinglées, Dependabot hebdomadaire, pip-audit et pnpm audit bloquants pour les vulnérabilités hautes.
- **S-16 Journaux :** structlog JSON, filtre qui retire e-mail, téléphone, jetons et contenu de réponse. Conservation 90 jours. Journal d'audit métier 3 ans, chaîné par hachage (`hash = sha256(previous_hash || canonical_json(event))`).
- **S-17 Sauvegardes :** WAL-G en continu vers le stockage objet hors site, sauvegarde complète quotidienne, restic pour les fichiers, test de restauration mensuel automatisé sur la préproduction avec rapport.
- **S-18 Tests d'intrusion :** liste OWASP ASVS niveau 2 exécutée avant le lancement, page `/.well-known/security.txt` et programme de signalement.
- **S-19 Paiement :** idempotence, signature, contre-vérification, rapprochement, alerte.
- **S-20 Abus :** filtre à la publication basé sur `config/abuse_terms.yaml` (exemples : « code PIN », « code secret », « mot de passe », « code Orange Money », « code MoMo », « PIN code », « password », « CVV », numéros de carte détectés par l'algorithme de Luhn). Revue manuelle des formulaires signalés. Suspension effective en moins de 60 secondes (cache invalidé).


## 13. Conventions d'API

- REST JSON sous `/v1`. Routes publiques sous `/v1/public`. Console sous `/v1/admin`.
- Erreurs au format RFC 9457 (`application/problem+json`) avec `type`, `title`, `status`, `detail`, `code` stable et message traduit.
- Pagination par curseur (`?cursor=...&limit=50`, maximum 200).
- En-tête `Idempotency-Key` obligatoire pour la création de paiement et l'envoi de réponse, stocké 24 heures.
- OpenAPI 3.1 généré par FastAPI, publié pour l'API publique (V2) avec exemples.
- Versionnement : changement incompatible uniquement par nouvelle version majeure de l'API.
- Toute date en ISO 8601 UTC. Tout montant en entier avec sa devise.


## 14. Conventions d'interface

### 14.1 Identité visuelle
Jetons dans `packages/ui/tokens.css` :

```css
--arha-orange: #C9621B;  --arha-orange-light: #E89A5C;
--arha-beige: #F3EBDD;   --arha-sand: #E6D8C0;   --arha-cream: #FCF9F4;
--arha-ink: #2A1F17;     --arha-grey: #7A6A5A;   --arha-green: #4E6B4A;
```

Titres en Cormorant Garamond, texte en Inter (application) et police système (formulaire public, pour le poids). Rayons doux, filets fins, beaucoup d'espace. Le thème de chaque formulaire peut remplacer la couleur primaire si le contraste reste au moins de 4,5 pour 1.

### 14.2 Règles
- Mobile d'abord. Cible de test principale : écran de 360 x 740 pixels, Chrome Android.
- Accessibilité WCAG 2.1 AA : libellés associés, focus visible, ordre de tabulation logique, rôles ARIA corrects, messages d'erreur liés aux champs, cibles tactiles de 44 pixels.
- Tous les textes passent par Lingui. Les catalogues `fr` et `en` sont complets avant toute fusion.
- Rédaction : vouvoiement, phrases courtes, aucun emoji, aucun tiret long, verbes d'action sur les boutons (« Publier le formulaire », « Payer 10 000 FCFA »).
- Formats : `Intl.NumberFormat` et `Intl.DateTimeFormat` selon la langue. Le franc CFA s'affiche « 10 000 FCFA ».
- L'éditeur affiche toujours un aperçu mobile à droite sur grand écran et un bouton d'aperçu sur mobile.


## 15. Stratégie de tests et barrières de qualité

| Niveau | Outil | Barrière |
|---|---|---|
| Unitaires Python | pytest, Hypothesis | Couverture d'au moins 85 % sur `logic`, `payments`, `billing`, `submissions` |
| Unitaires TS | Vitest | Couverture d'au moins 85 % sur `logic-ts` et le moteur de rendu |
| Conformité logique | cas JSON partagés | 100 % des cas passent en TS et en Python |
| Exports statistiques | jeu de référence SPSS | Statistiques et fichiers identiques aux résultats attendus |
| Hors ligne | Playwright en mode avion | 500 réponses synchronisées, aucun doublon, aucune perte |
| Isolation | tests transverses | Aucune fuite entre organisations |
| Permissions | test de parcours des routes | Aucune route sans permission ni liste blanche |
| Bout en bout | Playwright | Parcours critiques : inscription, création, relecture, publication, réponse en ligne, collecte en mode avion par un enquêteur, synchronisation, export SPSS, achat d'un Pass Mémoire |
| Taille | script de build | Formulaire public sous 60 Ko compressés |
| Performance | Lighthouse CI | Performance et accessibilité au moins 90 sur le formulaire public |
| Charge | k6 | 50 envois par seconde pendant 5 minutes, p95 sous 300 ms côté API |
| Sécurité | Semgrep, gitleaks, pip-audit, pnpm audit, Trivy | Aucune alerte haute ou critique |
| Typage | mypy strict, `tsc --noEmit` | Zéro erreur |

Le fournisseur de paiement est simulé par un faux serveur (`FakeNotchPay`) dans les tests. Un test d'intégration optionnel utilise l'environnement de test réel de l'agrégateur, déclenché manuellement.


## 16. Infrastructure et déploiement

### 16.1 Serveurs
- **Production :** Contabo Cloud VPS 30 (8 vCPU, 24 Go) en Allemagne. Services Compose : `caddy`, `api`, `worker`, `postgres`, `valkey`, `clamav`, `node-exporter`, `postgres-exporter`.
- **Préproduction et supervision :** Contabo Cloud VPS 10. Services : copie de la pile pour la préproduction, `prometheus`, `grafana`, `loki`, `glitchtip`, `uptime-kuma`, test de restauration mensuel.
- **Avant le lancement :** un seul Contabo Cloud VPS 20 héberge développement et bêta.
- **Stockage objet** compatible S3 pour les fichiers. **Second fournisseur** de stockage objet pour les sauvegardes hors site.
- **Cloudflare** (offre gratuite) pour le DNS, le cache des fichiers statiques et la protection anti-DDoS.

### 16.2 Variables d'environnement (extrait)

```
ARHA_ENV, ARHA_BASE_DOMAIN, ARHA_APP_URL, ARHA_FORMS_URL, ARHA_API_URL, ARHA_FILES_URL,
DATABASE_URL, VALKEY_URL, S3_ENDPOINT, S3_BUCKET, S3_ACCESS_KEY, S3_SECRET_KEY,
MASTER_KEY (via SOPS), TICKET_SIGNING_KEY (Ed25519, via SOPS),
NOTCHPAY_PUBLIC_KEY, NOTCHPAY_PRIVATE_KEY, NOTCHPAY_WEBHOOK_SECRET,
CAMPAY_USERNAME, CAMPAY_PASSWORD,
SMTP_HOST, SMTP_USER, SMTP_PASSWORD, MAIL_FROM,
GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET,
WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_ACCESS_TOKEN, WHATSAPP_APP_SECRET (V2),
GEMINI_API_KEY (V2), TURNSTILE_SECRET, GLITCHTIP_DSN
```

### 16.3 Chaîne CI/CD
1. `ci.yml` sur chaque demande de fusion : lint, typage, tests, conformité, taille, sécurité.
2. `build.yml` sur la branche principale : images Docker multi-étapes, scan Trivy, publication GHCR avec étiquette de commit.
3. `deploy-staging.yml` automatique : SSH vers la préproduction, `docker compose pull && up -d`, migrations Alembic, contrôle de santé, tests Playwright contre la préproduction.
4. `deploy-prod.yml` manuel avec approbation : même séquence, bascule après contrôle de santé, conservation de l'image précédente pour retour arrière en moins de 5 minutes.
5. Migrations en deux temps : ajout compatible, déploiement, puis suppression dans une version suivante.


## 17. Phases de réalisation

Chaque phase liste ses objectifs, ses livrables, les exigences couvertes (identifiants du cahier des charges) et ses critères de sortie. Tu ne passes pas à la phase suivante tant que les critères ne sont pas vérifiés.

### Phase 0 · Socle (sprint S0, 1 au 7 décembre 2026)
- Monorepo, outillage, `CLAUDE.md`, `docs/PROGRESS.md`, ADR 0001 (stack), ADR 0002 (multi-organisation par RLS), ADR 0003 (paiement sans détention de fonds).
- Compose de développement : PostgreSQL, Valkey, API, web, forms.
- Squelette FastAPI avec santé, journaux structurés, gestion des erreurs RFC 9457, réglages.
- `packages/schema` avec la première version du schéma et la génération des types.
- `config/plans.yaml` et son modèle de validation.
- CI complète (même avec peu de code).
- Script de durcissement du serveur et premier déploiement de préproduction.
- **Sortie :** `pnpm turbo build` et `uv run pytest` passent ; CI verte ; la préproduction répond en HTTPS ; gitleaks et Trivy propres.

### Phase 1 · Identité et organisations (S1, 8 au 21 décembre)
- F-AUT-01 à 03, F-ORG-01, 02, 04. S-01 à S-05.
- Inscription, vérification d'e-mail, connexion, lien magique, Google, TOTP, sessions, organisations, invitations, rôles, dossiers.
- Tests transverses d'isolation et de permissions en place dès cette phase.
- **Sortie :** parcours Playwright inscription, création d'organisation, invitation, changement de rôle ; test d'isolation et test de permissions verts.

### Phase 2 · Éditeur, versions et relecture (S1 et S2)
- F-EDI-01 à 12. Éditeur par blocs, commandes `/`, glisser-déposer, annuler et rétablir, aperçu mobile, thèmes, traductions, modèles méthodologiques (questionnaire de mémoire, enquête ménage, satisfaction, étude de marché, évaluation de formation, Likert, consentement éclairé), fermeture, page de fin, publication immuable, historique, noms de variables et codes de modalités, liens de relecture et commentaires de l'encadreur.
- **Sortie :** création d'un questionnaire de 40 blocs en deux langues, relecture commentée par un relecteur sans compte payant, publication, restauration d'une version ; aucune perte de saisie après rechargement brutal ; noms de variables valides pour SPSS, Stata et R.

### Phase 3 · Logique, formulaire public, hors ligne (S2, 22 décembre au 4 janvier 2027)
- F-LOG-01 à 05, F-PUB-01 à 10. Moteurs TS et Python, suite de 300 cas, détection à la publication, rendu Preact, sauvegarde locale, file d'envoi, reprise par code, consentement éclairé, balises Open Graph, badge, signalement, mention « Créé avec Arha ».
- **Sortie :** 100 % des cas de conformité ; formulaire public sous 60 Ko ; Lighthouse au moins 90 en 3G lente ; test Playwright hors ligne (coupure, saisie, retour du réseau, envoi unique).

### Phase 4 · Moteur Encaissement (S3, 5 au 18 janvier)
- F-PAY-01 à 12, section 9, S-19. Adaptateur Notch Pay (comptes connectés par le service Sync, frais de plateforme), adaptateur Campay de secours, champ de paiement dans l'éditeur et le formulaire public, machine à états, webhooks signés, contre-vérification, idempotence, frais reportés ou non au payeur, reçus PDF numérotés avec code QR de vérification, billets signés Ed25519 avec catégories et quotas, application de scan hors ligne, remboursements, rapprochement quotidien, tableau des encaissements avec export comptable.
- **Sortie :** paiement de bout en bout dans le bac à sable de l'agrégateur ; double clic et rejeu réseau sans double débit ; webhook falsifié rejeté ; 200 paiements simultanés pour un quota de 150 billets, jamais plus de 150 billets ; scan de 300 billets en mode avion avec détection des doubles scans ; aucun flux ne crédite un compte d'Arha pour le compte d'un client.

### Phase 5 · Mode enquêteur et qualité (S4, 19 janvier au 1er février)
- F-TER-01 à 07. Comptes enquêteurs, activation, téléchargement des questionnaires, collecte hors ligne illimitée, file chiffrée, métadonnées d'entretien, GPS, synchronisation par lots idempotents, contrôle qualité V1, tableau d'avancement par enquêteur.
- **Sortie :** 500 réponses collectées en mode avion sur un profil de téléphone modeste puis synchronisées sans doublon ni perte ; coupure simulée au milieu d'une synchronisation ; téléphone « perdu » sans réponse lisible ; drapeaux de qualité corrects sur un jeu de test.

### Phase 6 · Réponses, exports statistiques, analyse (S5, 2 au 15 février)
- F-REP-01 à 08, F-ANA-01 à 04, F-NOT-01 et 02, section 8 bis.
- Tableau des réponses paginé côté serveur, statuts, réponses partielles, statut de paiement visible et filtrable, exports CSV, Excel, SPSS, Stata et R, dictionnaire, export anonyme, statistiques descriptives, tableaux croisés et khi-deux, entonnoir sans cookie, Google Sheets, webhooks signés, e-mails.
- **Sortie :** le jeu de référence passe (statistiques égales à SPSS, fichiers .sav et .dta relus par pyreadstat avec libellés et codes corrects, script R exécuté dans un conteneur R) ; webhook reçu et vérifié ; tableau fluide avec 50 000 réponses.

### Phase 7 · Facturation, Pass Mémoire, confiance, console (S6, 16 février au 1er mars)
- F-FAC-01 à 06, F-ORG-03, F-ADM-01 à 05, S-20, section 9.0.
- Encaissement des ventes d'Arha par Mobile Money (compte marchand Notch Pay), abonnements, Pass Mémoire de 120 jours sans renouvellement automatique, factures numérotées, renouvellement, rétrogradation, compteurs d'usage, commission par offre lue dans `plans.yaml`, alertes, période de grâce, offre Pionnier, Programme Encadreur, filtre anti-hameçonnage, vérification d'organisation, plafonds d'encaissement pour les comptes récents, console interne (signalements, suspensions, indicateurs, suivi d'Arha Services et d'Arha Études).
- **Sortie :** achat d'un Pass Mémoire dans l'environnement de test de l'agrégateur ; cycle abonnement, dépassement, alerte, grâce, blocage, renouvellement ; changement d'offre qui modifie la commission dès le paiement suivant ; formulaire frauduleux bloqué ; suspension effective en moins de 60 secondes.

### Phase 8 · Durcissement et bêta (S7, 1er au 15 mars 2027)
- Revue ASVS niveau 2, test de charge k6, test de restauration complet, `security.txt`, documents juridiques intégrés (CGU, DPA, politique de confidentialité, usage acceptable, conditions d'encaissement pour les organisations, conditions d'Arha Services et d'Arha Études avec la règle d'intégrité), site vitrine Astro avec tarifs, modèles et guides, tableau de bord de supervision et alertes.
- Bêta privée avec 20 à 25 pilotes (étudiants, enseignants, deux cabinets, deux écoles, deux organisateurs), dont au moins trois formulaires payants réels de faible montant. Tri quotidien des retours. Gel des fonctionnalités le 8 mars.
- **Sortie :** aucune vulnérabilité haute ouverte ; restauration réussie et chronométrée sous 4 heures ; rapprochement sans écart sur toute la bêta ; lancement public le 16 mars 2027.

### Phase 9 · Version 2 (avril à juillet 2027)
- Version 2.0 (avril à mai) : import de questionnaires Word, PDF et Excel par modèle de langage, avec relecture obligatoire avant enregistrement ; Arha Terrain avancé (F-TER-08, assignations par zone, quotas, carte en direct, contrôle qualité avancé, mode kiosque) ; paiement par carte (F-PAY-13).
- Version 2.1 (juin à juillet) : F-NOT-03 et 04 (WhatsApp Cloud API direct, reçus et rappels par modèles utilitaires approuvés, WhatsApp Flows, SMS par pack), Arha Intelligence (passerelle unique, retrait des champs identifiants, crédits, Gemini Flash-Lite par défaut, modèle interchangeable, correcteur de questions, codage des réponses ouvertes, synthèse descriptive), F-ANA-05 et 06, banque de questions et d'échelles, lecture à voix haute, traduction automatique relue, journal d'audit consultable, approbations, domaine personnalisé, API publique documentée pour la collecte et l'encaissement, champs chiffrés.

### Phase 10 · Version 3 (août à novembre 2027)
- Version 3.0 (août à septembre) : pondération et calcul de taille d'échantillon, quiz, certificats vérifiables, import par photo, carte de la logique, cotisations récurrentes (F-PAY-14).
- Version 3.1 (octobre à novembre) : adaptateur CinetPay et devise XOF, questions en langage naturel, formulaires enchaînés et récurrents, réponse vocale transcrite, création par note vocale, relance par question de précision, vérification par rappel aléatoire, espace partenaire, résidence des données au Cameroun pour l'offre Institution.

## 18. Protocole de chaque session

1. Lis `CLAUDE.md`, `docs/PROGRESS.md`, les ADR récentes et la section de la phase demandée.
2. Rédige un plan : fichiers touchés, migrations, tests à écrire, risques, questions. Attends la validation du porteur si le plan change l'architecture, le modèle de données, la sécurité ou une règle commerciale.
3. Écris les tests d'acceptation. Montre qu'ils échouent.
4. Implémente par petites étapes. Lance les tests après chaque étape.
5. Lance la batterie complète : lint, typage, tests, conformité, taille, sécurité.
6. Relis ton propre code avec la liste de la section 12. Corrige.
7. Mets à jour `docs/PROGRESS.md` (fait, reste, dettes, points `VERIFY`), `docs/CHANGELOG.md` et les ADR.
8. Rends un compte rendu court : ce qui est livré, comment c'est vérifié (commandes et résultats), ce qui reste, ce qui est supposé.

Modèle de description de demande de fusion :

```
## Objet
Exigences couvertes : F-PAY-04, S-19

## Changements
...

## Vérification
- uv run pytest apps/api -k F_PAY_04 : OK
- pnpm --filter forms test : OK
- Taille formulaire public : 47,2 Ko

## Sécurité
Liste de la section 12 relue. Points concernés : S-19.

## Points à vérifier
# VERIFY: nom de l'en-tête de signature Notch Pay
```


## 19. Définition de « terminé »

Une fonctionnalité est terminée quand :

1. ses tests d'acceptation passent et citent les identifiants d'exigence ;
2. le typage strict passe ;
3. la liste de sécurité est relue ;
4. les textes existent en français et en anglais ;
5. la documentation est à jour ;
6. la fonctionnalité tourne en préproduction.


## 20. Ce que tu ne fais jamais

- Encaisser ou reverser des fonds pour le compte d'une organisation.
- Faire confiance à un montant, une visibilité ou une validation calculés par le navigateur.
- Écrire un secret, une donnée personnelle ou un code Mobile Money dans un journal.
- Désactiver un contrôle de sécurité pour faire passer un test.
- Ajouter une dépendance non justifiée ou un service payant non prévu par le budget.
- Inventer un champ d'API externe sans le marquer `VERIFY`.
- Coder un prix, un quota ou un domaine en dur.
- Livrer un texte d'interface seulement en français ou seulement en anglais.
- Déployer en production sans l'accord explicite du porteur.
- Supprimer des données d'un client sans procédure tracée.
- Rédiger un mémoire, une thèse ou un article à la place d'un utilisateur.
- Afficher une réponse de terrain comme enregistrée avant qu'elle soit persistée localement.


## 21. Annexes

### 21.1 Indicateurs à exposer dans la console interne
Indicateurs directeurs : réponses valides collectées dans le mois (complètes et conformes au contrôle qualité) et volume encaissé dans le mois par les formulaires des clients. Puis : revenu récurrent mensuel, croissance mensuelle du revenu récurrent, rétention nette du revenu, organisations qui encaissent, taux de réussite des paiements, abonnés payants actifs, Pass Mémoire vendus, utilisateurs actifs (au moins un questionnaire avec dix réponses en 30 jours), exports statistiques du mois, conversion des étudiants vers le Pass, attrition, réussite de la synchronisation hors ligne, disponibilité, p95 de l'API, part d'Arha Services et d'Arha Études dans le revenu, coût d'infrastructure rapporté au chiffre d'affaires.

### 21.2 Paliers d'investissement (pour information)
- P1 : 20 pilotes actifs dont deux cabinets ou laboratoires et deux organisateurs ou écoles, 3 promesses d'achat, un paiement réel encaissé par un formulaire sur un compte connecté.
- P2 : revenu récurrent d'au moins 300 000 FCFA pendant deux mois.
- P3 : revenu récurrent d'au moins 1 000 000 FCFA pendant deux mois.
- P4 : revenu récurrent d'au moins 3 000 000 FCFA pendant deux mois.

Le code doit permettre de suivre ces seuils dans la console interne.

### 21.3 Glossaire technique
- **Compte connecté :** compte d'une organisation chez l'agrégateur, sur lequel ses encaissements sont réglés.
- **Frais de plateforme :** commission d'Arha prélevée par l'agrégateur au moment du paiement.
- **RLS :** sécurité au niveau des lignes de PostgreSQL.
- **UUIDv7 :** identifiant unique triable dans le temps.
- **AST :** arbre syntaxique d'une expression, stocké en JSON.

Fin du master prompt.
