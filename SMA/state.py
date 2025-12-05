# state.py
import operator
from typing import TypedDict, Annotated, Sequence, Optional, List, Dict, Any

from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    """
    Représente l'état partagé entre tous les agents du système.
    """
    messages: Annotated[Sequence[BaseMessage], operator.add]
    next_agent: str
    active_property_id: Optional[str] 
    
    # NOUVEAU: Permet à un agent de poser une question à un autre (délégation)
    delegation_query: Optional[str]
    
    # NOUVEAU: Stocke les derniers résultats de recherche pour sélection par numéro
    # Format: [{"id": "...", "titre": "...", "prix": "...", ...}, ...]
    last_search_results: Optional[List[Dict[str, Any]]]