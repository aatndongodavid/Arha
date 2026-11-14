# Journal des changements

## 0.2.0 · en cours · Alignement sur le cahier des charges v1.2

- Grille commerciale v1.2 : Découverte, Pass Mémoire, Pro, Équipe, Terrain, Institution ; commission et formats
  d'export par offre ; Pionnier limité aux offres listées ; remise associative retirée.
- Achat du Pass Mémoire par Mobile Money sur le compte marchand d'Arha, activation de 120 jours, expiration
  sans renouvellement, facture numérotée.

## 0.1.0 · 13 novembre 2026 · MVP

- API FastAPI : identité, organisations, formulaires, logique, réponses, encaissement, billets, facturation,
  exports, webhooks, console interne.
- Formulaire public Preact (26 Ko compressés), hors ligne, paiement Mobile Money.
- Application de gestion React : éditeur, réponses, résultats, encaissements, équipe, offre, scan, console.
- Site vitrine Astro avec tarifs lus dans `config/plans.yaml`.
- Infrastructure : Dockerfiles, Compose, Caddy, durcissement, sauvegardes, CI et CD GitHub Actions.
