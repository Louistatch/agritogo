"""
Profils pédologiques — propriétés hydrauliques ROSETTA v3 (USDA-ARS).
Valeurs pré-calculées via van Genuchten à partir des paramètres USDA.

RU  = Réserve Utile   = (FC - WP) × 1000  mm/m
RFU = Réserve Facilement Utilisable = RU × 2/3  mm/m
"""

SOIL_PROFILES = {
    "Sableux": {
        "emoji": "🏖️",
        "sand_pct": 75.0, "silt_pct": 17.0, "clay_pct": 8.0, "bdod": 1.55,
        "fc_pct": 14.2, "wp_pct": 5.8,
        "RU": 84, "RFU": 56,
        "source": "ROSETTA v3 (USDA-ARS)",
        "desc": "Drainage rapide, faible rétention",
    },
    "Sableux-Limoneux": {
        "emoji": "🌱",
        "sand_pct": 60.0, "silt_pct": 28.0, "clay_pct": 12.0, "bdod": 1.45,
        "fc_pct": 18.5, "wp_pct": 8.2,
        "RU": 103, "RFU": 69,
        "source": "ROSETTA v3 (USDA-ARS)",
        "desc": "Bonne structure, drainage modéré",
    },
    "Limoneux": {
        "emoji": "🌾",
        "sand_pct": 42.0, "silt_pct": 36.0, "clay_pct": 22.0, "bdod": 1.30,
        "fc_pct": 26.8, "wp_pct": 14.3,
        "RU": 125, "RFU": 83,
        "source": "ROSETTA v3 (USDA-ARS)",
        "desc": "Sol équilibré, idéal maraîchage",
    },
    "Argilo-Limoneux": {
        "emoji": "🟫",
        "sand_pct": 32.0, "silt_pct": 38.0, "clay_pct": 30.0, "bdod": 1.20,
        "fc_pct": 34.1, "wp_pct": 19.6,
        "RU": 145, "RFU": 97,
        "source": "ROSETTA v3 (USDA-ARS)",
        "desc": "Forte rétention, risque engorgement",
    },
    "Argileux": {
        "emoji": "🧱",
        "sand_pct": 20.0, "silt_pct": 38.0, "clay_pct": 42.0, "bdod": 1.10,
        "fc_pct": 42.0, "wp_pct": 26.5,
        "RU": 155, "RFU": 103,
        "source": "ROSETTA v3 (USDA-ARS)",
        "desc": "Très forte rétention, drainage lent",
    },
}
