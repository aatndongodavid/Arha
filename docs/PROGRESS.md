# Arha · État d'avancement

> **14 novembre 2026 : le cahier des charges passe en v1.2.** Le MVP ci-dessous suit la v1.0. Les écarts à combler sont listés dans `docs/ecarts-v1.2.md`.

Dernière mise à jour : 13 novembre 2026, fin de la session de réalisation du MVP.
Branche : `claude/arha-mvp`. Rien n'est déployé. Aucun paiement réel n'a été effectué.

## Comment vérifier

```bash
cd apps/api && uv run pytest tests --cov          # 401 tests
cd apps/api && uv run ruff check src tests && uv run mypy src
pnpm --filter @arha/logic-ts test                 # 337 tests, dont 327 cas de conformité
pnpm -r typecheck
pnpm --filter @arha/forms build                   # échoue au-delà de 60 Ko
node e2e/public-form.mjs && node e2e/web-app.mjs  # avec l'API et les deux applications démarrées
```

Résultats de la dernière exécution : 401 tests Python verts, couverture logic 89 %, payments 86 %, billing 95 %,
submissions 85 % ; ruff et mypy strict sans erreur ; 337 tests TypeScript verts ; formulaire public 26,0 Ko
compressés ; les deux parcours navigateur verts ; `pip-audit` sans faille ; `pnpm audit` sans faille haute.

## Fait et vérifié par des tests

| Domaine | Exigences | Vérification |
|---|---|---|
| Identité | F-AUT-01 à 03, S-01 à S-03 | `tests/test_identity.py` |
| Organisations, rôles, dossiers | F-ORG-01, 02, 04 | `tests/test_orgs.py` |
| Permissions et isolation | S-04, S-05 | parcours de toutes les routes |
| Éditeur, versions, modèles | F-EDI-01 à 10 | `tests/test_forms.py`, `e2e/web-app.mjs` |
| Logique et calculs | F-LOG-01 à 05 | 327 cas partagés Python et TypeScript |
| Formulaire public, hors ligne | F-PUB-01 à 09 | `tests/test_public.py`, `e2e/public-form.mjs` |
| Encaissement, billets, scan | F-PAY-01 à 10, S-19 | `tests/test_payments.py` (simulateur) |
| Réponses, exports, analyse | F-REP-01 à 04, 06, 07, F-ANA-01 à 03 | `tests/test_exports_billing_console.py` |
| Facturation et quotas | F-FAC-01 à 05 | idem |
| Confiance et console | F-ORG-03, F-ADM-01 à 04, S-20 | idem |
| Journaux et audit | S-16 | idem |

## Fait mais non vérifié en conditions réelles

- **Adaptateurs Notch Pay et Campay.** Écrits sans accès à la documentation (hôte `developer.notchpay.co` bloqué
  dans la session). 31 marqueurs `VERIFY` dans le code et la configuration. Aucun appel réel n'a été fait.
- **Infrastructure.** Dockerfiles, Compose, Caddyfile, `harden.sh`, scripts de sauvegarde et workflows GitHub
  Actions sont écrits et validés en syntaxe seulement. Aucune image n'a été construite, aucun serveur durci.
- **Worker Procrastinate.** Les tâches tournent en mode immédiat dans les tests. Le worker réel et ses tâches
  périodiques (rapprochement à 03:00, relances, balayage des paiements) n'ont pas été exécutés.
- **Analyse ClamAV, envoi SMTP, connexion Google.** Le code existe, aucun service réel n'a été branché.
- **Scan par caméra.** La vérification hors ligne et la saisie manuelle sont testées côté API. La lecture par
  caméra (`BarcodeDetector`) n'a pas été testée sur un téléphone.

## Non fait (reste de la V1)

- F-REP-05 : synchronisation Google Sheets (table et modèle présents, aucune logique).
- F-NOT-01 : résumé quotidien par e-mail (l'e-mail à chaque réponse est fait).
- F-EDI-05 : logo et image de couverture (couleurs faites, avec contrôle du contraste).
- Bloc `image` dans l'éditeur, téléversement d'images.
- S-09 : CSP avec nonce (une CSP stricte par hôte est posée dans Caddy, sans nonce).
- S-10 : adaptateur de stockage objet S3 (stockage local derrière la même interface).
- S-12 : défi Cloudflare Turnstile au-delà du seuil de suspicion.
- Page de vérification d'un reçu par code QR (`/recu` sur le site vitrine).
- Lighthouse CI, test de charge k6, revue ASVS niveau 2, Playwright dans la CI.
- Documents juridiques (CGU, DPA, confidentialité, usage acceptable), dossier de transfert de données.
- Programme ambassadeur (parrainage) : le code de parrainage est stocké, l'attribution n'est pas faite.

## Dettes techniques

1. **Règle d'architecture.** 17 imports directs de `models.py` d'un autre module subsistent (surtout dans les
   routeurs et les tâches). Le contrat import-linter est écrit mais n'est pas dans la CI. À résorber en passant
   par les services.
2. **Rotation de `MASTER_KEY`.** Aucun script de rechiffrement.
3. **ESLint, Prettier, Semgrep, gitleaks** : déclarés dans la CI, jamais exécutés localement.
4. **Éditeur.** Les conditions imbriquées s'affichent mais ne s'éditent qu'à un niveau. `between`, `in` et
   `not_in` existent dans le moteur, pas dans l'interface.
5. **Application de gestion.** Un seul fichier JavaScript de plus de 500 Ko : le découpage par route (NF-04)
   reste à faire.
6. **Indicateurs.** Disponibilité, p95 et coût d'infrastructure se lisent dans Grafana, pas dans la console.

## Ce que le porteur doit faire

1. Autoriser `developer.notchpay.co` dans le réseau de l'environnement, ou fournir les pages de documentation
   (paiements, Sync, webhooks), pour lever les marqueurs `VERIFY`.
2. Créer un compte Notch Pay de test et fournir les clés `test_` par le formulaire sécurisé de l'environnement.
3. Réserver le domaine et le serveur, générer la clé age, renseigner `.sops.yaml` et le contact de
   `security.txt`.
4. Valider les écarts de l'ADR 0001.
