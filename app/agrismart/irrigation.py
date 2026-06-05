"""
Calcul des besoins en irrigation — FAO-56 bilan hydrique complet.

Formule de base :
  ETM        = ETP × Kc × nb_jours           (besoin évapotranspiration mm/mois)
  Peff       = pluies efficaces USDA SCS      (mm/mois)
  RU         = sol.RU × profondeur_Z          (réserve utile mm)
  RFU        = (2/3) × RU                    (réserve facilement utilisable mm)
  Bilan      = Peff + RFU - ETM
  BNet       = max(0, -Bilan)               (besoin net survie mm/mois)
  BBrut      = BNet / efficience             (besoin brut mm/mois)
  Volume     = BBrut × 10                   (m³/ha/mois)

Rendement optimal (RAG agronomique Togo) :
  Même si BNet = 0 (pluie couvre les besoins), une part de la pluie mensuelle
  est mal répartie intra-mois (CV pluie Togo ≈ 0.40). Une irrigation
  complémentaire de 15 % de l'ETM garantit le rendement maximal.

  boost_mm  = max(0.15 × ETM, 5 mm)   quand besoin_net = 0
  boost_mm  = 0                         quand besoin_net > 0  (déjà couvert)
  boost_vol = boost_mm / eff × 10      (m³/ha/mois)
"""

from app.agrismart.kc_values import KC_VALUES, IRRIGATION_SYSTEMS, MOIS, JOURS_MOIS, MOIS_TO_JAN_IDX

# Coefficient de complément rendement optimal (15 % ETM → études IRRI / Togo)
_BOOST_COEF = 0.15
_BOOST_MIN_MM = 5.0   # plancher minimal même en saison des pluies


def _pluie_efficace(p_mm: float) -> float:
    """Pluies efficaces USDA SCS (mensuel)."""
    return (0.85 * p_mm + 3) if p_mm > 17 else 0.0


def compute_monthly_needs(
    crop_name: str,
    area_m2: float,
    soil_ru: float,
    system_name: str,
    climate: dict,
) -> list[dict]:
    """
    Calcule les besoins en eau mensuels.

    Args:
        crop_name   : nom de la culture (clé de KC_VALUES)
        area_m2     : superficie en m²
        soil_ru     : RU du sol en mm/m (depuis SOIL_PROFILES)
        system_name : système d'irrigation (clé de IRRIGATION_SYSTEMS)
        climate     : dict retourné par climate_normals.get_nasa_climatology()

    Returns:
        liste de 12 dicts (un par mois Avr→Mars)
    """
    crop    = KC_VALUES[crop_name]
    eff     = IRRIGATION_SYSTEMS[system_name]["efficiency"]
    area_ha = area_m2 / 10_000

    etp_jan   = climate["etp_mensuelle"]
    pluie_jan = climate["pluie_mensuelle"]

    rows = []
    for i, mois in enumerate(MOIS):
        jan_idx  = MOIS_TO_JAN_IDX[mois]
        nb_jours = JOURS_MOIS[i]
        etp      = etp_jan[jan_idx]
        pluie    = pluie_jan[jan_idx]
        kc       = crop["kc"][i]
        z        = crop["z"][i]

        etm         = etp * kc * nb_jours
        peff        = _pluie_efficace(pluie)
        ru          = soil_ru * z
        rfu         = (2 / 3) * ru
        bilan       = (peff + rfu) - etm
        besoin_net  = max(0.0, -bilan)
        besoin_brut = besoin_net / eff
        volume_ha   = besoin_brut * 10
        volume_m2   = volume_ha * area_ha    # total m³ pour la surface

        # ── Rendement optimal ──────────────────────────────────────────
        # Mois où la pluie couvre la survie → supplément pour rendement max
        if besoin_net == 0 and etm > 0:
            boost_mm  = max(_BOOST_COEF * etm, _BOOST_MIN_MM)
        else:
            boost_mm  = 0.0
        boost_vol_ha  = (boost_mm / eff) * 10       # m³/ha
        boost_vol_m2  = boost_vol_ha * area_ha       # m³ total parcelle

        rows.append({
            "mois":            mois,
            "mois_idx":        i,
            "nb_jours":        nb_jours,
            "etp":             round(etp, 2),
            "kc":              round(kc, 2),
            "z":               round(z, 2),
            "etm":             round(etm, 1),
            "pluie":           round(pluie, 1),
            "peff":            round(peff, 1),
            "ru":              round(ru, 1),
            "rfu":             round(rfu, 1),
            "bilan":           round(bilan, 1),
            "besoin_net":      round(besoin_net, 1),
            "besoin_brut":     round(besoin_brut, 1),
            "volume_ha":       round(volume_ha, 1),
            "volume_total":    round(volume_m2, 2),
            "boost_mm":        round(boost_mm, 1),
            "boost_vol_ha":    round(boost_vol_ha, 1),
            "boost_vol_total": round(boost_vol_m2, 2),
        })

    return rows


def compute_kpis(rows: list[dict], area_m2: float, system_name: str, crop_name: str = "") -> dict:
    """Calcule les KPIs de saison à partir des lignes mensuelles."""
    area_ha        = area_m2 / 10_000
    total_m3       = sum(r["volume_total"] for r in rows)
    total_boost    = sum(r["boost_vol_total"] for r in rows)
    total_optimal  = total_m3 + total_boost
    pic            = max(rows, key=lambda r: r["volume_total"] + r["boost_vol_total"])
    pic_vol        = pic["volume_total"] + pic["boost_vol_total"]
    debit_pompe    = (pic_vol / 30 / 12) * 0.277
    avg_kc         = sum(r["kc"] for r in rows) / 12
    avg_etp        = sum(r["etp"] for r in rows) / 12
    max_besoin_net = max(r["besoin_net"] for r in rows)
    eff            = IRRIGATION_SYSTEMS[system_name]["efficiency"]
    mois_zero      = [r["mois"] for r in rows if r["besoin_net"] == 0 and r["etm"] > 0]

    return {
        "crop":             crop_name,
        "area_m2":          area_m2,
        "area_ha":          round(area_ha, 4),
        "total_m3":         round(total_m3, 1),
        "total_boost_m3":   round(total_boost, 1),
        "total_optimal_m3": round(total_optimal, 1),
        "avg_monthly_m3":   round(total_m3 / 12, 2),
        "pic_mois":         pic["mois"],
        "pic_volume_m3":    round(pic_vol, 1),
        "debit_pompe_ls":   round(debit_pompe, 3),
        "avg_kc":           round(avg_kc, 2),
        "avg_etp_mmj":      round(avg_etp, 2),
        "max_besoin_net":   round(max_besoin_net, 1),
        "efficiency_pct":   int(eff * 100),
        "mois_pluie_couvre": mois_zero,
        "nb_mois_zero":     len(mois_zero),
    }
