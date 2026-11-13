# ADR 0004 · Partitionnement futur de `submissions`

Statut : proposée · 13 novembre 2026

`submissions` passera en partitionnement mensuel par `submitted_at` au-delà de 10 millions de lignes.
Préparation dès maintenant : la pagination utilise l'index `(form_id, started_at, id)`, aucune clé étrangère
entrante n'impose la table non partitionnée hormis `payments`, `tickets` et `submission_events`, qui seront
migrées vers une clé composite. La migration se fera en deux temps (nouvelle table partitionnée, copie par lots,
bascule), conformément à la règle des migrations compatibles.
