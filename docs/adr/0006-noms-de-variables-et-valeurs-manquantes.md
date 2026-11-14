# ADR 0006 · Noms de variables, codes de modalités et valeurs manquantes

Date : 14 novembre 2026. Statut : proposé, à valider par le porteur.

## Contexte

Le cahier des charges v1.2 (section 7, F-EDI-12) exige un nom de variable compatible SPSS, Stata et R pour chaque
question, un code numérique stable par modalité et des valeurs manquantes déclarées.

## Décisions

1. **Champ `varName`.** Il remplace `variableName`. La migration 0004 renomme le champ dans les brouillons existants.
   Le serveur génère le nom à partir du libellé quand il manque, puis renvoie le schéma normalisé à l'éditeur.
2. **Unicité sans tenir compte de la casse**, expansions comprises (`q5_1`, `gps_lat`, ...), car Stata et R
   distinguent la casse mais SPSS non. Les mots réservés des trois logiciels sont refusés.
3. **Modalités sous `options`, avec `code`.** Le cahier des charges écrit `choices`. Nous gardons `options` pour ne
   pas casser les schémas publiés du MVP ; seul le nom du champ diffère.
4. **Codes stables.** Un code absent reçoit le maximum existant plus un. Un code n'est jamais renuméroté, même après
   suppression ou réordonnancement d'une modalité.
5. **Valeur manquante déclarée** stockée sous la forme `{"missing": 98}`. Le serveur et le navigateur la refusent si
   le code n'est pas déclaré sur la question (`invalid_missing`). Une valeur manquante satisfait l'obligation de
   réponse.

## Conséquences

Les exports du chantier D lisent `varName` et `missingCodes` sans transformation. Point ouvert : les métadonnées
`_start`, `_end` de la section 8 bis commencent par un souligné, interdit par SPSS ; le chantier D proposera un
préfixe conforme.
