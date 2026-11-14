# Écarts entre le MVP (construit sur la v1.0) et le cahier des charges v1.2

Établi le 14 novembre 2026, par comparaison du master prompt v1.0 et v1.2 et des tableaux d'exigences des
sources LaTeX. Le MVP de la branche `claude/arha-mvp` suit la v1.0.

## Ce qui change dans la vision

La v1.2 fait d'Arha un produit à **deux moteurs** livrés dès la V1 : **Collecte** (questionnaires, mode
enquêteur hors ligne, contrôle qualité, exports statistiques) et **Encaissement** (le MVP actuel). Le moteur
Collecte devient la porte d'entrée principale : étudiants en mémoire, enseignants-chercheurs, cabinets d'études.
Nouvelle signature : « Concevoir. Collecter. Encaisser. Comprendre. » Bêta le 1er mars 2027, lancement le
16 mars 2027.

## Déjà conforme, à garder tel quel

F-AUT-01 et 03, F-ORG-01, 03 et 04, F-EDI-01 à 06 et 08 à 10, F-LOG-01 à 03 et 05, F-PUB-01 à 09,
F-PAY-01 à 10, F-REP-01 à 03, 06 et 07, F-NOT-01 et 02, F-ADM-01 à 03, règles 1 à 13, S-01 à S-05, S-11,
S-16, S-19, S-20. La RLS, le moteur de logique partagé, l'idempotence et la machine à états des paiements ne
bougent pas.

## Écarts, regroupés par chantier

| # | Chantier | Exigences | Ampleur | Ce qu'il faut faire |
|---|---|---|---|---|
| A | Configuration commerciale | F-FAC-01 à 06, section 11 | Moyenne | Renommer les offres (`decouverte`, `pass_memoire`, `pro`, `equipe`, `terrain`, `institution`), nouveau format (`responses.per_month` ou `total`, `exports`, `payment_fee_bps`, relecteurs, enquêteurs), Pass Mémoire (5 000 FCFA, 120 jours, sans renouvellement), Programme Encadreur, Pionnier limité à certaines offres, suppression de la remise associative, catalogue Arha Services et Arha Études. Découverte passe à 500 réponses par mois. |
| B | Noms de variables et codes | F-EDI-12, section 7 | Moyenne | `varName` obligatoire, généré, unique, compatible SPSS, Stata et R ; `code` stable par modalité ; `missingCodes` (98, 99). Migration des formulaires existants. |
| C | Nouveaux blocs | section 7 | Moyenne | `likert_matrix`, `geopoint`, `photo`, `barcode` dans le schéma, les deux moteurs, les cas de conformité, l'éditeur et le formulaire public. |
| D | Exports statistiques (fonctionnalité phare) | F-REP-04, F-REP-08, F-ANA-03, F-ANA-04, section 8 bis | Grande | Script `import.R`, choix codes ou libellés, valeurs manquantes déclarées, niveaux de mesure, variables de métadonnées (`_start`, `_duration_s`, `_lat`...), dictionnaire Excel et PDF, export anonyme, écart-type et valeurs manquantes, tableaux croisés avec pourcentages en ligne et en colonne et alerte sur les effectifs théoriques. Jeu de référence de 500 réponses. |
| E | Mode enquêteur | F-TER-01 à 07, F-ORG-02, règle 15, section 10 | Grande | Rôle `enumerator`, assignations, codes d'activation de 72 heures, application `/terrain` installable, file IndexedDB chiffrée (AES-GCM, PBKDF2 310 000 itérations), métadonnées d'entretien et GPS, synchronisation par lots qui reprend, contrôle qualité V1 et score, tableau d'avancement par enquêteur. Nouvelles colonnes sur `submissions`, tables `field_assignments` et `enumerator_devices`. |
| F | Relecture par l'encadreur | F-EDI-11 | Moyenne | Liens de relecture sans compte payant, commentaires par question, résolution un par un. Tables `review_links` et `review_comments`. |
| G | Consentement éclairé | F-PUB-10 | Petite | Un refus remercie le répondant et n'enregistre rien. |
| H | Encaissement complété | F-PAY-11, F-PAY-12, phase 7 | Moyenne | Remboursements en V1, export comptable CSV et Excel, commission lue par offre, plafonds d'encaissement pour les comptes récents. |
| I | Ventes d'Arha | F-FAC-06, F-ADM-05, section 9.0 | Moyenne | Achat du Pass Mémoire et des commandes Arha Services et Arha Études sur le compte marchand d'Arha ; suivi des commandes dans la console (statut, analyste, échéance, livrables). Tables `student_passes` et `study_orders`. |
| J | Indicateurs | F-ADM-04, règle 17, annexe 21.1 | Moyenne | Réponses valides du mois, volume encaissé, croissance et rétention nette du revenu récurrent, Pass vendus, exports du mois, réussite de la synchronisation, palier P1 révisé. |
| K | Modèles et site vitrine | F-EDI-07, chapitre 12 | Petite | Modèles méthodologiques (mémoire, enquête ménage, satisfaction, étude de marché, évaluation de formation, Likert, consentement) ; site repositionné sur les deux moteurs, avec Pass Mémoire et services. |
| L | Routage et infrastructure | section 2 | Petite | Route `f.arha.africa/terrain` dans Caddy, stockage persistant demandé par le navigateur. |

## Points qui demandent une décision du porteur

1. **Jeu de référence SPSS.** Les tests doivent comparer chaque statistique à des résultats « calculés dans
   SPSS ». SPSS n'est pas disponible dans l'environnement de réalisation. Proposition : calculer les résultats
   attendus avec une implémentation indépendante (SciPy), puis les faire confirmer une fois dans SPSS par le
   porteur.
2. **Exécution du script R.** La sortie de la phase 6 exige un script R exécuté dans un conteneur R. À vérifier
   dans la CI si l'environnement de réalisation ne dispose pas de R.
3. **Formulaires créés pendant le MVP.** La migration vers `varName` obligatoire génère des noms automatiques
   pour les formulaires existants. Aucune donnée réelle n'existe encore, le risque est nul aujourd'hui.

## Ordre de réalisation proposé

A, puis B et C, puis D, puis E, puis F et G, puis H et I, puis J, K et L. La configuration commerciale vient en
premier parce que tous les contrôles de fonctionnalités en dépendent. Les noms de variables viennent avant les
exports et le mode enquêteur, qui les utilisent tous les deux.
