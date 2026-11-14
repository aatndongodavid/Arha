# ADR 0003 · Encaissement sans détention de fonds

Statut : acceptée · 13 novembre 2026

## Décision
Arha est un prestataire technique. Les paiements des répondants sont réglés sur le compte connecté de
l'organisation chez l'agrégateur. La commission d'Arha est prélevée par l'agrégateur (frais de plateforme).
Aucun flux ne crédite un compte d'Arha pour reverser ensuite (règlement 04/18/CEMAC/UMAC/COBAC).

## Mise en œuvre
- `PaymentProvider` (interface), `FakeNotchPay` (tests et développement), `NotchPay`, `Campay`.
- Un formulaire payant ne se publie pas sans compte connecté vérifié (hors simulateur).
- Le simulateur est refusé quand `ARHA_ENV=prod`.
- L'abonnement à Arha est le seul paiement sans compte connecté : c'est le chiffre d'affaires d'Arha.
- Avec Campay (secours, sans partage de commission), la commission est comptée dans `usage_counters`
  (`platform_fee_due`) pour une facturation mensuelle.
- L'appel au fournisseur se fait toujours hors transaction. Le paiement est créé et validé avant l'appel.
- Un succès tardif après expiration est accepté et signalé par une alerte : de l'argent réel n'est jamais perdu.

## Points à vérifier avant tout paiement réel
Les adaptateurs Notch Pay et Campay ont été écrits **sans accès à la documentation officielle** (hôte bloqué par
le réseau de la session). Chaque champ est marqué `# VERIFY:`. Voir `docs/PROGRESS.md`.
