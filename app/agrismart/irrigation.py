"""
Besoins en irrigation — FAO-56, pas journalier agrégé par mois.

Méthode (Allen et al., 1998 ; CROPWAT) :
  ETc(j)   = ETo(mois) × Kc(j)            Kc journalier de la courbe FAO-56,
                                          à partir du mois de repiquage
  Peff     = USDA SCS (CROPWAT) :          P ≤ 250 : P(125 − 0,2P)/125
                                          P > 250 : 125 + 0,1P
             au prorata des jours de culture dans le mois
  Réserve  = RFU = p × RU(sol) × Zr        pleine au repiquage, CONSOMMÉE puis
                                          rechargée par les excédents de pluie
                                          (jamais remise à plein chaque mois)
  Besoin net = ETc − Peff − prélèvement sur la réserve (≥ 0)
  Besoin brut = net / efficience ;  m³ = mm × 10 × ha

Deux scénarios de pluie :
  « année normale »  : pluie moyenne (Peff USDA SCS)     → volume_total
  « année sèche »    : pluie fiable 4 ans sur 5 (FAO,
                       0,6P − 10 si P ≤ 70, sinon 0,8P − 24) → dimensionnement
  boost_* = marge à prévoir pour l'année sèche (sèche − normale).

Avant cet audit : Kc fixe sur 12 mois (culture présente toute l'année),
réserve du sol remise à plein chaque mois, pluie efficace « 0,85P + 3 »
non standard, et un « boost » de 15 % de l'ETM sans source. Ces trois
choix sous-estimaient les besoins de saison sèche.
"""

from app.agrismart.kc_values import (
    CROPS,
    DEFAULT_PLANTING,
    IRRIGATION_SYSTEMS,
    JOURS_MOIS,
    MOIS,
    MOIS_TO_JAN_IDX,
    cycle_length,
    daily_kc_zr,
)

PUMP_HOURS_PER_DAY = 12


def peff_usda(p_mm: float) -> float:
    """Pluie efficace mensuelle USDA SCS (formule CROPWAT)."""
    if p_mm <= 0:
        return 0.0
    return p_mm * (125 - 0.2 * p_mm) / 125 if p_mm <= 250 else 125 + 0.1 * p_mm


def peff_dependable(p_mm: float) -> float:
    """Pluie efficace fiable (probabilité 80 %), formule FAO/CROPWAT."""
    return max(0.0, 0.6 * p_mm - 10 if p_mm <= 70 else 0.8 * p_mm - 24)


def _cycle_by_month(crop: dict, planting: str) -> list[dict]:
    """Agrège la courbe journalière par mois du cycle : jours, Σ Kc, Zr fin de mois."""
    start = MOIS.index(planting)
    out = [{"days": 0, "kc_sum": 0.0, "zr": 0.0} for _ in range(12)]
    m, d_in_m = start, 0
    for day in range(cycle_length(crop)):
        kc, zr = daily_kc_zr(crop, day)
        out[m]["days"] += 1
        out[m]["kc_sum"] += kc
        out[m]["zr"] = zr
        d_in_m += 1
        if d_in_m >= JOURS_MOIS[m]:
            m, d_in_m = (m + 1) % 12, 0
    return out


