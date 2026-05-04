"""Serveur Flask + HTMX pour AgriTogo."""

import os
import asyncio
import threading
import queue
import json
import time
from flask import Flask, render_template, request, session, Response, stream_with_context

# Persistent event loop for async agent calls
_loop = asyncio.new_event_loop()
_thread = threading.Thread(target=_loop.run_forever, daemon=True)
_thread.start()

def run_async(coro):
    """Run async coroutine on the persistent event loop."""
    import concurrent.futures
    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    return future.result(timeout=120)


# ── Thought Stream (SSE) ──────────────────────────────────
_thought_queues = {}  # session_id → queue


def get_thought_queue(session_id):
    if session_id not in _thought_queues:
        _thought_queues[session_id] = queue.Queue(maxsize=100)
    return _thought_queues[session_id]


def emit_thought(session_id, thought_type, content, agent=None):
    """Push a thought event to the SSE stream."""
    q = get_thought_queue(session_id)
    try:
        q.put_nowait({
            "type": thought_type,  # "thinking" | "tool_call" | "tool_result" | "decision" | "done"
            "content": content,
            "agent": agent or "AgriTogo",
            "ts": time.time(),
        })
    except queue.Full:
        pass

from dotenv import load_dotenv

# override=False ensures Railway env vars take priority over .env file
load_dotenv(override=False)

from app.database import (
    init_db, get_produits, get_marches,
    get_prix_historiques, save_conversation, get_conversations,
    get_latest_prices, clear_conversations,
)
from app.i18n import get_translations, get_lang_instruction
from app.admin import admin_bp
from app.api import api_bp

# Heavy imports — wrapped to avoid crashing workers at startup
try:
    from app.agent import ask_agent
    from app.agents.engine import process_query, get_memory, add_feedback
    from app.ml.crop_yield import run_crop_yield_prediction
    from app.ml.garch_volatility import run_garch_forecast
    from app.ml.financial_risk import run_risk_assessment
    from app.ml.farmer_segmentation import run_farmer_segmentation
    from app.ml.kpi_dashboard import get_kpi_data
    _ML_AVAILABLE = True
except Exception as e:
    print(f"[WARN] ML/Agent imports failed: {e}")
    _ML_AVAILABLE = False

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "static"),
)

app.secret_key = os.environ.get("SECRET_KEY", "agritogo-secret-key-2026")
app.register_blueprint(admin_bp)
app.register_blueprint(api_bp)

# Init DB after app creation (non-blocking)
try:
    init_db()
except Exception as e:
    print(f"[WARN] DB init failed: {e}")


@app.route("/health")
def health():
    return {"status": "ok"}, 200


@app.route("/lang/<lang>")
def set_lang(lang):
    if lang in ("en", "fr"):
        session["lang"] = lang
    return "", 204, {"HX-Refresh": "true"}


@app.route("/thoughts")
def thoughts_stream():
    """SSE endpoint — streams agent reasoning steps to the frontend."""
    sid = session.get("_id", "default")
    q = get_thought_queue(sid)

    def generate():
        yield "data: {\"type\":\"connected\"}\n\n"
        while True:
            try:
                event = q.get(timeout=30)
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("type") == "done":
                    break
            except queue.Empty:
                yield "data: {\"type\":\"ping\"}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.context_processor
def inject_i18n():
    lang = session.get("lang", "fr")
    if "_id" not in session:
        import uuid
        session["_id"] = str(uuid.uuid4())[:8]
    return {"t": get_translations(lang), "lang": lang}


@app.route("/")
def index():
    produits = get_produits()
    marches = get_marches()
    conversations = get_conversations()
    latest_prices = get_latest_prices()
    return render_template(
        "index.html",
        produits=produits,
        marches=marches,
        conversations=conversations,
        prices=latest_prices,
    )


@app.route("/chat/clear", methods=["DELETE"])
def chat_clear():
    clear_conversations()
    return '<div class="msg msg-agent"><span class="msg-role">AgriTogo</span><p>Conversation cleared. How can I help?</p></div>'


