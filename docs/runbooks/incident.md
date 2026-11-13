# Runbook · Incident

1. Qualifier : indisponibilité, fuite de données, fraude par formulaire, écart de paiement.
2. Contenir : suspendre le formulaire ou l'organisation depuis la console (effet immédiat), révoquer les sessions,
   couper un fournisseur de paiement par `config/countries.yaml`.
3. Informer : le porteur, puis les organisations touchées. En cas de violation de données personnelles, notifier
   l'autorité compétente dans les délais de la loi n° 2024/017.
4. Corriger, déployer, vérifier.
5. Rédiger un compte rendu daté : cause, durée, données touchées, mesures.
