"""Client KoboCollect API et générateur XLSForm pour AgriTogo."""

import csv
import io
import json
import os
import requests


CONFIG_PATH = os.path.join(os.path.dirname(__file__), "kobo_config.json")


class KoboClient:
    """Client pour l'API KoboToolbox v2."""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.headers = {"Authorization": f"Token {token}"}

    def get_forms(self) -> list:
        """Récupère la liste des formulaires."""
        try:
            r = requests.get(
                f"{self.base_url}/api/v2/assets/?format=json",
                headers=self.headers, timeout=15,
            )
            r.raise_for_status()
            return [
                {"uid": a["uid"], "name": a["name"],
                 "deployment_status": a.get("deployment_status", "")}
                for a in r.json().get("results", [])
            ]
        except Exception:
            return []

    def get_submissions(self, form_uid: str) -> list:
        """Récupère les soumissions d'un formulaire."""
        try:
            r = requests.get(
                f"{self.base_url}/api/v2/assets/{form_uid}/data/?format=json",
                headers=self.headers, timeout=15,
            )
            r.raise_for_status()
            return r.json().get("results", [])
        except Exception:
            return []

    def get_form_count(self) -> int:
        """Retourne le nombre total de formulaires."""
        return len(self.get_forms())


def generate_price_survey_xlsform() -> dict:
    """Génère un XLSForm pour la collecte de prix sur les marchés togolais."""
    markets = ["Lome-Adawlato", "Kara", "Sokode", "Atakpame", "Dapaong"]
    products = ["Mais", "Riz", "Sorgho", "Mil", "Haricot", "Soja",
                "Arachide", "Igname", "Manioc", "Tomate", "Piment", "Oignon"]
    units = ["kg", "tonne", "sac"]
    def _f(t, n, l, req="yes", c=""):
        return {"type": t, "name": n, "label": l, "required": req, "constraint": c}
    survey = [
        _f("today", "date", "Date de collecte"),
        _f("select_one market", "market", "Marché"),
        _f("select_one product", "product", "Produit"),
        _f("integer", "price", "Prix (FCFA)", c=". > 0"),
        _f("select_one unit", "unit", "Unité"),
        _f("text", "collector_name", "Nom du collecteur"),
        _f("geopoint", "gps_location", "Position GPS", req="no"),
        _f("text", "notes", "Notes", req="no"),
    ]
    choices = (
        [{"list_name": "market", "name": m, "label": m} for m in markets]
        + [{"list_name": "product", "name": p, "label": p} for p in products]
        + [{"list_name": "unit", "name": u, "label": u} for u in units]
    )
    return {"survey": survey, "choices": choices,
            "title": "AgriTogo - Collecte Prix Marches", "form_id": "agritogo_prix"}


def generate_farmer_survey_xlsform() -> dict:
    """Génère un XLSForm pour le profilage des agriculteurs togolais."""
    regions = ["Maritime", "Plateaux", "Centrale", "Kara", "Savanes"]
    crops = ["Mais", "Riz", "Sorgho", "Mil", "Igname", "Manioc",
             "Soja", "Arachide", "Tomate", "Piment"]
    yn = ["yes", "no"]
    storage = ["none", "basic", "good"]
    def _f(t, n, l, req="yes", c=""):
        return {"type": t, "name": n, "label": l, "required": req, "constraint": c}
    survey = [
        _f("text", "farmer_name", "Nom de l'agriculteur"),
        _f("select_one region", "region", "Région"),
        _f("decimal", "farm_size_ha", "Superficie (ha)", c=". > 0"),
        _f("select_one crop", "main_crop", "Culture principale"),
        _f("select_one crop", "secondary_crop", "Culture secondaire", req="no"),
        _f("integer", "annual_revenue_fcfa", "Revenu annuel (FCFA)", req="no", c=". >= 0"),
        _f("select_one yn", "has_irrigation", "Irrigation ?"),
        _f("select_one yn", "has_insurance", "Assurance ?"),
        _f("integer", "years_experience", "Années d'expérience", c=". >= 0"),
        _f("select_one storage", "storage_capacity", "Capacité de stockage"),
        _f("decimal", "distance_to_market_km", "Distance au marché (km)", req="no", c=". >= 0"),
        _f("text", "notes", "Notes", req="no"),
    ]
    choices = (
        [{"list_name": "region", "name": r, "label": r} for r in regions]
        + [{"list_name": "crop", "name": c, "label": c} for c in crops]
        + [{"list_name": "yn", "name": v, "label": v} for v in yn]
        + [{"list_name": "storage", "name": s, "label": s} for s in storage]
    )
    return {"survey": survey, "choices": choices,
            "title": "AgriTogo - Profil Agriculteur", "form_id": "agritogo_farmer"}


def xlsform_to_xlsx(xlsform_dict: dict) -> bytes:
    """Convertit un dict XLSForm en fichier Excel (.xlsx) avec feuilles survey, choices, settings."""
    from openpyxl import Workbook
    wb = Workbook()

    # Survey sheet
    ws_survey = wb.active
    ws_survey.title = "survey"
    if xlsform_dict.get("survey"):
        keys = list(xlsform_dict["survey"][0].keys())
        ws_survey.append(keys)
        for row in xlsform_dict["survey"]:
            ws_survey.append([row.get(k, "") for k in keys])

    # Choices sheet
    ws_choices = wb.create_sheet("choices")
    if xlsform_dict.get("choices"):
        keys = list(xlsform_dict["choices"][0].keys())
        ws_choices.append(keys)
        for row in xlsform_dict["choices"]:
            ws_choices.append([row.get(k, "") for k in keys])

    # Settings sheet
    ws_settings = wb.create_sheet("settings")
    ws_settings.append(["form_title", "form_id", "version"])
    title = xlsform_dict.get("title", "AgriTogo Survey")
    form_id = xlsform_dict.get("form_id", "agritogo_form")
    ws_settings.append([title, form_id, "1"])

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


def save_kobo_config(base_url: str, token: str) -> None:
    """Sauvegarde la configuration KoboCollect."""
    with open(CONFIG_PATH, "w") as f:
        json.dump({"base_url": base_url, "token": token}, f)


def load_kobo_config() -> dict | None:
    """Charge la configuration KoboCollect, ou None si absente."""
    if not os.path.exists(CONFIG_PATH):
        return None
    with open(CONFIG_PATH) as f:
        return json.load(f)
