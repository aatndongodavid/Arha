# ADR 0002 · Isolation des organisations par RLS

Statut : acceptée · 13 novembre 2026

## Décision
- Chaque table métier porte `organization_id` avec `DEFAULT app_org()`. La RLS est activée et **forcée**.
- Trois rôles PostgreSQL : `arha_owner` (migrations), `arha_app` (application, sans `BYPASSRLS`),
  `arha_platform` (console interne, rapprochement, tâches multi-organisations, avec `BYPASSRLS`).
- Chaque transaction fixe `app.organization_id` et `app.user_id` par `set_config(..., true)` (équivalent de
  `SET LOCAL`).
- Les routes publiques et les webhooks trouvent l'organisation par la fonction `resolve_org(kind, key)`,
  `SECURITY DEFINER`, propriété de `arha_platform`. Elle ne renvoie qu'un identifiant d'organisation.

## Conséquences apprises pendant la réalisation
- `FORCE ROW LEVEL SECURITY` filtre aussi le propriétaire des tables. Les jeux d'essai passent par `arha_platform`.
- Une vérification d'unicité globale (slug d'organisation) ne peut pas se faire par une requête applicative : elle
  passe par `resolve_org`. Un test couvre ce cas.
- Les événements d'audit sans organisation (connexion) sont visibles de leur seul auteur.

## Vérification
`tests/test_isolation.py` parcourt toutes les routes d'organisation avec la session d'une autre organisation et
exige 403 ou 404. Il vérifie aussi que `arha_app` ne voit aucune ligne sans contexte.
