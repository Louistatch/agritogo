"""Agent IA AgriTogo - Forecasting des prix agricoles au Togo."""

import os

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
from app.key_rotation import get_gemini_key, rotate_gemini_key

SYS_PROMPT = """Tu es AgriTogo, le Decision Intelligence Engine v2.0 pour l'agriculture resiliente au Togo et en Afrique de l'Ouest.

Tu n'es PAS un agent generique. Tu es une application specialisee qui resout des defis agricoles reels pour les petits exploitants togolais, cooperatives, conseillers et projets (FIDA, Banque Mondiale, CTOP).

Ton expertise combine:
- Connaissances agronomiques (production vegetale, irrigation, conservation des sols, chaines de valeur: gingembre, cacao, ananas, maraichage)
- Data science et ingenierie financiere (prediction de rendement, volatilite GARCH, risque de credit, segmentation agriculteurs)
- Experience terrain de 8+ ans au Togo (S&E digital avec KoBoToolbox, structuration de 200+ cooperatives, mobilisation de 500M+ FCFA)

Outils disponibles:
- consulter_prix, lister_produits, lister_marches, analyser_tendance, enregistrer_prevision
- predire_rendement_cultures (par culture: Mais, Riz, Sorgho, Soja, Manioc, Igname)
- prevoir_volatilite (GARCH par produit)
- evaluer_risque_financier (scoring par region et taille)
- segmenter_agriculteurs (K-Means + PCA)
- obtenir_kpi_agriculture (rendements, couts, ROI)
- consulter_donnees_terrain, analyser_collecte_terrain (KoboCollect)
- generer_formulaire_prix, generer_formulaire_agriculteur (XLSForm)

Regles strictes:
1. Reste TOUJOURS dans le personnage AgriTogo: pratique, ancre terrain, actionnable.
2. Utilise tes outils AVANT de repondre. Ne reponds jamais sans donnees.
3. Ne fabrique jamais de chiffres. Base tes reponses sur les donnees ou indique clairement les limites.
4. Interprete TOUJOURS les resultats: jamais de chiffres bruts sans explication.

Format de sortie obligatoire:
AgriTogo Decision Engine:
Analyse de la situation: [synthese contextualisee au Togo]
Recommandations concretes: [points actionnables]
Risques et precautions: [si applicable]
Prochaines etapes: [1, 2, 3...]
Donnees utilisees: [outils utilises ou donnees requises]

Termine chaque reponse par: "Comment puis-je vous aider davantage sur vos defis agricoles?"
"""

_agents = {}


def _build_toolkit():
    if not _AGENTSCOPE_AVAILABLE:
        return None
    toolkit = Toolkit()
    for fn in [consulter_prix, lister_produits, lister_marches,
               enregistrer_prevision, analyser_tendance,
               predire_rendement_cultures, prevoir_volatilite,
               evaluer_risque_financier, segmenter_agriculteurs,
               obtenir_kpi_agriculture,
               consulter_donnees_terrain, analyser_collecte_terrain,
               generer_formulaire_prix, generer_formulaire_agriculteur]:
        toolkit.register_tool_function(fn)
    return toolkit


def _create_gemini_agent(api_key):
    """Create a Gemini agent with a specific key."""
    return ReActAgent(
        name="AgriTogo",
        sys_prompt=SYS_PROMPT,
        model=GeminiChatModel(
            model_name="gemini-2.5-flash",
            api_key=api_key,
            stream=False,
        ),
        formatter=GeminiChatFormatter(),
        memory=InMemoryMemory(),
        toolkit=_build_toolkit(),
    )


def _get_agent(model_choice="gemini"):
    global _agents
    if model_choice == "qwen":
        if "qwen" not in _agents:
            _agents["qwen"] = ReActAgent(
                name="AgriTogo",
                sys_prompt=SYS_PROMPT,
                model=DashScopeChatModel(
                    model_name="qwen-max",
                    api_key=os.environ.get("DASHSCOPE_API_KEY", ""),
                    stream=False,
                ),
                formatter=DashScopeChatFormatter(),
                memory=InMemoryMemory(),
                toolkit=_build_toolkit(),
            )
        return _agents["qwen"]
    else:
        key = get_gemini_key()
        cache_key = f"gemini_{key[-6:]}"
        if cache_key not in _agents:
            _agents[cache_key] = _create_gemini_agent(key)
        return _agents[cache_key]


async def ask_agent(question: str, model_choice: str = "gemini") -> str:
    """Pose une question avec rotation automatique des 3 clés Gemini."""
    if not _AGENTSCOPE_AVAILABLE:
        return "⚠️ AgentScope non disponible. Vérifiez l'installation des dépendances."
    from app.key_rotation import get_all_keys_count, get_gemini_key
    # Debug: log key availability
    key_preview = get_gemini_key()
    print(f"[AGENT] key available: {'YES' if key_preview else 'NO'}, count: {get_all_keys_count()}")
    max_tries = get_all_keys_count()
    for attempt in range(max_tries):
        try:
            agent = _get_agent("gemini")
            msg = Msg(name="user", role="user", content=question)
            response = await agent(msg)
            return response.get_text_content()
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "quota" in err or "resource_exhausted" in err:
                rotate_gemini_key()
                if attempt < max_tries - 1:
                    continue
                return "All Gemini API keys have reached their daily quota. Please use Claude (unlimited) in the Analyst tab."
            return f"Error: {e}"
    return f"No API keys available (GEMINI_API_KEY_1/2/3 not set). Use Claude (unlimited) in the Analyst tab."
