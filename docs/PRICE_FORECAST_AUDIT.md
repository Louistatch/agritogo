# Audit du modèle de prévision des prix — octobre 2026

Périmètre : `app/ml/price_forecast.py` (prévision 1–4 semaines), données
`market_prices`, pipeline d'ingestion SIM-CPC (`app/ingestion/`,
`.github/workflows/cpc-market-ingestion.yml`). Évaluation refaite sur la base
de production (1 564 relevés SIM-CPC, 27 marchés, 8 produits, 11/01 → 02/10/2026).

## 1. Source et pipeline — conformes

| Point | Constat |
|---|---|
| Provenance | API officielle CPC (`apicpc.cpc-togo.com/.../getAllValidation`) : seuls les relevés **validés** ; chaque relevé porte n° de fiche, enquêteur, superviseur, `dateCollecte`, `dateValidation`. |
| Date | `observed_at` = date de collecte terrain (pas la date d'enregistrement). Décalage moyen collecte → ingestion : 118 jours (historique rattrapé). |
| Traçabilité | payload brut conservé (`market_raw_payloads`), staging (`market_price_staging`), promotion idempotente par `record_hash`, doublons marqués `superseded` (jamais supprimés). |
| Contrôle qualité | score qualité par relevé ; détection robuste d'anomalies (médiane/MAD par marché-produit-unité) ; unité normalisée en FCFA/kg. |
| Fréquence | toutes les 6 h (GitHub Actions). |

## 2. Défauts trouvés et corrigés

1. **Mélange de sources.** 424 prix `manual` (sans date d'observation, sans
   protocole, unités kg/litre/m³) étaient agrégés avec le SIM. Maïs : médiane
   214 FCFA/kg (manuel) contre 135 (CPC), +58 %. → La prévision n'utilise plus
   que des relevés datés en FCFA/kg.
2. **Biais de composition.** L'indice de zone était la médiane des marchés
   présents : un marché cher absent une semaine faisait « baisser » la zone.
   → Indice à effets fixes marché (log p = a[marché] + b[semaine], médianes
   itérées). Bruit de l'indice réduit d'environ 20 % (erreur naïve à 1 semaine
   6,2 % → 5,0 %).
3. **Validation trop courte et optimiste.** 8 plis seulement ; le gain annoncé
   (MAPE 8,6 % contre 10,0 % au naïf) **n'est pas reproduit** sur toutes les
   origines glissantes : 8,6 % contre 8,7 %, le modèle ne bat le naïf que dans
   45 % des cas. → Validation sur toutes les origines (≥ 8 semaines
   d'apprentissage), MASE (Hyndman & Koehler, 2006) en plus du MAPE, semaines
   reportées exclues des cibles.
4. **Intervalle mal calibré.** 1,2816·σ·√h avec σ des résidus in-sample :
   couverture réelle 76 % à 1 semaine, 89 % à 4 semaines. → Quantiles
   empiriques des erreurs hors échantillon. Quantiles 10/90 % : 72,9 %
   (sous-couverture de petit échantillon) ; 5/95 % retenus : **78,7 %** mesurés
   hors échantillon (221 tests). La couverture est publiée avec chaque prévision.
5. **Confiance non fondée.** → « moyenne » si gain ≥ 5 % sur le naïf (≥ 10
   plis), « élevée » si ≥ 15 % (≥ 20 plis), sinon « faible » ; le Conseiller
   marché ne donne alors aucun conseil de stockage ou d'attente.

## 3. Modèle retenu et résultat

Moyenne naïf + lissage simple + Holt amorti sur log-prix (famille du benchmark
« Comb » de M4, Makridakis et al., 2020). Résultat sur 20 séries
culture × région : MAPE 4 semaines 7,6 % (naïf 7,5 %), gain médian ≈ 0.
Confiance : 13 faible, 5 moyenne, 2 élevée (Gari-Kara, Riz-Centrale).

**Conclusion honnête :** à 1–4 semaines, les prix SIM du Togo se comportent
quasiment comme une marche aléatoire ; aucun modèle testé ne bat nettement
« le prix ne bouge pas ». C'est conforme à la littérature (le naïf est le
meilleur à 1 mois dans plusieurs études sur produits agricoles). La valeur
utile pour le producteur est surtout : prix actuel fiable, écart entre
marchés, fourchette d'incertitude calibrée.

## 4. Limites restantes (non corrigées ici)

- **Saisonnalité** : 38 semaines de données ; il faut 2 à 3 ans au minimum
  (FEWS NET : moyenne 5 ans). Aucun facteur saisonnier n'est estimé.
- **Variétés fusionnées** (haricot blanc/rouge, maïs blanc/jaune, riz
  étuvé/local) : l'indice par marché × variété a été testé, sans gain mesurable
  (bruit 2,71 % contre 2,64 %) ; à revoir pour l'affichage des prix.
- **Type de prix** (gros/détail) non fourni par CPC (`price_type = unknown`).
- **Inflation et interventions ANSAT** non modélisées.
- Les vues `market_price_current` / `market_price_scoped` de FaîtiereHub
  utilisent encore la médiane des marchés pour la tendance affichée.

## Références

- Hyndman & Athanasopoulos, *Forecasting: Principles and Practice* (3e éd.) :
  validation croisée temporelle, intervalles — https://otexts.com/fpp3/
- Hyndman & Koehler (2006), *Another look at measures of forecast accuracy*,
  IJF — https://doi.org/10.1016/j.ijforecast.2006.03.001
- Makridakis, Spiliotis & Assimakopoulos (2020), *The M4 Competition*, IJF —
  https://doi.org/10.1016/j.ijforecast.2019.04.014
- FEWS NET, *Guidance on price projections* (2018) —
  https://fews.net/sites/default/files/documents/reports/Guidance_Document_Price_Projections_2018.pdf
- WFP, *Market Analysis Guidelines* — https://www.wfp.org/publications/market-analysis-guidelines
- WFP ALPS (alerte sur prix) — https://dataviz.vam.wfp.org/GuineaBissau/economic/how-it-works
- Prévision de prix agricoles, naïf difficile à battre à 1 mois —
  https://link.springer.com/article/10.1007/s44564-026-00015-0 ;
  https://www.mdpi.com/2571-9394/8/5/92
