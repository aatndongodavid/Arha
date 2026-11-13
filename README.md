# Arha

Collecter. Encaisser. Comprendre.

Plateforme de formulaires, d'encaissement Mobile Money (Orange Money, MTN MoMo) et d'analyse de données, conçue au
Cameroun pour l'Afrique. Le cahier des charges est dans `docs/cahier-des-charges/`, les règles de réalisation dans
`CLAUDE.md`, l'état exact du projet dans `docs/PROGRESS.md`.

## Démarrer en local

Prérequis : Docker, Python 3.12 avec `uv`, Node 22 avec `pnpm`.

```bash
docker compose -f infra/compose/docker-compose.dev.yml up -d
cp .env.example apps/api/.env
cd apps/api && uv sync && uv run alembic upgrade head
ARHA_JOBS_EAGER=1 uv run uvicorn arha.main:app --reload --port 8000
```

Dans un autre terminal :

```bash
pnpm install
pnpm --filter @arha/web dev      # application de gestion, port 5173
pnpm --filter @arha/forms dev    # formulaire public, port 5174
pnpm --filter @arha/site dev     # site vitrine, port 4321
```

En développement, les e-mails sont écrits dans `/tmp/arha-mail` et le paiement passe par un simulateur :
un numéro qui finit par `0000` échoue, les autres restent en attente jusqu'à confirmation.

## Organisation

| Dossier | Contenu |
|---|---|
| `apps/api` | API FastAPI, migrations Alembic, tâches Procrastinate |
| `apps/web` | Application de gestion et console interne (React) |
| `apps/forms` | Formulaire public (Preact, moins de 60 Ko) |
| `apps/site` | Site vitrine (Astro) |
| `packages/schema` | Schéma JSON du formulaire, source des types |
| `packages/logic-ts`, `packages/logic-conformance` | Moteur de logique et cas de conformité partagés |
| `packages/i18n`, `packages/ui` | Catalogues français et anglais, jetons de design |
| `config` | Offres et prix, pays et fournisseurs, termes interdits |
| `infra` | Docker, Compose, Caddy, durcissement, sauvegardes |

## Règles à ne jamais enfreindre

Arha ne détient jamais l'argent d'un tiers. Le serveur recalcule toujours les montants. Le code secret Mobile Money
n'est jamais demandé. Les organisations sont isolées par la sécurité au niveau des lignes de PostgreSQL. Voir
`CLAUDE.md`, section 3.
