# agents/agent_negociation.py
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, AIMessage
# On importe les outils depuis le dossier outils/
from outils.outils_negociation import get_property_negotiation_details
from state import AgentState

def create_negotiation_agent(api_key: str):
    """
    Crée la logique de noeud et les outils de l'Agent Négociation (Le Closer).
    Utilise Gemini 1.5 Pro pour une logique de négociation complexe et stable.
    """
    
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-pro", # Pro pour une logique de négociation fine et stable
        google_api_key=api_key,
        temperature=0.4 # Un peu de créativité pour l'argumentation
    ) 
    
    tools = [get_property_negotiation_details]
    llm_with_tools = llm.bind_tools(tools)

    prompt_template = """Tu es un négociateur immobilier expert représentant le PROPRIÉTAIRE (l'annonceur).
    
    TA MISSION : Vendre le bien au meilleur prix possible.
    
    RÈGLES STRICTES DE NÉGOCIATION :
    - NE JAMAIS révéler le 'floor_price' au client. C'est ton secret.
    - Si l'offre du client est < floor_price : Refuse poliment et justifie le prix (atouts, marché).
    - Si l'offre est entre floor_price et listing_price : Propose une contre-offre (couper la poire en deux).
    - Si l'offre est >= listing_price : Accepte avec enthousiasme.
    
    {context_instruction}
    """
    
    def negotiation_node(state: AgentState):
        messages = state["messages"]
        active_id = state.get("active_property_id")
        
        context_instruction = ""
        
        if active_id:
            # Si un ID est dans l'état, on force l'appel à l'outil pour récupérer les marges
            context_instruction = (
                f"IMPORTANT : L'utilisateur est intéressé par le bien ID: {active_id}. "
                f"ACTION IMMÉDIATE : Appelle TOUT DE SUITE l'outil 'get_property_negotiation_details' avec l'ID {active_id} "
                f"pour obtenir le prix plancher et les arguments de vente."
            )
        else:
            # Si l'agent de négociation est appelé sans ID (erreur de routage ou début de conversation vague)
            context_instruction = "L'utilisateur veut négocier mais tu ne sais pas quel bien. Demande-lui poliment l'ID du bien ou de coller la référence."

        full_prompt = prompt_template.format(context_instruction=context_instruction)
        
        response = llm_with_tools.invoke([SystemMessage(content=full_prompt)] + messages)
        
        # Le Négociateur pourrait déléguer une question légale (par exemple: "Quelles sont les taxes pour ce type de bien?")
        # Pour une version plus avancée, on pourrait analyser la réponse et mettre à jour `delegation_query` ici si nécessaire.
        
        return {"messages": [response]}
    
    return negotiation_node, tools