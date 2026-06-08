"""Decision Intelligence Engine — Moteur central multi-agents AgriTogo."""

import os
from datetime import datetime

# Lazy imports to avoid crash at startup if agentscope is not yet installed
try:
    from agentscope.agent import ReActAgent
    from agentscope.model import OpenAIChatModel
    from agentscope.formatter import DeepSeekChatFormatter
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
    evaluer_risque_financier, segmenter_agriculteurs, obtenir_kpi_agriculture,
    consulter_meteo_region, rafraichir_donnees_climat,
)
from app.kobo_tools import (
    consulter_donnees_terrain, analyser_collecte_terrain,
    generer_formulaire_prix, generer_formulaire_agriculteur,
)

# Agent registry  (key: "{agent_type}_{model_name}")
_agents = {}
_memory_store = []

DEEPSEEK_BASE_URL = "https://api.deepseek.com"

AGENT_CONFIGS = {
    "coordinator": {"prompt": COORDINATOR_PROMPT, "tools": "all"},
    "market_intel": {"prompt": MARKET_INTEL_PROMPT, "tools": "market"},
    "quant_forecast": {"prompt": QUANT_FORECAST_PROMPT, "tools": "ml"},
    "risk_volatility": {"prompt": RISK_VOLATILITY_PROMPT, "tools": "risk"},
    "decision": {"prompt": DECISION_PROMPT, "tools": "all"},
    "ux_agent": {"prompt": UX_AGENT_PROMPT, "tools": "none"},
}


def _build_toolkit(tool_set="all"):
    if not _AGENTSCOPE_AVAILABLE:
        return None
    toolkit = Toolkit()
    market_tools = [consulter_prix, lister_produits, lister_marches,
                    enregistrer_prevision, analyser_tendance]
    ml_tools = [predire_rendement_cultures, prevoir_volatilite,
                obtenir_kpi_agriculture, consulter_meteo_region, rafraichir_donnees_climat]
    risk_tools = [evaluer_risque_financier, segmenter_agriculteurs,
                  prevoir_volatilite, consulter_meteo_region]
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
    seen = set()
    for t in tools:
        if t.__name__ not in seen:
            toolkit.register_tool_function(t)
            seen.add(t.__name__)
    return toolkit


def _create_model(model_name: str):
    """Create an AgentScope model from a model name string.

    Supported prefixes:
      deepseek-*  → OpenAIChatModel via api.deepseek.com
      qwen-*      → DashScopeChatModel
      gemini-*    → GeminiChatModel (fallback for vision/audio only)
    """
    if not _AGENTSCOPE_AVAILABLE:
        raise RuntimeError("AgentScope not available")

    if model_name.startswith("deepseek-"):
        from app.key_rotation import get_deepseek_key
        return (
            OpenAIChatModel(
                model_name=model_name,
                api_key=get_deepseek_key(),
                client_kwargs={"base_url": DEEPSEEK_BASE_URL},
                stream=False,
            ),
            DeepSeekChatFormatter(),
        )

    if model_name.startswith("qwen-"):
        from agentscope.model import DashScopeChatModel
        from agentscope.formatter import DashScopeChatFormatter
        return (
            DashScopeChatModel(
                model_name=model_name,
                api_key=os.environ.get("DASHSCOPE_API_KEY", ""),
                stream=False,
            ),
            DashScopeChatFormatter(),
        )

    # gemini-* kept as last-resort (vision/audio)
    from agentscope.model import GeminiChatModel
    from agentscope.formatter import GeminiChatFormatter
    from app.key_rotation import get_gemini_key
    return (
        GeminiChatModel(
            model_name=model_name,
            api_key=get_gemini_key(),
            stream=False,
        ),
        GeminiChatFormatter(),
    )


def _get_agent(agent_type: str, model_name: str = None):
    """Get or create a specialized agent for the given model."""
    if model_name is None:
        model_name = select_model(agent_type)

    key = f"{agent_type}_{model_name}"
    if key not in _agents:
        config = AGENT_CONFIGS.get(agent_type, AGENT_CONFIGS["coordinator"])
        model, formatter = _create_model(model_name)
        _agents[key] = ReActAgent(
            name=f"AgriTogo-{agent_type}",
            sys_prompt=config["prompt"],
            model=model,
            formatter=formatter,
            memory=InMemoryMemory(),
            toolkit=_build_toolkit(config["tools"]),
        )
    return _agents[key]


