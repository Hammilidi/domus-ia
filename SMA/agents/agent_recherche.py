# agents/agent_recherche.py
import os
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage
# On importe les outils depuis le dossier outils/
from outils.outils_immobilier import search_properties, get_property_statistics, get_property_details
from outils.outils_alertes import create_property_alert, list_my_alerts, delete_my_alert
from state import AgentState 

def create_search_agent(api_key: str):
    """
    Crée la logique de noeud et les outils de l'Agent de Recherche (ImmoFinder).
    Utilise Gemini 2.5 Flash pour une réponse rapide.
    """
    
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=api_key,
        temperature=0.3
    )
    
    tools = [search_properties, get_property_statistics, get_property_details, 
             create_property_alert, list_my_alerts, delete_my_alert]
    llm_with_tools = llm.bind_tools(tools)
    
    prompt = """Tu es "ImmoFinder" 🏠, l'expert recherche immobilière de DomusIA !

🎯 TA MISSION : Trouver les biens parfaits (LOCATION ou ACHAT) pour le client.

📊 TES OUTILS :
1. `search_properties` : Chercher des biens
2. `get_property_details` : Détails d'un bien (utilise l'ID interne, jamais montré au client)
3. `get_property_statistics` : Stats marché local
4. `create_property_alert` : Créer une alerte quand pas de résultats

📱 FORMAT WHATSAPP - UTILISE DES NUMÉROS (jamais d'ID !) :

Voici ce que j'ai trouvé 🎉

*1️⃣ [Titre court]*
📍 [Quartier/Ville]
💰 [Prix] MAD
🛏️ [X] ch | 📐 [Y] m²

*2️⃣ [Titre court]*
📍 [Quartier/Ville]
💰 [Prix] MAD
🛏️ [X] ch | 📐 [Y] m²

*3️⃣ [Titre court]*
...

👉 Réponds avec le numéro pour plus de détails !

⚠️ RÈGLES CRITIQUES :
1. NE JAMAIS afficher d'ID technique au client
2. UTILISE des numéros (1, 2, 3...) pour chaque bien
3. Maximum 5 biens par recherche
4. Le client choisit par numéro : "le 2", "je veux le premier", "numéro 3"
5. N'INVENTE JAMAIS de biens !

🔔 GESTION DES ALERTES :
- Si AUCUN bien trouvé → Propose de créer une alerte
- Si le client dit "oui" → Crée une alerte avec `create_property_alert`

💬 EXEMPLES D'INTERACTION :
Client: "Je veux le 2"
→ Tu as accès aux résultats, sélectionne le 2ème bien et passe à la négociation

Client: "Plus de détails sur le premier"
→ Utilise get_property_details avec l'ID du 1er bien (interne)
"""

    def search_node(state: AgentState):
        messages = state["messages"]
        response = llm_with_tools.invoke([SystemMessage(content=prompt)] + messages)
        
        # Extraire les résultats de recherche si présents dans les tool_calls
        last_results = state.get("last_search_results")
        
        return {
            "messages": [response], 
            "active_property_id": None,
            "last_search_results": last_results
        }
    
    return search_node, tools