@app.route("/chat", methods=["POST"])
def chat():
    if not _ML_AVAILABLE:
        return "<div class='msg msg-agent'><p>⚠️ Agent non disponible au démarrage.</p></div>"
    message = request.form.get("message", "").strip()
    model_choice = request.form.get("model", "gemini")
    if not message:
        return ""
    lang = session.get("lang", "fr")
    lang_suffix = get_lang_instruction(lang)
    sid = session.get("_id", "default")
    emit_thought(sid, "thinking", f"Processing: {message[:80]}...", "AgriTogo")
    save_conversation("user", message)
    response = run_async(ask_agent(message + lang_suffix, model_choice))
    emit_thought(sid, "done", "Response ready")
    save_conversation("agent", response)
    conversations = get_conversations()
    return render_template("partials/chat_messages.html", conversations=conversations)


@app.route("/prix", methods=["POST"])
def prix():
    produit = request.form.get("produit", "")
    marche = request.form.get("marche", "")
    data = get_prix_historiques(produit, marche or None, 20)
    return render_template("partials/prix_table.html", data=data, produit=produit)


@app.route("/dashboard")
def dashboard():
    produits = get_produits()
    marches = get_marches()
    return render_template(
        "partials/dashboard.html",
        produits=produits,
        marches=marches,
    )


@app.route("/ml/interpret", methods=["POST"])
def ml_interpret():
    """Send ML results to the agent for professional interpretation."""
    module = request.form.get("module", "")
    lang = session.get("lang", "fr")
    lang_suffix = get_lang_instruction(lang)
    sid = session.get("_id", "default")
    emit_thought(sid, "thinking", f"Running {module} analysis...", "Quant Agent")
    emit_thought(sid, "tool_call", f"Module: {module}", "Quant Agent")

    # Re-run the module to get full data for the agent
    data_str = ""
    try:
        if module == "crop_yield":
            crop = request.form.get("crop", "Mais")
            r = run_crop_yield_prediction(crop=crop)
            data_str = (f"Yield Prediction for {r['crop']}: "
                       f"RF R2={r['metrics']['random_forest']['r2']}, "
                       f"XGB R2={r['metrics']['xgboost']['r2']}, "
                       f"avg yield={r['avg_yield_t_ha']} t/ha, "
                       f"observations={r['n_observations']}, "
                       f"features: {r['feature_importance']}, "
                       f"yield by region: {r['region_yields']}")
        elif module == "garch":
            produit = request.form.get("produit", "Mais")
            r = run_garch_forecast(product=produit)
            data_str = (f"GARCH Volatility for {r['product']}: last price={r['last_price_fcfa']} FCFA, "
                       f"current vol={r['historical_volatility_stats']['current']}, "
                       f"params={r['model_params']}, {r['summary']}")
        elif module == "risk":
            r = run_risk_assessment()
            data_str = (f"Financial Risk Assessment on {r['total_dossiers']} loan dossiers. "
                       f"F1={r['metrics']['f1']}, accuracy={r['metrics']['accuracy']}. "
                       f"Riskiest region: {r['riskiest_region']}, safest: {r['safest_region']}. "
                       f"Risk by region: {r['risk_by_region']}. "
                       f"Risk by size: {r['risk_by_size']}. "
                       f"Key factors: {r['feature_importance'][:3]}. "
                       f"{r['summary']}")
        elif module == "segmentation":
            r = run_farmer_segmentation()
            profiles = [(p['name'], p['count'], p['avg_revenue_fcfa'], p['profit_margin_pct'], p['avg_climate_risk'], p['top_region']) for p in r['cluster_profiles']]
            data_str = (f"Farmer Segmentation: {r['total_farmers']} farmers in {r['n_clusters']} segments. "
                       f"PCA variance: {sum(r['explained_variance'])*100:.1f}%. "
                       f"Profiles (name, count, avg_revenue, margin%, climate_risk, top_region): {profiles}. "
                       f"Region summary: {r['region_summary']}. {r['summary']}")
        elif module == "kpi":
            r = get_kpi_data()
            data_str = (f"Agriculture KPIs Togo: "
                       f"national yield={r['national_summary']['avg_national_yield']} kg/ha, "
                       f"total area={r['national_summary']['total_cultivated_ha']} ha, "
                       f"input cost={r['national_summary']['total_input_cost_ha']} FCFA/ha, "
                       f"top crops by ROI: {[(c['crop'], c['roi_percent']) for c in r['top_performers']]}, "
                       f"yield by region: {[(k, v['avg_yield_kg_ha']) for k,v in r['yield_by_region'].items()]}, "
                       f"climate risk: {[(k, v['risk_score']) for k,v in r['climate_risk_by_region'].items()]}")
    except Exception as e:
        data_str = f"Module {module} error: {e}"

    if not data_str:
        data_str = f"Module '{module}' not recognized or returned no data."

    print(f"[INTERPRET] module={module}, data_len={len(data_str)}")
    emit_thought(sid, "tool_result", f"Data ready: {len(data_str)} chars", "Quant Agent")
    emit_thought(sid, "thinking", "Generating interpretation...", "AgriTogo")

    prompt = (
        f"Voici les resultats complets du module d'analyse '{module}'. "
        f"Interprete ces resultats pour un decideur agricole au Togo. "
        f"Explique ce que chaque chiffre signifie concretement. "
        f"Donne des recommandations actionnables. "
        f"Si les metriques sont mauvaises, explique pourquoi et quoi faire. "
        f"Max 6 phrases.\n\nRESULTATS:\n{data_str}{lang_suffix}"
    )
    response = run_async(ask_agent(prompt))
    emit_thought(sid, "done", "Interpretation complete")
    header = "Analyse de l'agent" if lang == "fr" else "Agent Analysis"
    return f'<div class="agent-interpretation"><div class="interp-header">{header}</div><div class="response-body">{response}</div></div>'


