# ADR 0005 · Grille commerciale v1.2

Statut : acceptée · 14 novembre 2026

## Décision
`config/plans.yaml` reprend les valeurs de référence de la section 11 du master prompt v1.2 :
Découverte (gratuite, 500 réponses par mois), Pass Mémoire (5 000 FCFA, 120 jours, 3 000 réponses au total,
sans renouvellement), Pro, Équipe, Terrain, Institution. La commission de chaque offre est `payment_fee_bps`.
Les formats d'export autorisés sont listés par offre (`exports`).

## Écarts aux valeurs de référence
- `institution` reçoit `inherits: terrain`. Sans cela, l'offre la plus haute n'aurait aucune fonctionnalité et
  ses propriétaires échapperaient à la double authentification obligatoire (S-03). À valider par le porteur.

## Conséquences
- Les codes d'offre changent : `discovery` devient `decouverte`, `business` devient `equipe`, `enterprise`
  devient `institution` (migration 0003).
- La remise associative disparaît (règle E-02).
- L'offre Pionnier ne s'applique qu'aux offres listées dans `pioneer.plans`.
- Le Pass Mémoire est une vente d'Arha, encaissée sur son compte marchand, sans compte connecté (section 9.0).
  Un nouveau Pass remet à zéro le quota total ; un Pass acheté pendant un Pass actif le prolonge.
- Le Programme Encadreur (E-07) est décrit dans la configuration. Son attribution dépend des liens de relecture
  et sera livrée avec le chantier F.
