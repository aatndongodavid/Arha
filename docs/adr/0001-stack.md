# ADR 0001 · Stack technique

Statut : acceptée · 13 novembre 2026

## Décision
La stack de la section 4 du master prompt est appliquée : FastAPI, PostgreSQL 16, SQLAlchemy 2 async, Alembic,
Procrastinate, Valkey, React 19, Preact, Astro, pnpm et Turborepo, uv.

## Écarts à valider par le porteur
1. **Lingui sans macros.** `@lingui/core` est utilisé avec des catalogues JSON par surface, compilés par
   `packages/i18n/compile.mjs`. La compilation échoue si une clé manque en français ou en anglais. Raison : garder le
   formulaire public léger et éviter la chaîne Babel des macros.
2. **Téléphones côté formulaire public.** `libphonenumber-js` (environ 40 Ko) n'est pas embarqué dans le formulaire
   public pour tenir le budget de 60 Ko. Le navigateur applique une règle simple, le serveur valide avec
   `phonenumbers`. Le serveur reste la référence.
3. **Arithmétique.** Le master prompt cite `Decimal` côté Python. Les deux moteurs utilisent la même arithmétique en
   entiers mis à l'échelle (10^6) avec arrondi bancaire, ce qui garantit l'égalité au franc près entre Python et
   TypeScript. Les 327 cas de conformité le vérifient.
4. **ESLint et Prettier** ne sont pas encore configurés. Le typage strict (`tsc`) et les tests passent.
5. **Site vitrine.** Les textes du site sont dans `apps/site/src/i18n.ts` (français et anglais), pas dans Lingui.
