# Secrets

Aucun secret en clair dans ce dossier. Chaque environnement a un fichier `staging.enc.env` ou `prod.enc.env`
chiffré avec SOPS et age (`sops -e -i infra/secrets/prod.enc.env`). Le déploiement le déchiffre dans
`/run/arha/env` (tmpfs). Rotation : voir `docs/runbooks/rotation-des-secrets.md`.
