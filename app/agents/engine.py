"""Decision Intelligence Engine — Moteur central multi-agents AgriTogo."""

import os
import asyncio
from datetime import datetime

# Lazy imports to avoid crash at startup if agentscope is not yet installed
try:
    from agentscope.agent import ReActAgent
    from agentscope.model import GeminiChatModel, DashScopeChatModel
    from agentscope.formatter import GeminiChatFormatter, DashScopeChatFormatter
    from agentscope.memory import InMemoryMemory
    from agentscope.tool import Toolkit
    from agentscope.message import Msg
    _AGENTSCOPE_AVAILABLE = True
except ImportError:
    _AGENTSCOPE_AVAILABLE = False

from app.agents.prompts import (
    COORDINATOR_PROMPT, MARKET_INTEL_PROMPT, QUANT_FORECAST_PROMPT,
    RISK_VOLATILITY_PROMPT, DECISION_PROMPT, UX_AGENT_PROMPT,
)
from app.agents.router import route_query, should_debate, select_model
from app.tools import (
    consulter_prix, lister_produits, lister_marches,
    enregistrer_prevision, analyser_tendance,
)
from app.ml_tools import (
    predire_rendement_cultures, prevoir_volatilite,
    evaluer_risque_financier, segmenter_agriculteurs,
    obtenir_kpi_agriculture,
)
from app.kobo_tools import (
    consulter_donnees_terrain, analyser_collecte_terrain,
    generer_formulaire_prix, generer_formulaire_agriculteur,
)

# Agent registry
_agents = {}
_memory_store = []  # Simple feedback memory


AGENT_CONFIGS = {
    "coordinator": {"prompt": COORDINATOR_PROMPT, "tools": "all"},
    "market_intel": {"prompt": MARKET_INTEL_PROMPT, "tools": "market"},
    "quant_forecast": {"prompt": QUANT_FORECAST_PROMPT, "tools": "ml"},
    "risk_volatility": {"prompt": RISK_VOLATILITY_PROMPT, "tools": "risk"},
    "decision": {"prompt": DECISION_PROMPT, "tools": "all"},
    "ux_agent": {"prompt": UX_AGENT_PROMPT, "tools": "none"},
}


def _build_toolkit(tool_set="all"):
    """Build toolkit based on agent specialization."""
    if not _AGENTSCOPE_AVAILABLE:
        return None
    toolkit = Toolkit()
    market_tools = [consulter_prix, lister_produits, lister_marches,
                    enregistrer_prevision, analyser_tendance]
    ml_tools = [predire_rendement_cultures, prevoir_volatilite,
                obtenir_kpi_agriculture]
    risk_tools = [evaluer_risque_financier, segmenter_agriculteurs,
                  prevoir_volatilite]
    kobo_tools = [consulter_donnees_terrain, analyser_collecte_terrain,
                  generer_formulaire_prix, generer_formulaire_agriculteur]

    if tool_set == "none":
        return toolkit
    tools = []
    if tool_set in ("all", "market"):
        tools.extend(market_tools)
    if tool_set in ("all", "ml"):
        tools.extend(ml_tools)
    if tool_set in ("all", "risk"):
        tools.extend(risk_tools)
    if tool_set in ("all", "market"):
        tools.extend(kobo_tools)
    # Deduplicate
    seen = set()
    for t in tools:
        if t.__name__ not in seen:
            toolkit.register_tool_function(t)
            seen.add(t.__name__)
    return toolkit


def _create_model(model_choice="gemini"):
    if not _AGENTSCOPE_AVAILABLE:
        raise RuntimeError("AgentScope not available")
    if model_choice == "qwen":
        return (
            DashScopeChatModel(
                model_name="qwen-max",
                api_key=os.environ.get("DASHSCOPE_API_KEY", ""),
                stream=False,
            ),
            DashScopeChatFormatter(),
        )
    from app.key_rotation import get_gemini_key
    return (
        GeminiChatModel(
            model_name="gemini-2.5-flash",
            api_key=get_gemini_key(),
            stream=False,
        ),
        GeminiChatFormatter(),
    )


def _get_agent(agent_type: str, model_choice: str = None):
    """Get or create a specialized agent."""
    if model_choice is None:
        model_choice = select_model(agent_type)

    key = f"{agent_type}_{model_choice}"
    if key not in _agents:
        config = AGENT_CONFIGS.get(agent_type, AGENT_CONFIGS["coordinator"])
        model, formatter = _create_model(model_choice)
        _agents[key] = ReActAgent(
            name=f"AgriTogo-{agent_type}",
            sys_prompt=config["prompt"],
            model=model,
            formatter=formatter,
            memory=InMemoryMemory(),
            toolkit=_build_toolkit(config["tools"]),
        )
    return _agents[key]


