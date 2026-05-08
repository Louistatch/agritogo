"""Serveur Flask + HTMX pour AgriTogo."""

import os
import asyncio
import threading
import queue
import json
import time
from flask import Flask, render_template, request, session, Response, stream_with_context

from dotenv import load_dotenv
load_dotenv(override=False)

# ── Flask app — created IMMEDIATELY, before any heavy import ──
app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "static"),
)
app.secret_key = os.environ.get("SECRET_KEY", "agritogo-secret-key-2026")

# ── Health check — registered FIRST, responds in <1ms ────────
@app.route("/health")
def health():
    return {"status": "ok"}, 200

@app.route("/debug/env")
def debug_env():
    from app.key_rotation import has_keys, _get_keys
    return {
        "gemini_keys_count": len(_get_keys()),
        "gemini_keys_set": has_keys(),
        "GEMINI_API_KEY_1": "SET" if os.environ.get("GEMINI_API_KEY_1") else "MISSING",
        "GEMINI_API_KEY_2": "SET" if os.environ.get("GEMINI_API_KEY_2") else "MISSING",
        "GEMINI_API_KEY_3": "SET" if os.environ.get("GEMINI_API_KEY_3") else "MISSING",
        "ml_available": _ML_AVAILABLE,
        "startup_done": _STARTUP_DONE,
    }, 200

# ── Lazy ML state — loaded in background after startup ───────
_ML_AVAILABLE = False
_STARTUP_DONE = False
_ML_LOADING = False
_ml_lock = threading.Lock()

# Module-level references — populated after background load
ask_agent = None
process_query = None
get_memory = None
add_feedback = None
run_crop_yield_prediction = None
run_garch_forecast = None
run_risk_assessment = None
run_farmer_segmentation = None
get_kpi_data = None


def _load_ml_modules():
    """Load all heavy ML/AI modules in a background thread."""
    global _ML_AVAILABLE, _STARTUP_DONE, _ML_LOADING
    global ask_agent, process_query, get_memory, add_feedback
    global run_crop_yield_prediction, run_garch_forecast
    global run_risk_assessment, run_farmer_segmentation, get_kpi_data

    with _ml_lock:
        if _STARTUP_DONE:
            return
        try:
            print("[STARTUP] Loading ML modules...")
            t0 = time.time()

            from app.agent import ask_agent as _ask
            from app.agents.engine import (
                process_query as _pq,
                get_memory as _gm,
                add_feedback as _af,
            )
            from app.ml.crop_yield import run_crop_yield_prediction as _cy
            from app.ml.garch_volatility import run_garch_forecast as _gf
            from app.ml.financial_risk import run_risk_assessment as _ra
            from app.ml.farmer_segmentation import run_farmer_segmentation as _fs
            from app.ml.kpi_dashboard import get_kpi_data as _kd

            ask_agent = _ask
            process_query = _pq
            get_memory = _gm
            add_feedback = _af
            run_crop_yield_prediction = _cy
            run_garch_forecast = _gf
            run_risk_assessment = _ra
            run_farmer_segmentation = _fs
            get_kpi_data = _kd

            _ML_AVAILABLE = True
            print(f"[STARTUP] ML modules loaded in {time.time()-t0:.1f}s")
        except Exception as e:
            print(f"[STARTUP] ML load failed: {e}")
            _ML_AVAILABLE = False
        finally:
            _STARTUP_DONE = True
            _ML_LOADING = False


def _trigger_ml_load():
    """Trigger ML loading in background — called once on first ML request."""
    global _ML_LOADING
    if not _STARTUP_DONE and not _ML_LOADING:
        _ML_LOADING = True
        t = threading.Thread(target=_load_ml_modules, daemon=True)
        t.start()

# ── Persistent event loop for async agent calls ───────────────
# Created lazily on first use — not at module import
_loop = None
_loop_thread = None
_loop_lock = threading.Lock()


def _get_loop():
    global _loop, _loop_thread
    if _loop is None:
        with _loop_lock:
            if _loop is None:
                _loop = asyncio.new_event_loop()
                _loop_thread = threading.Thread(
                    target=_loop.run_forever, daemon=True
                )
                _loop_thread.start()
    return _loop


def run_async(coro):
    import concurrent.futures
    loop = _get_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=120)


# ── Thought Stream (SSE) ──────────────────────────────────────
_thought_queues = {}


def get_thought_queue(session_id):
    if session_id not in _thought_queues:
        _thought_queues[session_id] = queue.Queue(maxsize=100)
    return _thought_queues[session_id]


def emit_thought(session_id, thought_type, content, agent=None):
    q = get_thought_queue(session_id)
    try:
        q.put_nowait({
            "type": thought_type,
            "content": content,
            "agent": agent or "AgriTogo",
            "ts": time.time(),
        })
    except queue.Full:
        pass


# ── Database + Blueprints — lightweight, load immediately ─────
from app.database import (
    init_db, get_produits, get_marches,
    get_prix_historiques, save_conversation, get_conversations,
    get_latest_prices, clear_conversations,
)
from app.i18n import get_translations, get_lang_instruction
from app.admin import admin_bp
from app.api import api_bp

app.register_blueprint(admin_bp)
app.register_blueprint(api_bp)

try:
    init_db()
except Exception as e:
    print(f"[WARN] DB init failed: {e}")


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
    try:
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
    except Exception as e:
        import traceback
        print(f"[ERROR] / route failed: {traceback.format_exc()}")
        return f"<pre>Error: {e}\n\n{traceback.format_exc()}</pre>", 500


@app.route("/chat/clear", methods=["DELETE"])
def chat_clear():
    clear_conversations()
    return '<div class="msg msg-agent"><span class="msg-role">AgriTogo</span><p>Conversation cleared. How can I help?</p></div>'


@app.route("/chat", methods=["POST"])
def chat():
    _trigger_ml_load()
    if not _ML_AVAILABLE or ask_agent is None:
        return "<div class='msg msg-agent'><p>⚠️ Agent en cours de chargement, réessayez dans 30 secondes.</p></div>"
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
    _trigger_ml_load()
    if not _ML_AVAILABLE or process_query is None:
        return "<div class='msg'>⚠️ Engine en cours de chargement, réessayez dans 30 secondes.</div>"
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
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=False, host="0.0.0.0", port=port)
