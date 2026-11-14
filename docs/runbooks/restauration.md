# Runbook · Restauration

Objectif : perte maximale de 15 minutes, reprise complète en moins de 4 heures.

1. Provisionner un serveur et lancer `infra/hardening/harden.sh`.
2. Déchiffrer les secrets : `sops -d infra/secrets/prod.enc.env > /run/arha/env`.
3. Restaurer PostgreSQL : `wal-g backup-fetch /var/lib/arha/postgres LATEST`, créer `recovery.signal`, démarrer.
4. Restaurer les fichiers : `restic restore latest --tag arha-files --target /`.
5. Démarrer la pile : `docker compose -f infra/compose/docker-compose.prod.yml up -d`.
6. Vérifier `/healthz`, une connexion, un formulaire public, le rapprochement des paiements.

Le test mensuel est automatisé par `infra/backup/restore-test.sh`. Non exécuté à ce jour sur un serveur réel.
