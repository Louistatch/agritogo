"""
Rendement attendu — fonction de production en eau FAO-33 (Doorenbos & Kassam,
1979), sur le bilan hydrique FAO-56 d'AgriSmart.

    1 − Ya/Ym = Ky · (1 − ETa/ETc)          (FAO-33 ; rappelée dans FAO-66 ch. 2)

ETc (besoin de la culture) et le déficit non couvert par la pluie viennent du
bilan FAO-56 (app.agrismart.irrigation) : ETa = ETc − déficit. Pour une
parcelle irriguée, le déficit est considéré comme couvert (ETa = ETc).

POURQUOI UNE FORMULATION RELATIVE. Le rendement « sans stress » Ym d'un petit
exploitant n'est pas connu au Togo : l'écart au potentiel est surtout dû à la
fertilité et aux pratiques, pas à l'eau (van Ittersum et al., 2016, PNAS). On
part donc du RENDEMENT MOYEN NATIONAL observé (Yref, sourcé) et on ne fait
varier que la part expliquée par l'eau :

    Ya(parcelle) = Yref × f(WSI_parcelle) / f(WSI_national),  f(w) = 1 − Ky(1 − w)

où WSI = ETa/ETc (indice de satisfaction des besoins en eau) et WSI_national
la moyenne des 5 régions pour le même calendrier. Une région plus sèche que la
moyenne obtient moins que Yref ; une parcelle irriguée un peu plus.

Limites (affichées avec chaque résultat) :
  - relation linéaire valable pour un déficit < ~50 % (FAO-66) ;
  - ni fertilité, ni ravageurs, ni variété ;
  - Yref national (aucune statistique régionale publique récupérée) ;
  - NON VALIDÉ LOCALEMENT tant qu'aucun rendement observé n'est disponible
    (productions déclarées rattachées à une parcelle) — voir validate().
"""

from __future__ import annotations

from app.agrismart.climate_normals import REGION_COORDS, get_nasa_climatology, get_region_climatology
from app.agrismart.irrigation import compute_monthly_needs
from app.agrismart.kc_values import CROPS

MODEL = "fao33-relatif-v1"

# Ky saisonnier — FAO-33, repris dans FAO-66 ch. 2 (https://www.fao.org/4/i2800e/i2800e02.pdf).
# « hypothèse » : culture absente de la table, valeur d'une culture voisine.
KY = {
    "Maïs": (1.25, "FAO-33"), "Sorgho": (0.90, "FAO-33"), "Mil": (0.90, "hypothèse (= sorgho)"),
    "Soja": (0.85, "FAO-33"), "Arachide": (0.70, "FAO-33"), "Niébé": (1.15, "FAO-33 (haricot)"),
    "Tomate": (1.05, "FAO-33"), "Oignon": (1.10, "FAO-33"), "Piment": (1.10, "FAO-33 (poivron)"),
    "Chou": (0.95, "FAO-33"), "Pastèque": (1.10, "FAO-33"), "Laitue": (1.00, "hypothèse"),
    "Carotte": (1.00, "hypothèse"), "Concombre": (1.10, "hypothèse (= pastèque)"),
    "Aubergine": (1.10, "hypothèse (= poivron)"), "Gombo": (1.10, "hypothèse (= poivron)"),
}

# Rendement moyen national observé (t/ha). status : « vérifié » = chiffre trouvé
# dans une source publique citée ; « à vérifier » = ordre de grandeur à confirmer
# sur FAOSTAT QCL (Togo, 2018–2023) avant usage commercial.
YREF = {
    "Maïs": (1.23, "vérifié", "ITRA/ICAT, fiche maïs (2019) — https://icat.tg/wp-content/uploads/2024/09/Mais-1.pdf"),
    "Sorgho": (0.84, "vérifié", "Sorgho + mil 2023/24 — https://www.togofirst.com/fr/agro/2101-15590-agriculture-togolaise-entre-transformations-et-defis"),
    "Mil": (0.84, "vérifié", "Sorgho + mil 2023/24 — même source"),
    "Soja": (0.9, "à vérifier", "FAOSTAT (ordre de grandeur)"),
    "Arachide": (0.9, "à vérifier", "FAOSTAT (ordre de grandeur)"),
    "Niébé": (0.7, "à vérifier", "FAOSTAT (ordre de grandeur)"),
    "Tomate": (7.5, "à vérifier", "ordre de grandeur, forte incertitude"),
    "Oignon": (12.0, "à vérifier", "ordre de grandeur, forte incertitude"),
    "Piment": (4.5, "à vérifier", "ordre de grandeur, forte incertitude"),
    "Gombo": (4.0, "à vérifier", "ordre de grandeur, forte incertitude"),
}

# Repiquage / semis pluvial typique (saison principale) si non précisé.
DEFAULT_RAINFED_PLANTING = {"Maritime": "Avril", "Plateaux": "Avril", "Centrale": "Mai", "Kara": "Juin", "Savanes": "Juin"}
DEFAULT_IRRIGATED_PLANTING = "Novembre"

SOIL_ALIASES = {
    "sableux": "Sableux", "sablo-limoneux": "Sableux-Limoneux", "sableux-limoneux": "Sableux-Limoneux",
    "limoneux": "Limoneux", "argilo-limoneux": "Argilo-Limoneux", "argileux": "Argileux",
}
SOIL_RU = {"Sableux": 84, "Sableux-Limoneux": 103, "Limoneux": 125, "Argilo-Limoneux": 145, "Argileux": 155}
RAINFED = {"", "pluviale", "pluvial", "aucune", "non", "none"}
UNCERTAINTY = {"vérifié": 0.25, "à vérifier": 0.40}


