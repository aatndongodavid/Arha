# Runbook · Rotation des secrets

- **Clés des agrégateurs, SMTP, OAuth** : générer la nouvelle valeur chez le fournisseur, mettre à jour
  `infra/secrets/prod.enc.env` avec `sops`, déployer, révoquer l'ancienne valeur.
- **`MASTER_KEY`** : chiffre les clés de données des organisations, les secrets TOTP et les secrets de webhook.
  La rotation exige un script de rechiffrement (à écrire avant le lancement). Ne jamais la changer sans ce script.
- **`TICKET_SIGNING_KEY`** : une rotation invalide les billets déjà émis. La planifier entre deux événements.
- **Mots de passe PostgreSQL** : `ALTER ROLE ... PASSWORD`, puis mise à jour des URL dans les secrets.