async def _call_agent(agent_type: str, question: str, model_name: str = None) -> str:
    """Call a specialized agent; rotates DeepSeek keys automatically on 429."""
    chosen = model_name or select_model(agent_type)
    try:
        agent = _get_agent(agent_type, chosen)
        msg = Msg(name="user", role="user", content=question)
        response = await agent(msg)
        return response.get_text_content()
    except Exception as e:
        err = str(e).lower()
        if "429" in err or "quota" in err or "rate" in err or "resource_exhausted" in err:
            if chosen.startswith("deepseek-"):
                from app.key_rotation import (
                    mark_deepseek_key_exhausted, rotate_deepseek_key,
                    get_deepseek_keys_count,
                )
                mark_deepseek_key_exhausted()
                for _ in range(get_deepseek_keys_count() - 1):
                    rotate_deepseek_key()
                    try:
                        _agents.pop(f"{agent_type}_{chosen}", None)
                        agent = _get_agent(agent_type, chosen)
                        msg = Msg(name="user", role="user", content=question)
                        response = await agent(msg)
                        return "[🔄 Clé DeepSeek rotée] " + response.get_text_content()
                    except Exception:
                        continue
            return "⚠️ Service temporairement indisponible (quota atteint). Réessayez dans 60 secondes."
        raise


async def _debate(question: str) -> dict:
    """Multi-agent debate on high-stakes queries.

    All three rounds use deepseek-reasoner for maximum precision.
    """
    # Step 1: decision agent proposes strategy
    proposal = await _call_agent("decision", question, "deepseek-reasoner")

    # Step 2: risk agent critiques with quantitative analysis
    critique_q = (
        f"Voici une recommandation stratégique. Critique-la avec des données "
        f"quantitatives et identifie les failles:\n\n{proposal}\n\n"
        f"Question originale: {question}"
    )
    critique = await _call_agent("risk_volatility", critique_q, "deepseek-reasoner")

    # Step 3: coordinator arbitrates
    arbitration_q = (
        f"DÉBAT MULTI-AGENT:\n\n"
        f"📌 PROPOSITION:\n{proposal}\n\n"
        f"📌 CRITIQUE QUANTITATIVE:\n{critique}\n\n"
        f"Arbitre ce débat. Donne la décision finale avec confiance et justification."
    )
    final = await _call_agent("coordinator", arbitration_q, "deepseek-reasoner")

    return {
        "proposal": proposal,
        "critique": critique,
        "final_decision": final,
        "debate_used": True,
    }


async def process_query(question: str, audience: str = "farmer") -> dict:
    """Main entry point for the Decision Intelligence Engine."""
    timestamp = datetime.now().isoformat()
    agent_type = route_query(question)
    model_name = select_model(agent_type)  # auto-selected
    debate = should_debate(question)

    result = {
        "timestamp": timestamp,
        "query": question,
        "agent_type": agent_type,
        "model_used": model_name,
        "debate_used": debate,
        "audience": audience,
    }

    try:
        if debate:
            # High-stakes: escalate all rounds to deepseek-reasoner
            debate_result = await _debate(question)
            result.update(debate_result)
            result["model_used"] = "deepseek-reasoner"
            raw_response = debate_result["final_decision"]
        else:
            raw_response = await _call_agent(agent_type, question, model_name)
            result["response"] = raw_response

        # Detect model errors before passing to UX agent
        if raw_response and ("⚠️" in raw_response or "indisponible" in raw_response
                            or "quota" in raw_response.lower()):
            result["error"] = raw_response
            result["formatted_response"] = (
                "🔧 Le service est temporairement surchargé. "
                "Veuillez réessayer dans quelques secondes. "
                "Si le problème persiste, contactez votre coopérative."
            )
        elif agent_type != "ux_agent" and audience in ("farmer", "cooperative"):
            ux_q = f"Reformule pour un {audience} togolais:\n\n{raw_response}"
            try:
                # UX reformulation always uses fast model
                result["formatted_response"] = await _call_agent(
                    "ux_agent", ux_q, "deepseek-chat"
                )
            except Exception:
                result["formatted_response"] = raw_response
        else:
            result["formatted_response"] = raw_response

    except Exception as e:
        err_str = str(e)
        result["error"] = err_str
        if "429" in err_str or "quota" in err_str.lower() or "rate" in err_str.lower():
            result["formatted_response"] = (
                "🔧 Le service est temporairement surchargé (quota atteint). "
                "Réessayez dans 30 secondes."
            )
        else:
            result["formatted_response"] = "⚠️ Une erreur est survenue. Réessayez dans un instant."

    _memory_store.append(result)
    return result


def get_memory(limit=20):
    return _memory_store[-limit:]


def add_feedback(index: int, outcome: str, actual_price: float = None):
    if 0 <= index < len(_memory_store):
        _memory_store[index]["feedback"] = {
            "outcome": outcome,
            "actual_price": actual_price,
            "feedback_date": datetime.now().isoformat(),
        }
