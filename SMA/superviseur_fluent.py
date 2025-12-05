# superviseur_fluent.py
import os
import re
from typing import Literal, Optional
from dotenv import load_dotenv

# LangChain / LangGraph
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from pydantic import BaseModel, Field

# Imports des modules modularisés
from state import AgentState 
from agents.agent_recherche import create_search_agent # Assurez-vous d'avoir ces fichiers
from agents.agent_negociation import create_negotiation_agent
from agents.agent_juridique import create_droit_agent

# Imports Outils
from outils.outils_immobilier import search_properties, get_property_statistics
from outils.outils_negociation import get_property_negotiation_details
from outils.outils_droit import query_droit_immobilier

load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# ==================== 1. ROUTEUR / SUPERVISEUR OPTIMISÉ ====================

class RouteResponse(BaseModel):
    """Choisit le prochain agent à activer."""
    next: Literal["SEARCH_AGENT", "NEGOTIATION_AGENT", "GENERAL_CHAT", "JURIDIQUE_ADVISOR"] = Field(
        description="L'agent vers lequel router la demande."
    )

def detect_property_id(text: str) -> Optional[str]:
    """Fonction utilitaire pour repérer un ID MongoDB (24 chars hex)"""
    # Regex qui cherche une séquence de 24 caractères hexadécimaux
    match = re.search(r'\b[a-f0-9]{24}\b', text, re.IGNORECASE)
    return match.group(0) if match else None

def supervisor_node(state: AgentState):
    
    # 1. OPTIMISATION RAPIDITÉ : Utilisation de Flash pour le routage
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=GOOGLE_API_KEY, temperature=0)

    last_msg = state["messages"][-1].content
    
    # --- 1. INTELLIGENCE RÉFLEXE (Détection d'ID) ---
    detected_id = detect_property_id(str(last_msg))
    if detected_id:
        # L'ID est détecté, on force la négociation
        return {
            "next_agent": "NEGOTIATION_AGENT", 
            "active_property_id": detected_id
        }
    
    # --- 2. GESTION DE LA DÉLÉGATION (Coordination) ---
    # Si un agent a posté une délégation, on ne route pas, on exécute l'agent délégataire
    if state.get("delegation_query"):
        # Ici on doit faire une vérification pour savoir à qui déléguer
        # Pour l'instant, on suppose que seule la recherche et le droit sont délégables.
        # Exemple: L'agent de Négo demande au Juridique si la TVA est incluse.
        # On va utiliser une heuristique simple (LLM-based) pour déterminer la cible
        
        # Ce serait le point d'amélioration pour les agents qui délèguent
        # Pour la simplicité ici, on va s'assurer que c'est l'agent recherché.
        
        # Si on détecte une question légale, on délègue au Juridique.
        if any(w in state["delegation_query"].lower() for w in ["loi", "taxe", "contrat", "notaire", "légal", "bail", "procédure"]):
             # On vide le message utilisateur pour éviter la confusion
            return {"next_agent": "JURIDIQUE_ADVISOR", "messages": [HumanMessage(content=state["delegation_query"])]}
        else:
             # Sinon, on délègue par défaut à la recherche (ou chat général)
            return {"next_agent": "GENERAL_CHAT", "messages": [HumanMessage(content=state["delegation_query"])]}
            
    # --- 3. INTELLIGENCE SÉMANTIQUE (Routage LLM Classique) ---
    system_prompt = """Tu es le routeur d'une agence immobilière IA. Ton rôle est UNIQUEMENT de diriger le client.

    RÈGLES DE ROUTAGE :
    1. Demande de recherche, critères, prix, ville -> 'SEARCH_AGENT'.
    2. Discussion sur un bien précis, négociation, offre, "celui-ci m'intéresse" -> 'NEGOTIATION_AGENT'.
    3. Question sur des lois, contrats, taxes, procédures légales, baux -> 'JURIDIQUE_ADVISOR'.
    4. Salutations simples, blabla -> 'GENERAL_CHAT'.
    """
    
    router = llm.with_structured_output(RouteResponse)
    # Le routeur LLM doit décider
    decision = router.invoke([SystemMessage(content=system_prompt)] + state["messages"])
    
    return {"next_agent": decision.next}

# ==================== 2. CONSTRUCTION DU GRAPHE FINAL ====================

