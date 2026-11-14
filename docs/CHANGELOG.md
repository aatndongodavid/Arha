# Journal des changements

## 0.2.0 · en cours · Alignement sur le cahier des charges v1.2

- Grille commerciale v1.2 : Découverte, Pass Mémoire, Pro, Équipe, Terrain, Institution ; commission et formats
  d'export par offre ; Pionnier limité aux offres listées ; remise associative retirée.
- Achat du Pass Mémoire par Mobile Money sur le compte marchand d'Arha, activation de 120 jours, expiration
  sans renouvellement, facture numérotée.
- Noms de variables (`varName`) générés, uniques sans tenir compte de la casse, compatibles SPSS, Stata et R,
  modifiables dans l'éditeur ; codes de modalités stables, jamais renumérotés ; valeurs manquantes déclarées
  (98 « Ne sait pas », 99 « Refus de répondre ») ; contrôle bloquant à la publication.
- Nouveaux blocs : matrice de Likert, point GPS, photo, code-barres, dans l'éditeur, le formulaire public et les
  deux moteurs de logique. Suite de conformité portée à 369 cas.

## 0.1.0 · 13 novembre 2026 · MVP

- API FastAPI : identité, organisations, formulaires, logique, réponses, encaissement, billets, facturation,
  exports, webhooks, console interne.
- Formulaire public Preact (26 Ko compressés), hors ligne, paiement Mobile Money.
- Application de gestion React : éditeur, réponses, résultats, encaissements, équipe, offre, scan, console.
- Site vitrine Astro avec tarifs lus dans `config/plans.yaml`.
- Infrastructure : Dockerfiles, Compose, Caddy, durcissement, sauvegardes, CI et CD GitHub Actions.
