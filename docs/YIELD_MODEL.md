# Rendement attendu — modèle FAO-33 relatif (v1, octobre 2026)

Code : `app/agrismart/yield_estimate.py` · API : `GET|POST /api/v1/yield/estimate`
· Tests : `tests/test_yield_estimate.py`.

## Pourquoi l'ancien modèle est retiré

`app/ml/crop_yield.py` entraînait une forêt aléatoire et XGBoost sur des
parcelles **fictives** (rendements saisis à la main + formule + bruit aléatoire).
Le R² affiché mesurait sa capacité à réapprendre la formule, pas à prédire. Il
n'est plus utilisé par l'assistant ; il reste marqué « déprécié ».

## Méthode

Fonction de production en eau FAO-33 (Doorenbos & Kassam, 1979 ; FAO-66, ch. 2) :

    1 − Ya/Ym = Ky · (1 − ETa/ETc)

- **ETc et déficit** : bilan hydrique FAO-56 d'AgriSmart (Kc par stade à partir
  du mois de semis, réserve du sol reportée, pluie efficace USDA SCS ; année
  sèche = pluie fiable 4 ans sur 5). ETa = ETc − déficit ; irrigué : ETa = ETc.
- **Formulation relative** : le potentiel Ym d'un petit exploitant n'est pas
  connu (l'écart est surtout dû à la fertilité, van Ittersum et al. 2016). On
  part du rendement moyen national observé Yref et on ne fait varier que la
  part due à l'eau :

      Ya = Yref × f(WSI_parcelle) / f(WSI_national),   f(w) = 1 − Ky(1 − w)

  WSI_national = moyenne des 5 régions en pluvial, semis typique.
- **Entrées parcelle** : culture, région ou GPS (NASA POWER, normales 30 ans),
  type de sol (réserve utile ROSETTA), irrigation, mois de semis, surface.
- **Sortie** : t/ha année normale et année sèche, fourchette (incertitude
  ±25 % si Yref vérifié, ±40 % sinon), satisfaction des besoins en eau,
  production attendue pour la surface, méthode, sources, limites.

## Références et statut

| Culture | Yref (t/ha) | Statut | Source |
|---|---|---|---|
| Maïs | 1,23 | vérifié | ITRA/ICAT fiche maïs 2019 |
| Sorgho, Mil | 0,84 | vérifié | Togo First, campagne 2023/24 (sorgho + mil) |
| Soja 0,9 · Arachide 0,9 · Niébé 0,7 | — | à vérifier | FAOSTAT QCL (ordre de grandeur) |
| Tomate 7,5 · Oignon 12 · Piment 4,5 · Gombo 4 | — | à vérifier | forte incertitude |

Ky (FAO-33) : maïs 1,25 ; sorgho 0,9 ; soja 0,85 ; arachide 0,70 ; haricot/niébé
1,15 ; tomate 1,05 ; oignon 1,1 ; poivron/piment 1,1 ; chou 0,95 ; pastèque 1,1.
Mil, laitue, carotte, concombre, aubergine, gombo : valeurs « hypothèse »
(culture voisine), signalées dans la réponse.

## Limites (renvoyées avec chaque estimation)

1. Fertilité, ravageurs, variété non modélisés.
2. Référence nationale : aucune statistique régionale publique récupérée.
3. Relation linéaire valable pour un déficit en eau < 50 %.
4. **Pas mensuel sur normales climatiques** : les poches de sécheresse à
   l'intérieur d'un mois ne sont pas vues ; l'écart année normale / sèche est
   donc sous-estimé en saison des pluies.
5. **Non validé localement** : aucun rendement observé disponible.

## Validation (procédure)

`validate(observations)` compare l'estimation aux rendements observés (t/ha)
et publie n, MAPE, RMSE, biais. Sources d'observations prévues :
productions déclarées rattachées à une parcelle (FaîtiereHub), statistiques
DSID/FAOSTAT par préfecture. Objectif d'usage commercial : erreur relative
< 30 % sur au moins 2 campagnes, validation en laissant une année de côté.

## Prochaines étapes

1. Télécharger FAOSTAT QCL (Togo, 2018–2023) et l'annuaire DSID pour passer
   toutes les références au statut « vérifié » et ajouter des Yref régionaux.
2. Suivi en cours de saison : bilan décadaire avec la pluie réellement tombée
   (indice de satisfaction des besoins en eau type WRSI, CHIRPS/Open-Meteo).
3. Relier les productions aux parcelles pour mesurer l'erreur réelle.
