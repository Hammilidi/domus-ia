# outils/outils_alertes.py - Outils pour la gestion des alertes immobilières

from langchain_core.tools import tool
import json
import asyncio
from typing import Optional

# Import du service d'alertes
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@tool
def create_property_alert(
    phone_number: str,
    user_name: str,
    property_type: str = None,
    transaction_type: str = None,
    location: str = None,
    min_price: float = None,
    max_price: float = None,
    bedrooms: int = None,
    standing: str = None
) -> str:
    """
    Créer une alerte pour être notifié quand un nouveau bien correspond aux critères.
    Utilise cet outil quand l'utilisateur dit 'oui' pour créer une alerte après une recherche sans résultat.
    
    Args:
        phone_number: Numéro WhatsApp de l'utilisateur (format: +212...)
        user_name: Nom de l'utilisateur
        property_type: Type de bien recherché (appartement, villa, bureau, etc.)
        transaction_type: 'location' ou 'vente'
        location: Ville ou quartier
        min_price: Prix minimum
        max_price: Prix maximum
        bedrooms: Nombre de chambres minimum
        standing: Niveau de standing souhaité
    
    Returns:
        Confirmation de création de l'alerte
    """
    from services.alert_service import create_alert
    
    criteria = {}
    if property_type: criteria["property_type"] = property_type
    if transaction_type: criteria["transaction_type"] = transaction_type
    if location: criteria["location"] = location
    if min_price: criteria["min_price"] = min_price
    if max_price: criteria["max_price"] = max_price
    if bedrooms: criteria["bedrooms"] = bedrooms
    if standing: criteria["standing"] = standing
    
    if not criteria:
        return json.dumps({
            "success": False,
            "message": "Aucun critère spécifié pour l'alerte."
        }, ensure_ascii=False)
    
    # Créer l'alerte de manière synchrone (wrapper)
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    alert_id = loop.run_until_complete(create_alert(phone_number, user_name, criteria))
    
    if alert_id:
        # Formater les critères pour le message
        criteria_parts = []
        if property_type: criteria_parts.append(f"Type: {property_type}")
        if transaction_type: criteria_parts.append(f"{'Location' if transaction_type == 'location' else 'Achat'}")
        if location: criteria_parts.append(f"📍 {location}")
        if min_price or max_price:
            price_range = f"{int(min_price or 0):,} - {int(max_price) if max_price else '∞'} MAD".replace(",", " ")
            criteria_parts.append(f"💰 {price_range}")
        if bedrooms: criteria_parts.append(f"🛏️ {bedrooms}+ ch")
        
        return json.dumps({
            "success": True,
            "alert_id": alert_id,
            "message": f"✅ Alerte créée avec succès !\n\n🔔 Je te préviendrai dès qu'un bien correspondant arrive.\n\n📋 Tes critères :\n{' | '.join(criteria_parts)}\n\n💡 Tu peux continuer à chercher d'autres biens en attendant !"
        }, ensure_ascii=False)
    else:
        return json.dumps({
            "success": False,
            "message": "⚠️ Tu as déjà une alerte active avec ces critères !"
        }, ensure_ascii=False)


@tool
def list_my_alerts(phone_number: str) -> str:
    """
    Lister toutes les alertes actives d'un utilisateur.
    
    Args:
        phone_number: Numéro WhatsApp de l'utilisateur
    
    Returns:
        Liste des alertes actives
    """
    from services.alert_service import get_user_alerts, format_alert_message
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    alerts = loop.run_until_complete(get_user_alerts(phone_number))
    
    if not alerts:
        return json.dumps({
            "count": 0,
            "message": "Tu n'as aucune alerte active pour le moment.\n\n💡 Lance une recherche et je te proposerai de créer une alerte si aucun bien ne correspond !"
        }, ensure_ascii=False)
    
    message = f"🔔 Tu as {len(alerts)} alerte(s) active(s) :\n\n"
    for i, alert in enumerate(alerts, 1):
        criteria = alert.get("criteria", {})
        criteria_str = format_alert_message(criteria)
        message += f"{i}. {criteria_str}\n   🆔 `{alert['_id']}`\n\n"
    
    message += "💡 Pour supprimer une alerte, dis-moi son numéro."
    
    return json.dumps({
        "count": len(alerts),
        "alerts": alerts,
        "message": message
    }, ensure_ascii=False)


@tool  
def delete_my_alert(phone_number: str, alert_id: str) -> str:
    """
    Supprimer une alerte.
    
    Args:
        phone_number: Numéro WhatsApp de l'utilisateur
        alert_id: ID de l'alerte à supprimer
    
    Returns:
        Confirmation de suppression
    """
    from services.alert_service import delete_alert
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    success = loop.run_until_complete(delete_alert(alert_id, phone_number))
    
    if success:
        return json.dumps({
            "success": True,
            "message": "✅ Alerte supprimée ! Tu ne recevras plus de notifications pour ces critères."
        }, ensure_ascii=False)
    else:
        return json.dumps({
            "success": False,
            "message": "⚠️ Alerte non trouvée ou déjà supprimée."
        }, ensure_ascii=False)
