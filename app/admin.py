"""Routes admin Flask pour AgriTogo — Data, KoboCollect, ML modules."""

import os
from flask import Blueprint, render_template, request, Response
from app.database import (
    get_produits, get_marches, get_db_stats, get_all_prix,
    add_produit, delete_produit, delete_prix,
    add_prix_from_csv, add_produit_from_csv, export_prix_csv,
)
from app.kobo import (
    save_kobo_config, load_kobo_config, KoboClient,
    generate_price_survey_xlsform, generate_farmer_survey_xlsform,
    generate_crop_yield_form, generate_financial_risk_form,
    generate_market_price_form, xlsform_to_xlsx,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin", template_folder="templates")

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'agentscope', 'data')


@admin_bp.route("/")
def admin_index():
    stats = get_db_stats()
    produits = get_produits()
    marches = get_marches()
    kobo_cfg = load_kobo_config()
    kobo_forms = []
    if kobo_cfg:
        try:
            client = KoboClient(kobo_cfg["base_url"], kobo_cfg["token"])
            kobo_forms = client.get_forms()
        except Exception:
            pass
    # Check which data files exist
    data_files = {}
    for name, path in [
        ("yield_df", os.path.join(DATA_DIR, "archive1", "yield_df.csv")),
        ("Core_TimeSeries", os.path.join(DATA_DIR, "Core_TimeSeries.csv")),
        ("AgriRiskFin", os.path.join(DATA_DIR, "AgriRiskFin_Dataset.csv")),
        ("data2_excel", os.path.join(DATA_DIR, "Copy of data2(1).xlsx")),
        ("rainfall", os.path.join(DATA_DIR, "archive1", "rainfall.csv")),
        ("temp", os.path.join(DATA_DIR, "archive1", "temp.csv")),
    ]:
        data_files[name] = os.path.exists(path)
    return render_template("admin.html", stats=stats, produits=produits,
                           marches=marches, kobo_cfg=kobo_cfg,
                           kobo_forms=kobo_forms, data_files=data_files)


@admin_bp.route("/stats")
def admin_stats():
    return render_template("partials/admin_stats.html", stats=get_db_stats())

@admin_bp.route("/produits")
def admin_produits():
    return render_template("partials/admin_produits.html", produits=get_produits())

@admin_bp.route("/produit/add", methods=["POST"])
def admin_add_produit():
    nom = request.form.get("nom", "").strip()
    unite = request.form.get("unite", "kg").strip()
    cat = request.form.get("categorie", "cereale").strip()
    msg = ""
    if nom:
        ok = add_produit(nom, unite, cat)
        msg = f"{nom} added" if ok else f"{nom} already exists"
    return render_template("partials/admin_produits.html", produits=get_produits(), msg=msg)

@admin_bp.route("/produit/delete/<int:pid>", methods=["DELETE"])
def admin_delete_produit(pid):
    delete_produit(pid)
    return render_template("partials/admin_produits.html", produits=get_produits(), msg="Deleted")

@admin_bp.route("/prix", methods=["GET"])
def admin_prix():
    page = int(request.args.get("page", 1))
    data = get_all_prix(page=page)
    return render_template("partials/admin_prix.html", data=data, page=page)

@admin_bp.route("/prix/delete/<int:pid>", methods=["DELETE"])
def admin_delete_prix(pid):
    delete_prix(pid)
    return render_template("partials/admin_prix.html", data=get_all_prix(page=1), page=1)

@admin_bp.route("/upload/prix", methods=["POST"])
def admin_upload_prix():
    f = request.files.get("file")
    msg = "CSV file required"
    if f and f.filename.endswith(".csv"):
        count = add_prix_from_csv(f.read().decode("utf-8"))
        msg = f"{count} price entries imported"
    return render_template("partials/admin_stats.html", stats=get_db_stats(), msg=msg)

@admin_bp.route("/upload/produits", methods=["POST"])
def admin_upload_produits():
    f = request.files.get("file")
    msg = "CSV file required"
    if f and f.filename.endswith(".csv"):
        count = add_produit_from_csv(f.read().decode("utf-8"))
        msg = f"{count} products imported"
    return render_template("partials/admin_produits.html", produits=get_produits(), msg=msg)

@admin_bp.route("/upload/dataset", methods=["POST"])
def admin_upload_dataset():
    """Upload any dataset file to the data directory."""
    f = request.files.get("file")
    target = request.form.get("target", "")
    msg = "No file uploaded"
    if f and target:
        os.makedirs(DATA_DIR, exist_ok=True)
        if target.startswith("archive1/"):
            os.makedirs(os.path.join(DATA_DIR, "archive1"), exist_ok=True)
        dest = os.path.join(DATA_DIR, target)
        f.save(dest)
        msg = f"Uploaded {target} ({os.path.getsize(dest):,} bytes)"
    return f'<div class="admin-msg">{msg}</div>'

@admin_bp.route("/export/prix")
def admin_export_prix():
    return Response(export_prix_csv(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment;filename=agritogo_prix.csv"})


# ── KoboCollect Routes ──

@admin_bp.route("/kobo/config", methods=["POST"])
def admin_kobo_config():
    url = request.form.get("kobo_url", "").strip()
    token = request.form.get("kobo_token", "").strip()
    if url and token:
        save_kobo_config(url, token)
        try:
            client = KoboClient(url, token)
            count = client.get_form_count()
            msg = f"Connected. {count} form(s) found."
        except Exception as e:
            msg = f"Saved but connection failed: {e}"
    else:
        msg = "URL and token required"
    return f'<div class="admin-msg">{msg}</div>'


@admin_bp.route("/kobo/forms")
def admin_kobo_forms():
    cfg = load_kobo_config()
    if not cfg:
        return '<div class="admin-msg">KoboCollect not configured</div>'
    client = KoboClient(cfg["base_url"], cfg["token"])
    forms = client.get_forms()
    return render_template("partials/admin_kobo_forms.html", forms=forms)


@admin_bp.route("/kobo/submissions/<uid>")
def admin_kobo_submissions(uid):
    cfg = load_kobo_config()
    if not cfg:
        return '<div class="admin-msg">Not configured</div>'
    client = KoboClient(cfg["base_url"], cfg["token"])
    subs = client.get_submissions(uid)
    return render_template("partials/admin_kobo_subs.html", subs=subs, uid=uid)


@admin_bp.route("/kobo/xlsform/<form_type>")
def admin_download_xlsform(form_type):
    if form_type == "price":
        form = generate_price_survey_xlsform()
        name = "agritogo_price_survey.xlsx"
    elif form_type == "yield":
        form = generate_crop_yield_form()
        name = "agritogo_yield_survey.xlsx"
    elif form_type == "risk_form":
        form = generate_financial_risk_form()
        name = "agritogo_financial_risk_survey.xlsx"
    elif form_type == "market":
        form = generate_market_price_form()
        name = "agritogo_market_price_survey.xlsx"
    else:
        form = generate_farmer_survey_xlsform()
        name = "agritogo_farmer_survey.xlsx"
    xlsx_data = xlsform_to_xlsx(form)
    return Response(xlsx_data,
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment;filename={name}"})
