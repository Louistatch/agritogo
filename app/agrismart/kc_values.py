"""
Paramètres culturaux FAO-56 (Allen et al., 1998, Tableaux 11, 12 et 22).

Chaque culture est décrite par son CYCLE : durées des 4 stades (initial,
développement, mi-saison, arrière-saison, en jours), Kc ini / mi / fin,
profondeur racinaire min → max (m) et fraction p de la réserve utilisable sans
stress. Le Kc journalier suit la courbe FAO (plat, linéaire, plat, linéaire)
à partir du MOIS DE REPIQUAGE choisi par l'utilisateur.

Avant cet audit, un Kc était fixé pour chacun des 12 mois de l'année (culture
présente toute l'année, Kc « initial » en pleine saison sèche) : cela sous-
estimait fortement les besoins de la saison où l'on irrigue réellement.

Gombo : absent des tableaux FAO-56 ; valeurs d'études régionales, à
confirmer localement.
"""

MOIS = [
    "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre",
    "Octobre", "Novembre", "Décembre", "Janvier", "Février", "Mars"
]
JOURS_MOIS = [30, 31, 30, 31, 31, 30, 31, 30, 31, 31, 28, 31]

MOIS_TO_JAN_IDX = {
    "Avril": 3, "Mai": 4, "Juin": 5, "Juillet": 6,
    "Août": 7, "Septembre": 8, "Octobre": 9, "Novembre": 10,
    "Décembre": 11, "Janvier": 0, "Février": 1, "Mars": 2,
}

# Repiquage par défaut : début de saison sèche, période où l'irrigation du
# maraîchage est la règle au Togo.
DEFAULT_PLANTING = "Novembre"

# stages = (L_ini, L_dev, L_mid, L_late) jours ; kc = (ini, mid, end) ;
# zr = (repiquage, maximum) m — maximum pris au BAS de la fourchette du
# Tableau 22 (maraîchage, irrigation localisée) : hypothèse prudente ;
# p = fraction de la réserve utile consommable sans stress (Tableau 22).
CROPS = {
    "Tomate":    {"emoji": "🍅", "stages": (30, 40, 40, 25), "kc": (0.60, 1.15, 0.80), "zr": (0.25, 0.70), "p": 0.40},
    "Piment":    {"emoji": "🌶️", "stages": (30, 35, 40, 20), "kc": (0.60, 1.05, 0.90), "zr": (0.25, 0.50), "p": 0.30},
    "Oignon":    {"emoji": "🧅", "stages": (15, 25, 70, 40), "kc": (0.70, 1.05, 0.75), "zr": (0.15, 0.30), "p": 0.30},
    "Chou":      {"emoji": "🥬", "stages": (40, 60, 50, 15), "kc": (0.70, 1.05, 0.95), "zr": (0.25, 0.50), "p": 0.45},
    "Laitue":    {"emoji": "🥗", "stages": (20, 30, 15, 10), "kc": (0.70, 1.00, 0.95), "zr": (0.15, 0.30), "p": 0.30},
    "Carotte":   {"emoji": "🥕", "stages": (20, 30, 30, 20), "kc": (0.70, 1.05, 0.95), "zr": (0.20, 0.50), "p": 0.35},
    "Concombre": {"emoji": "🥒", "stages": (20, 30, 40, 15), "kc": (0.60, 1.00, 0.75), "zr": (0.25, 0.70), "p": 0.50},
    "Aubergine": {"emoji": "🍆", "stages": (30, 40, 40, 20), "kc": (0.60, 1.05, 0.90), "zr": (0.25, 0.70), "p": 0.45},
    "Gombo":     {"emoji": "🌿", "stages": (25, 30, 40, 20), "kc": (0.50, 1.00, 0.80), "zr": (0.20, 0.40), "p": 0.40},
    "Pastèque":  {"emoji": "🍉", "stages": (20, 30, 30, 30), "kc": (0.40, 1.00, 0.75), "zr": (0.30, 0.80), "p": 0.40},
}


def daily_kc_zr(crop: dict, day: int) -> tuple[float, float]:
    """Kc et profondeur racinaire au jour `day` (0 = repiquage), courbe FAO-56."""
    l_ini, l_dev, l_mid, l_late = crop["stages"]
    kc_ini, kc_mid, kc_end = crop["kc"]
    zr_min, zr_max = crop["zr"]
    if day < l_ini:
        kc = kc_ini
    elif day < l_ini + l_dev:
        kc = kc_ini + (kc_mid - kc_ini) * (day - l_ini) / l_dev
    elif day < l_ini + l_dev + l_mid:
        kc = kc_mid
    else:
        kc = kc_mid + (kc_end - kc_mid) * (day - l_ini - l_dev - l_mid) / l_late
    grow = l_ini + l_dev
    zr = zr_min + (zr_max - zr_min) * min(day, grow) / grow
    return kc, zr


def cycle_length(crop: dict) -> int:
    return sum(crop["stages"])


def monthly_profile(crop: dict, planting: str = DEFAULT_PLANTING) -> tuple[list[float], list[float]]:
    """Kc et Zr moyens par mois (ordre MOIS), 0 hors cycle — pour l'affichage."""
    start = MOIS.index(planting)
    kc_sum = [0.0] * 12
    zr_sum = [0.0] * 12
    days = [0] * 12
    m, d_in_m = start, 0
    for day in range(cycle_length(crop)):
        kc, zr = daily_kc_zr(crop, day)
        kc_sum[m] += kc
        zr_sum[m] += zr
        days[m] += 1
        d_in_m += 1
        if d_in_m >= JOURS_MOIS[m]:
            m, d_in_m = (m + 1) % 12, 0
    kc = [round(kc_sum[i] / days[i], 2) if days[i] else 0.0 for i in range(12)]
    zr = [round(zr_sum[i] / days[i], 2) if days[i] else 0.0 for i in range(12)]
    return kc, zr


# Compatibilité : /agrismart/crops exposait un profil mensuel par culture.
KC_VALUES = {}
for _name, _c in CROPS.items():
    _kc, _z = monthly_profile(_c)
    KC_VALUES[_name] = {"emoji": _c["emoji"], "kc": _kc, "z": _z}

IRRIGATION_SYSTEMS = {
    "Goutte à goutte": {"efficiency": 0.90, "emoji": "💧"},
    "Bande perforée":  {"efficiency": 0.75, "emoji": "〰️"},
    "Aspersion":       {"efficiency": 0.75, "emoji": "🌧️"},
    "Gravitaire":      {"efficiency": 0.60, "emoji": "🌊"},
}