def compute_monthly_needs(
    crop_name: str,
    area_m2: float,
    soil_ru: float,
    system_name: str,
    climate: dict,
    planting: str = DEFAULT_PLANTING,
) -> list[dict]:
    """12 lignes (ordre MOIS, Avril → Mars) ; mois hors cycle à zéro."""
    crop = CROPS[crop_name]
    eff = IRRIGATION_SYSTEMS[system_name]["efficiency"]
    area_ha = area_m2 / 10_000
    cyc = _cycle_by_month(crop, planting)

    # Ordre chronologique du cycle à partir du repiquage (franchit l'année).
    start = MOIS.index(planting)
    order = [(start + k) % 12 for k in range(12)]
    rows: dict[int, dict] = {}
    stock = {"normal": None, "dry": None}

    for i in order:
        c = cyc[i]
        jan_idx = MOIS_TO_JAN_IDX[MOIS[i]]
        etp = climate["etp_mensuelle"][jan_idx]
        pluie = climate["pluie_mensuelle"][jan_idx]
        days = c["days"]
        frac = days / JOURS_MOIS[i]
        etm = etp * c["kc_sum"]                       # Σ ETo × Kc(j)
        kc_mean = c["kc_sum"] / days if days else 0.0
        ru = soil_ru * c["zr"]
        rfu = crop["p"] * ru
        peff = peff_usda(pluie) * frac
        peff80 = peff_dependable(pluie) * frac

        res = {}
        for key, rain in (("normal", peff), ("dry", peff80)):
            if days == 0:
                res[key] = 0.0
                continue
            if stock[key] is None:
                stock[key] = rfu                      # réserve pleine au repiquage
            deficit = etm - rain
            if deficit > 0:
                use = min(stock[key], deficit)
                stock[key] -= use
                res[key] = deficit - use
            else:
                stock[key] = min(rfu, stock[key] - deficit)
                res[key] = 0.0
            stock[key] = min(stock[key], rfu)

        net = res["normal"]
        net_dry = max(res["dry"], net)
        brut = net / eff
        brut_dry = net_dry / eff
        rows[i] = {
            "mois": MOIS[i],
            "mois_idx": i,
            "nb_jours": days,
            "etp": round(etp, 2),
            "kc": round(kc_mean, 2),
            "z": round(c["zr"], 2),
            "etm": round(etm, 1),
            "pluie": round(pluie, 1),
            "peff": round(peff, 1),
            "peff_seche": round(peff80, 1),
            "ru": round(ru, 1),
            "rfu": round(rfu, 1),
            "bilan": round(peff - etm, 1),
            "besoin_net": round(net, 1),
            "besoin_brut": round(brut, 1),
            "volume_ha": round(brut * 10, 1),
            "volume_total": round(brut * 10 * area_ha, 2),
            "boost_mm": round(net_dry - net, 1),
            "boost_vol_ha": round((brut_dry - brut) * 10, 1),
            "boost_vol_total": round((brut_dry - brut) * 10 * area_ha, 2),
        }
    return [rows[i] for i in range(12)]


def pump_flow_ls(peak_m3: float, days: int) -> float:
    """Débit (L/s) pour apporter `peak_m3` sur `days` jours à 12 h/j."""
    if days <= 0:
        return 0.0
    return peak_m3 / days / PUMP_HOURS_PER_DAY / 3.6


def compute_kpis(rows: list[dict], area_m2: float, system_name: str, crop_name: str = "") -> dict:
    """Indicateurs de saison ; la pompe est dimensionnée sur l'année sèche."""
    area_ha = area_m2 / 10_000
    total_m3 = sum(r["volume_total"] for r in rows)
    total_boost = sum(r["boost_vol_total"] for r in rows)
    in_cycle = [r for r in rows if r["nb_jours"] > 0]
    pic = max(rows, key=lambda r: r["volume_total"] + r["boost_vol_total"])
    pic_vol = pic["volume_total"] + pic["boost_vol_total"]
    eff = IRRIGATION_SYSTEMS[system_name]["efficiency"]
    mois_zero = [r["mois"] for r in in_cycle if r["besoin_net"] == 0]
    n = max(len(in_cycle), 1)
    return {
        "crop": crop_name,
        "area_m2": area_m2,
        "area_ha": round(area_ha, 4),
        "total_m3": round(total_m3, 1),
        "total_boost_m3": round(total_boost, 1),
        "total_optimal_m3": round(total_m3 + total_boost, 1),
        "avg_monthly_m3": round(total_m3 / n, 2),
        "pic_mois": pic["mois"],
        "pic_volume_m3": round(pic_vol, 1),
        "debit_pompe_ls": round(pump_flow_ls(pic_vol, pic["nb_jours"]), 3),
        "avg_kc": round(sum(r["kc"] for r in in_cycle) / n, 2),
        "avg_etp_mmj": round(sum(r["etp"] for r in in_cycle) / n, 2),
        "max_besoin_net": round(max(r["besoin_net"] for r in rows), 1),
        "efficiency_pct": int(eff * 100),
        "mois_pluie_couvre": mois_zero,
        "nb_mois_zero": len(mois_zero),
        "nb_mois_cycle": len(in_cycle),
    }