def _norm_crop(name: str) -> str | None:
    key = (name or "").strip().lower()
    for crop in KY:
        if crop.lower() == key or crop.lower().replace("ï", "i").replace("é", "e") == key.replace("ï", "i").replace("é", "e"):
            return crop
    aliases = {"mais": "Maïs", "poivron": "Piment", "haricot": "Niébé", "niebe": "Niébé"}
    return aliases.get(key)


def _wsi(crop: str, soil_ru: float, climate: dict, planting: str, irrigated: bool, dry: bool) -> float:
    rows = compute_monthly_needs(crop, 10_000, soil_ru, "Goutte à goutte", climate, planting)
    etc = sum(r["etm"] for r in rows)
    if etc <= 0:
        return 1.0
    if irrigated:
        return 1.0
    deficit = sum(r["besoin_net"] + (r["boost_mm"] if dry else 0) for r in rows)
    return max(0.0, min(1.0, (etc - deficit) / etc))


def _f(ky: float, wsi: float) -> float:
    return max(0.0, 1 - ky * (1 - wsi))


def estimate(
    crop_name: str,
    region: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    soil_type: str | None = None,
    irrigation: str | None = None,
    planting_month: str | None = None,
    area_ha: float | None = None,
) -> dict:
    crop = _norm_crop(crop_name)
    if not crop or crop not in CROPS:
        return {"ok": False, "reason": f"culture non prise en charge : {crop_name}"}
    if crop not in YREF:
        return {"ok": False, "reason": f"aucun rendement de référence sourcé pour {crop}"}

    irrigated = (irrigation or "").strip().lower() not in RAINFED
    region = region.capitalize() if region else None
    if region not in REGION_COORDS:
        region = None
    if lat is not None and lon is not None:
        climate = get_nasa_climatology(float(lat), float(lon))
    elif region:
        climate = get_region_climatology(region)
    else:
        return {"ok": False, "reason": "localisation inconnue (région ou GPS requis)"}

    soil = SOIL_ALIASES.get((soil_type or "").strip().lower(), "Limoneux")
    planting = planting_month or (DEFAULT_IRRIGATED_PLANTING if irrigated else DEFAULT_RAINFED_PLANTING.get(region or "Centrale", "Mai"))
    ky, ky_src = KY[crop]
    yref, status, source = YREF[crop]

    # Référence nationale : satisfaction en eau moyenne des 5 régions, en pluvial.
    nat = [
        _wsi(crop, SOIL_RU["Limoneux"], get_region_climatology(r), DEFAULT_RAINFED_PLANTING[r], False, False)
        for r in REGION_COORDS
    ]
    wsi_nat = sum(nat) / len(nat)
    base = _f(ky, wsi_nat) or 1e-6

    wsi_normal = _wsi(crop, SOIL_RU[soil], climate, planting, irrigated, False)
    wsi_dry = _wsi(crop, SOIL_RU[soil], climate, planting, irrigated, True)
    y_normal = yref * _f(ky, wsi_normal) / base
    y_dry = yref * _f(ky, wsi_dry) / base
    u = UNCERTAINTY[status]

    def t(x: float) -> float:
        return round(x, 2)

    out = {
        "ok": True,
        "crop": crop,
        "region": region,
        "soil": soil,
        "irrigated": irrigated,
        "planting_month": planting,
        "yield_t_ha": {
            "annee_normale": t(y_normal),
            "annee_seche": t(y_dry),
            "fourchette": [t(y_dry * (1 - u)), t(y_normal * (1 + u))],
        },
        "water_satisfaction_pct": {"annee_normale": round(wsi_normal * 100), "annee_seche": round(wsi_dry * 100)},
        "method": {
            "model": MODEL,
            "equation": "Ya = Yref × [1 − Ky(1 − ETa/ETc)] / [1 − Ky(1 − WSI_national)]",
            "ky": ky,
            "ky_source": ky_src,
            "yref_t_ha": yref,
            "yref_status": status,
            "yref_source": source,
            "climate_source": climate.get("source"),
            "validated_locally": False,
            "limits": [
                "Fertilité, ravageurs et variété non pris en compte",
                "Rendement de référence national (pas de statistique régionale publique)",
                "Relation FAO-33 valable pour un déficit en eau < 50 %",
                "Non validé localement : aucun rendement observé encore disponible",
            ],
        },
    }
    if area_ha:
        out["production_t"] = {
            "annee_normale": t(y_normal * area_ha),
            "annee_seche": t(y_dry * area_ha),
        }
    return out


def validate(observations: list[dict]) -> dict:
    """Compare estimations et rendements observés (t/ha).

    observations : [{crop, region, soil_type, irrigation, planting_month, observed_t_ha}].
    Renvoie n, MAPE, RMSE, biais — à publier avec le modèle dès que n est suffisant.
    """
    pairs = []
    for o in observations:
        e = estimate(o["crop"], region=o.get("region"), soil_type=o.get("soil_type"),
                     irrigation=o.get("irrigation"), planting_month=o.get("planting_month"))
        if e.get("ok") and o.get("observed_t_ha"):
            pairs.append((e["yield_t_ha"]["annee_normale"], float(o["observed_t_ha"])))
    n = len(pairs)
    if n == 0:
        return {"n": 0, "message": "aucun rendement observé : modèle non validé localement"}
    mape = sum(abs(p - a) / a for p, a in pairs) / n * 100
    rmse = (sum((p - a) ** 2 for p, a in pairs) / n) ** 0.5
    bias = sum(p - a for p, a in pairs) / n
    return {"n": n, "mape_pct": round(mape, 1), "rmse_t_ha": round(rmse, 2), "bias_t_ha": round(bias, 2)}
