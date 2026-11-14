# Sauvegardes

- PostgreSQL : WAL-G, archivage continu des journaux (`archive_timeout=900`, perte maximale de 15 minutes) et
  sauvegarde complète quotidienne par `backup.sh` (cron à 01:30 UTC).
- Fichiers : restic vers un second fournisseur de stockage objet.
- Test de restauration mensuel : `restore-test.sh` sur la préproduction, rapport dans `/var/lib/arha/reports/`.

Non vérifié dans cette session : ces scripts n'ont pas été exécutés sur un serveur réel. L'image PostgreSQL doit
embarquer `wal-g` et définir `archive_command = 'wal-g wal-push %p'`. À valider lors du premier déploiement.