def build_fluent_graph():
    workflow = StateGraph(AgentState)

    # Récupération des agents et outils (maintenant dans d'autres fichiers)
    search_node, search_tools = create_search_agent(GOOGLE_API_KEY)
    negot_node, negot_tools = create_negotiation_agent(GOOGLE_API_KEY)
    droit_node, droit_tools = create_droit_agent(GOOGLE_API_KEY)

    # Ajout des noeuds
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("search_agent", search_node)
    workflow.add_node("negotiation_agent", negot_node)
    workflow.add_node("droit_agent", droit_node)
    
    # NOUVEAU: Agent Chat Général avec personnalité DomusIA
    def general_chat_node(state: AgentState):
        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=GOOGLE_API_KEY, temperature=0.5)
        
        system_prompt = """Tu es DomusIA 🏠, l'assistant immobilier IA le plus cool du Maroc !

🎯 TES TALENTS :
- Recherche de biens immobiliers (villas, appartements, terrains...)
- Négociation et conseils prix
- Expertise juridique immobilière

💬 TON STYLE :
- Sympa, chaleureux, tutoiement
- Concis (c'est WhatsApp, pas un roman !)
- Emojis avec parcimonie
- Proactif : propose toujours la suite

📱 EXEMPLES DE RÉPONSES :

Pour "Bonjour" :
"Hey ! 👋 Bienvenue sur DomusIA !

Je suis ton assistant immobilier IA. Je peux t'aider à :
🔍 Trouver ton bien idéal
💰 Négocier le meilleur prix
⚖️ Répondre à tes questions juridiques

Qu'est-ce qui t'amène aujourd'hui ?"

Pour "Merci" :
"Avec plaisir ! 😊 N'hésite pas si tu as d'autres questions. Bonne recherche ! 🏡"

IMPORTANT : Garde tes réponses COURTES (max 500 caractères).
"""
        response = llm.invoke([SystemMessage(content=system_prompt)] + state["messages"])
        return {"messages": [response]}
        
    workflow.add_node("general_chat", general_chat_node)
    
    # Ajout des nœuds d'outils
    # L'approche LangGraph simplifie grandement ces nœuds
    all_tools = search_tools + negot_tools + droit_tools
    # On ajoute un ToolNode générique pour la flexibilité (même si on peut le garder spécifique)
    # Ici, nous le gardons spécifique pour le moment pour simplifier le retour dans la boucle.
    workflow.add_node("search_tools", ToolNode(search_tools))
    workflow.add_node("negotiation_tools", ToolNode(negot_tools))
    workflow.add_node("droit_tools", ToolNode(droit_tools)) 

    workflow.set_entry_point("supervisor")

    # Logique de routage du superviseur
    workflow.add_conditional_edges(
        "supervisor",
        lambda x: x["next_agent"],
        {
            "SEARCH_AGENT": "search_agent",
            "NEGOTIATION_AGENT": "negotiation_agent",
            "JURIDIQUE_ADVISOR": "droit_agent",
            "GENERAL_CHAT": "general_chat"
        }
    )

    # Fonction pour vérifier si un outil a été appelé
    def should_continue_tools(state: AgentState):
        last_msg = state["messages"][-1]
        # On vérifie si un outil est appelé ou si l'agent a terminé sa tâche
        # (Dans cet exemple, l'agent termine s'il n'appelle pas d'outil)
        return "tools" if hasattr(last_msg, "tool_calls") and last_msg.tool_calls else END

    # Cycles Agent <-> Outils
    workflow.add_conditional_edges("search_agent", should_continue_tools, {"tools": "search_tools", END: END})
    workflow.add_edge("search_tools", "search_agent") # Après l'outil, on revient à l'agent pour formuler la réponse
    
    workflow.add_conditional_edges("negotiation_agent", should_continue_tools, {"tools": "negotiation_tools", END: END})
    workflow.add_edge("negotiation_tools", "negotiation_agent")
    
    workflow.add_conditional_edges("droit_agent", should_continue_tools, {"tools": "droit_tools", END: END})
    workflow.add_edge("droit_tools", "droit_agent")
    
    # La sortie des agents va au superviseur
    # NOUVEAU : On fait passer la sortie des agents au superviseur pour une éventuelle autre étape de routage.
    # Dans une architecture plus simple, ils iraient à END. Ici, on va vers END pour rester simple.
    workflow.add_edge("general_chat", END)
    
    return workflow.compile()

# ==================== MAIN LOOP ====================

if __name__ == "__main__":
    app = build_fluent_graph()
    print("\n--- 🏢 AGENCE IMMOBILIÈRE IA MODULAIRE & RAPIDE ---")
    print("Modes : RECHERCHE | NÉGOCIATION (collez l'ID) | JURIDIQUE (questions sur les lois)")
    
    chat_history = []
    
    while True:
        user_input = input("\n👤 Vous: ")
        if user_input.lower() in ["q", "quit"]: break
        
        chat_history.append(HumanMessage(content=user_input))
        
        # On initialise l'état avec l'historique et on prépare les champs
        inputs = {
            "messages": chat_history, 
            "active_property_id": None, # L'ID sera mis à jour par le superviseur si détecté
            "next_agent": None,
            "delegation_query": None
        }
        
        print("⏳ Réflexion du Superviseur...")
        # L'appel du graphe
        # On augmente le recursion_limit pour les boucles outil/agent
        result = app.invoke(inputs, config={"recursion_limit": 30})
        
        # Mise à jour de l'historique et de l'état (y compris l'ID actif si détecté)
        # L'historique des messages est la clé
        chat_history = result["messages"]
        
        # Affichage propre de la dernière réponse
        print(f"\n🤖 IA: {chat_history[-1].content}")