# Audit AgriSmart (besoins en eau) et météo — octobre 2026

Référence : FAO-56 (Allen et al., 1998), CROPWAT (FAO), NASA POWER (community=ag).

## 1. Besoins en eau — défauts corrigés

| # | Avant | Problème | Après |
|---|---|---|---|
| 1 | Kc fixé pour les 12 mois (culture présente toute l'année, Kc « initial » de décembre à mars) | Pas un cycle cultural ; besoins de saison sèche sous-estimés | Courbe Kc FAO-56 par stade (ini/dév/mi/fin), jour par jour, à partir du **mois de repiquage** (nouveau champ `planting_month`, défaut novembre) |
| 2 | Réserve du sol (RFU) remise à plein **chaque mois** | Le même stock d'eau compté jusqu'à 12 fois | Réserve pleine au repiquage, consommée puis rechargée par les excédents de pluie (bilan reporté) |
| 3 | Pluie efficace `0,85P + 3 si P > 17` | Formule non reconnue | USDA SCS (formule CROPWAT) : `P(125−0,2P)/125` si P ≤ 250 mm, sinon `125 + 0,1P` |
| 4 | « Rendement optimal » = +15 % de l'ETM chaque mois pluvieux | Coefficient sans source | Remplacé par la **marge année sèche** : pluie fiable 4 ans sur 5 (FAO : `0,6P−10` / `0,8P−24`) |
| 5 | Pompe : volume de pointe / 30 j | Mois de 31 j ou 28 j ignorés ; dimensionnement sur un supplément arbitraire | Volume de pointe de l'année sèche / jours réels du mois / 12 h |
| 6 | Penman-Monteith : `es = e°(Tmoy)` | Sous-estime le déficit de vapeur (FAO-56 éq. 12) | `es = [e°(Tmax) + e°(Tmin)] / 2` |
| 7 | Penman-Monteith : `Rso = 0,75·Rs + 0,1` | Rso dérivé de Rs lui-même : rayonnement net de grande longueur d'onde faussé | `Rso = (0,75 + 2·10⁻⁵ z)·Ra`, Ra calculé (latitude, jour ; éq. 21–25), Rs/Rso ≤ 1 |
| 8 | G = 0, γ fixe | Simplifications | G mensuel (éq. 43), γ selon l'altitude |

Paramètres culturaux : FAO-56 tableaux 11, 12, 22 ; profondeur racinaire
maximale prise au bas de la fourchette (maraîchage, irrigation localisée).
Gombo : hors FAO-56, valeurs régionales à valider.

**Effet mesuré** (tomate, 1 000 m², goutte-à-goutte, sol limoneux,
repiquage en novembre) :

| Région | Avant | Après (année normale) | Après (année sèche) |
|---|---|---|---|
| Kara | 346 m³ | 735 m³ | 766 m³ |
| Maritime | 303 m³ | 462 m³ | 576 m³ |
| Savanes | 500 m³ | 881 m³ | 900 m³ |

L'ancien calcul sous-estimait d'un facteur 1,5 à 2 les besoins du maraîchage
de saison sèche. ETo de mars à Kara : 4,65 → 6,27 mm/j, plus conforme aux valeurs habituelles du nord du Togo en saison sèche.

Tests : `tests/test_agrismart_fao56.py` (formules, courbe Kc, réserve comptée
une seule fois, année sèche ≥ année normale, pompe, Ra et ETo).

## 2. Météo (FaîtiereHub, lib/weather/open-meteo.ts) — défauts corrigés

| Avant | Problème | Après |
|---|---|---|
| Valeur absente de l'API → 0 | ECMWF ne fournit pas de probabilité de pluie : 0 entrait dans la moyenne ; idem humidité, pluie | Valeur absente ignorée ; moyenne des seuls modèles disponibles |
| Probabilité = **maximum** des modèles | Gonfle les alertes de pluie | Moyenne des modèles qui la fournissent ; à défaut, part des modèles annonçant ≥ 1 mm |
| Pluie = 70 % moyenne + 30 % maximum | Biais vers le haut sans base de vérification | Moyenne des modèles |
| Poids 0,45 / 0,35 / 0,20 | Aucune vérification locale | Poids égaux tant qu'aucun score local n'existe |
| Saisonnier : « Bonne / Normale / Sèche » par seuils fixes (150, 80 mm) | « Sèche » pour décembre, sec par nature | Lecture par rapport à la normale du mois et de la région (± 20 %) ; mois normalement secs affichés « saison sèche » ; fiabilité limitée signalée |

## 3. Limites restantes (recommandations)

- **Probabilité de pluie** : la bonne méthode est la fraction des membres
  d'ensemble (API Ensemble d'Open-Meteo : IFS 51, GEFS 31, ICON-EPS 40 membres)
  dépassant 1 mm. À intégrer.
- **Vérification locale** des modèles (stations, CHIRPS, ERA5) avant tout poids
  inégal.
- **Ajustement climatique de Kc mi/fin** (FAO-56 éq. 62 : vent, HRmin) non
  appliqué : HRmin non disponible en climatologie.
- **ea** : NASA POWER fournit T2MDEW ; `ea = e°(Tdew)` serait plus précis que
  l'humidité relative moyenne.
- **Prévision saisonnière** : afficher en terciles par rapport à la
  climatologie du modèle lui-même (CFS ou SEAS5), pas en millimètres.