async def _call_agent(agent_type: str, question: str, model: str = None) -> str:
    """Call a single specialized agent with automatic fallback."""
    chosen_model = model or select_model(agent_type)
    try:
        agent = _get_agent(agent_type, chosen_model)
        msg = Msg(name="user", role="user", content=question)
        response = await agent(msg)
        return response.get_text_content()
    except Exception as e:
        err = str(e).lower()
        # Auto-fallback: if Gemini rate-limited, rotate key then switch to Qwen
        if "429" in err or "quota" in err or "rate" in err or "resource_exhausted" in err:
            # Try rotating Gemini key first
            if chosen_model == "gemini":
                from app.key_rotation import rotate_gemini_key, get_all_keys_count
                for _ in range(get_all_keys_count() - 1):
                    rotate_gemini_key()
                    try:
                        # Clear cached agent for this type to use new key
                        new_key = rotate_gemini_key()
                        _agents.pop(f"{agent_type}_gemini", None)
                        agent = _get_agent(agent_type, "gemini")
                        msg = Msg(name="user", role="user", content=question)
                        response = await agent(msg)
                        return f"[🔄 Clé Gemini rotée] " + response.get_text_content()
                    except Exception:
                        continue
            fallback = "gemini"  # Only Gemini with key rotation
            try:
                agent = _get_agent(agent_type, fallback)
                msg = Msg(name="user", role="user", content=question)
                response = await agent(msg)
                return f"[Fallback → {fallback.upper()}] " + response.get_text_content()
            except Exception as e2:
                return f"⚠️ Les deux modèles sont indisponibles. Gemini: quota épuisé. Qwen: {e2}"
        raise


async def _debate(question: str) -> dict:
    """Multi-model debate: Gemini proposes, Qwen critiques, Coordinator arbitrates."""
    # Step 1: Gemini proposes strategy
    gemini_response = await _call_agent("decision", question, "gemini")

    # Step 2: Qwen critiques with quantitative analysis
    critique_q = (
        f"Voici une recommandation stratégique. Critique-la avec des données "
        f"quantitatives et identifie les failles:\n\n{gemini_response}\n\n"
        f"Question originale: {question}"
    )
    qwen_response = await _call_agent("risk_volatility", critique_q, "qwen")

    # Step 3: Coordinator arbitrates
    arbitration_q = (
        f"DÉBAT MULTI-MODÈLE:\n\n"
        f"📌 PROPOSITION (Gemini):\n{gemini_response}\n\n"
        f"📌 CRITIQUE (Qwen):\n{qwen_response}\n\n"
        f"Arbitre ce débat. Donne la décision finale avec confiance et justification."
    )
    final = await _call_agent("coordinator", arbitration_q, "gemini")

    return {
        "proposal": gemini_response,
        "critique": qwen_response,
        "final_decision": final,
        "debate_used": True,
    }


async def process_query(question: str, audience: str = "farmer") -> dict:
    """Main entry point for the Decision Intelligence Engine.

    Routes query, optionally triggers debate, formats for audience.
    """
    timestamp = datetime.now().isoformat()
    agent_type = route_query(question)
    model = select_model(agent_type)
    debate = should_debate(question)

    result = {
        "timestamp": timestamp,
        "query": question,
        "agent_type": agent_type,
        "model_used": model,
        "debate_used": debate,
        "audience": audience,
    }

    try:
        if debate:
            debate_result = await _debate(question)
            result.update(debate_result)
            raw_response = debate_result["final_decision"]
        else:
            raw_response = await _call_agent(agent_type, question, model)
            result["response"] = raw_response

        # Format for audience if not already the UX agent
        if agent_type != "ux_agent" and audience in ("farmer", "cooperative"):
            ux_q = (
                f"Reformule pour un {audience} togolais:\n\n{raw_response}"
            )
            result["formatted_response"] = await _call_agent(
                "ux_agent", ux_q, "gemini"
            )
        else:
            result["formatted_response"] = raw_response

    except Exception as e:
        result["error"] = str(e)
        result["formatted_response"] = f"⚠️ Erreur: {e}"

    # Store in memory for feedback loop
    _memory_store.append(result)
    return result


def get_memory(limit=20):
    """Get recent decisions from memory."""
    return _memory_store[-limit:]


def add_feedback(index: int, outcome: str, actual_price: float = None):
    """Add real-world feedback to a past decision."""
    if 0 <= index < len(_memory_store):
        _memory_store[index]["feedback"] = {
            "outcome": outcome,
            "actual_price": actual_price,
            "feedback_date": datetime.now().isoformat(),
        }
