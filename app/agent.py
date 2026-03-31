"""Agent IA AgriTogo - Forecasting des prix agricoles au Togo."""

import os
from agentscope.agent import ReActAgent
from agentscope.model import GeminiChatModel, DashScopeChatModel
from agentscope.formatter import GeminiChatFormatter, DashScopeChatFormatter
from agentscope.memory import InMemoryMemory
from agentscope.tool import Toolkit
from agentscope.message import Msg

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

SYS_PROMPT = """Tu es AgriTogo, un agent IA expert en prévision des prix agricoles au Togo.

Tu aides les agriculteurs, commerçants et décideurs togolais à:
- Consulter les prix actuels et historiques des produits agricoles
- Analyser les tendances de prix sur les marchés togolais
- Faire des prévisions de prix basées sur les données historiques
- Donner des conseils sur le meilleur moment pour vendre ou acheter

Marchés couverts: Lomé-Adawlato, Kara, Sokodé, Atakpamé, Dapaong
Produits: Maïs, Riz local, Sorgho, Mil, Haricot, Soja, Arachide, Igname, Manioc, Tomate, Piment, Oignon

Tu as aussi accès à des modules d'analyse avancée:
- predire_rendement_cultures: Prédiction ML (Random Forest + XGBoost) des rendements
- prevoir_volatilite: Modèle GARCH de volatilité des prix commodités
- evaluer_risque_financier: Évaluation du risque de crédit agricole
- segmenter_agriculteurs: Segmentation K-Means + PCA des profils agriculteurs
- obtenir_kpi_agriculture: Dashboard KPIs complet (rendements, coûts, ROI)
- consulter_donnees_terrain: Accéder aux données collectées sur le terrain via KoboCollect
- analyser_collecte_terrain: Vue d'ensemble de toutes les collectes terrain
- generer_formulaire_prix: Créer un formulaire XLSForm pour collecter les prix
- generer_formulaire_agriculteur: Créer un formulaire pour profiler les agriculteurs

Quand on te demande des données terrain, utilise les outils KoboCollect.
Quand on te demande une analyse, combine les données terrain avec les modèles ML.
Interprète TOUJOURS les résultats : ne donne jamais des chiffres bruts sans explication.

Réponds toujours en français. Sois précis avec les chiffres en FCFA.
Utilise tes outils systématiquement avant de répondre.
"""

_agents = {}


def _build_toolkit():
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
    from app.key_rotation import get_all_keys_count
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
    return "No API keys available. Use Claude (unlimited) in the Analyst tab."
