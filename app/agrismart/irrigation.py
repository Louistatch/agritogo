"""
Calcul des besoins en irrigation — FAO-56 bilan hydrique complet.

Formule :
  ETM      = ETP × Kc × nb_jours           (besoin évapotranspiration mensuel mm)
  Peff     = pluies efficaces USDA SCS      (mm/mois)
  RU       = sol.RU × profondeur_Z          (réserve utile mm)
  RFU      = (2/3) × RU                    (réserve facilement utilisable mm)
  Bilan    = Peff + RFU - ETM
  BNet     = max(0, -Bilan)                (besoin net mm/mois)
  BBrut    = BNet / efficience              (besoin brut mm/mois)
  Volume   = BBrut × 10                    (m³/ha/mois)
"""

from app.agrismart.kc_values import KC_VALUES, IRRIGATION_SYSTEMS, MOIS, JOURS_MOIS, MOIS_TO_JAN_IDX


def _pluie_efficace(p_mm: float) -> float:
    """Pluies efficaces USDA SCS (mensuel)."""
    return (0.85 * p_mm + 3) if p_mm > 17 else 0.0


def compute_monthly_needs(
    crop_name: str,
    area_ha: float,
    soil_ru: float,
    system_name: str,
    climate: dict,
) -> list[dict]:
    """
    Calcule les besoins en eau mensuels.

    Args:
        crop_name   : nom de la culture (clé de KC_VALUES)
        area_ha     : superficie en hectares
        soil_ru     : RU du sol en mm/m (depuis SOIL_PROFILES)
        system_name : système d'irrigation (clé de IRRIGATION_SYSTEMS)
        climate     : dict retourné par climate_normals.get_nasa_climatology()
                      avec 'etp_mensuelle' (mm/j, Jan=0) et 'pluie_mensuelle' (mm/mois, Jan=0)

    Returns:
        liste de 12 dicts (un par mois Avr→Mars)
    """
    crop = KC_VALUES[crop_name]
    eff  = IRRIGATION_SYSTEMS[system_name]["efficiency"]

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
        volume_tot  = volume_ha * area_ha

        rows.append({
            "mois":         mois,
            "mois_idx":     i,
            "nb_jours":     nb_jours,
            "etp":          round(etp, 2),
            "kc":           round(kc, 2),
            "z":            round(z, 2),
            "etm":          round(etm, 1),
            "pluie":        round(pluie, 1),
            "peff":         round(peff, 1),
            "ru":           round(ru, 1),
            "rfu":          round(rfu, 1),
            "bilan":        round(bilan, 1),
            "besoin_net":   round(besoin_net, 1),
            "besoin_brut":  round(besoin_brut, 1),
            "volume_ha":    round(volume_ha, 1),
            "volume_total": round(volume_tot, 1),
        })

    return rows


def compute_kpis(rows: list[dict], area_ha: float, system_name: str) -> dict:
    """Calcule les KPIs de saison à partir des lignes mensuelles."""
    total_m3       = sum(r["volume_total"] for r in rows)
    avg_monthly    = total_m3 / 12
    pic            = max(rows, key=lambda r: r["volume_total"])
    debit_pompe    = (pic["volume_total"] / 30 / 12) * 0.277
    avg_kc         = sum(r["kc"] for r in rows) / 12
    avg_etp        = sum(r["etp"] for r in rows) / 12
    max_besoin_net = max(r["besoin_net"] for r in rows)
    eff            = IRRIGATION_SYSTEMS[system_name]["efficiency"]

    return {
        "total_m3":        round(total_m3, 0),
        "avg_monthly_m3":  round(avg_monthly, 0),
        "pic_mois":        pic["mois"],
        "pic_volume_m3":   round(pic["volume_total"], 0),
        "debit_pompe_ls":  round(debit_pompe, 2),
        "avg_kc":          round(avg_kc, 2),
        "avg_etp_mmj":     round(avg_etp, 2),
        "max_besoin_net":  round(max_besoin_net, 1),
        "efficiency_pct":  int(eff * 100),
        "area_ha":         area_ha,
    }