@app.route("/ml/crop-yield", methods=["POST"])
def ml_crop_yield():
    crop = request.form.get("crop", "Mais")
    result = run_crop_yield_prediction(crop=crop)
    return render_template("partials/ml_result.html", title=f"Yield Prediction — {crop}", result=result, module="crop_yield")


@app.route("/ml/garch", methods=["POST"])
def ml_garch():
    produit = request.form.get("produit", "Maïs")
    result = run_garch_forecast(product=produit)
    return render_template("partials/ml_result.html", title="📈 Volatilité GARCH", result=result, module="garch")


@app.route("/ml/risk", methods=["POST"])
def ml_risk():
    result = run_risk_assessment()
    return render_template("partials/ml_result.html", title="⚠️ Risque Financier", result=result, module="risk")


@app.route("/ml/segmentation", methods=["POST"])
def ml_segmentation():
    result = run_farmer_segmentation()
    return render_template("partials/ml_result.html", title="👥 Segmentation", result=result, module="segmentation")


@app.route("/ml/kpi", methods=["POST"])
def ml_kpi():
    result = get_kpi_data()
    return render_template("partials/ml_result.html", title="📊 KPIs Agriculture", result=result, module="kpi")


# ── Decision Intelligence Engine Routes ──

@app.route("/engine", methods=["POST"])
def engine_query():
    if not _ML_AVAILABLE:
        return "<div class='msg'>⚠️ Engine non disponible.</div>"
    question = request.form.get("question", "").strip()
    audience = request.form.get("audience", "farmer")
    if not question:
        return ""
    lang = session.get("lang", "fr")
    lang_suffix = get_lang_instruction(lang)
    sid = session.get("_id", "default")
    emit_thought(sid, "thinking", f"Routing query to specialized agents...", "Coordinator")
    result = run_async(process_query(question + lang_suffix, audience))
    emit_thought(sid, "decision", result.get("formatted_response", "")[:120] + "...", "Decision Agent")
    emit_thought(sid, "done", "Analysis complete")
    save_conversation("user", question)
    save_conversation("engine", result.get("formatted_response", ""))
    return render_template("partials/engine_result.html", result=result)


@app.route("/engine/memory")
def engine_memory():
    memory = get_memory(20)
    return render_template("partials/engine_memory.html", memory=memory)


@app.route("/engine/feedback", methods=["POST"])
def engine_feedback():
    idx = int(request.form.get("index", 0))
    outcome = request.form.get("outcome", "")
    price = request.form.get("actual_price")
    add_feedback(idx, outcome, float(price) if price else None)
    return "<div class='admin-msg'>✅ Feedback enregistré</div>"


if __name__ == "__main__":
    app.run(debug=True, port=5000)
