# services/alert_service.py - Service de gestion des alertes immobilières
"""
Ce service gère les alertes de recherche pour les utilisateurs.
Quand aucun bien ne correspond aux critères, on enregistre l'alerte.
Un job périodique vérifie les nouveaux biens et notifie les utilisateurs.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pymongo import MongoClient
from bson import ObjectId
import logging
import os
import json
import re
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Configuration MongoDB
MONGO_USER = os.getenv("MONGO_USER")
MONGO_PASSWORD = os.getenv("MONGO_PASSWORD")
MONGO_HOST = os.getenv("MONGO_HOST", "localhost")
MONGO_PORT = os.getenv("MONGO_PORT", "27017")
MONGO_DB = os.getenv("MONGO_DB", "listings")

if MONGO_USER and MONGO_PASSWORD:
    MONGODB_URI = f"mongodb://{MONGO_USER}:{MONGO_PASSWORD}@{MONGO_HOST}:{MONGO_PORT}/?authSource=admin"
else:
    MONGODB_URI = f"mongodb://{MONGO_HOST}:{MONGO_PORT}/"


def get_alerts_collection():
    """Récupérer la collection des alertes"""
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    return client[MONGO_DB]["property_alerts"]


def clean_price(price_value):
    """Extrait un nombre flottant depuis une valeur de prix"""
    if isinstance(price_value, (int, float)):
        return float(price_value)
    if not price_value:
        return 0.0
    str_val = str(price_value)
    match = re.search(r"([0-9\s\.,]+)", str_val)
    if match:
        clean_str = match.group(1).replace(" ", "").replace("\u00a0", "").replace(",", ".")
        try:
            return float(clean_str)
        except:
            return 0.0
    return 0.0


async def create_alert(
    phone_number: str,
    user_name: str,
    criteria: Dict[str, Any]
) -> str:
    """
    Créer une nouvelle alerte de recherche.
    
    Args:
        phone_number: Numéro WhatsApp de l'utilisateur
        user_name: Nom de l'utilisateur
        criteria: Critères de recherche (property_type, location, min_price, max_price, etc.)
    
    Returns:
        ID de l'alerte créée
    """
    try:
        collection = get_alerts_collection()
        
        # Vérifier si une alerte similaire existe déjà
        existing = collection.find_one({
            "phone_number": phone_number,
            "criteria": criteria,
            "status": "active"
        })
        
        if existing:
            logger.info(f"Alerte similaire existante pour {phone_number}")
            return str(existing["_id"])
        
        alert = {
            "phone_number": phone_number,
            "user_name": user_name,
            "criteria": criteria,
            "status": "active",
            "created_at": datetime.utcnow(),
            "last_checked_at": datetime.utcnow(),
            "last_property_check": datetime.utcnow(),  # Pour tracker les nouvelles propriétés
            "notifications_sent": 0,
            "max_notifications": 10  # Limite de notifications par alerte
        }
        
        result = collection.insert_one(alert)
        logger.info(f"✅ Alerte créée pour {phone_number}: {criteria}")
        
        return str(result.inserted_id)
        
    except Exception as e:
        logger.error(f"Erreur création alerte: {e}")
        return None


async def get_user_alerts(phone_number: str) -> List[Dict[str, Any]]:
    """Récupérer toutes les alertes actives d'un utilisateur"""
    try:
        collection = get_alerts_collection()
        
        alerts = list(collection.find({
            "phone_number": phone_number,
            "status": "active"
        }))
        
        for alert in alerts:
            alert["_id"] = str(alert["_id"])
            
        return alerts
        
    except Exception as e:
        logger.error(f"Erreur récupération alertes: {e}")
        return []


async def delete_alert(alert_id: str, phone_number: str) -> bool:
    """Supprimer une alerte"""
    try:
        collection = get_alerts_collection()
        
        result = collection.update_one(
            {"_id": ObjectId(alert_id), "phone_number": phone_number},
            {"$set": {"status": "deleted", "deleted_at": datetime.utcnow()}}
        )
        
        return result.modified_count > 0
        
    except Exception as e:
        logger.error(f"Erreur suppression alerte: {e}")
        return False


async def check_new_properties_for_alerts() -> List[Dict[str, Any]]:
    """
    Vérifier s'il y a de nouvelles propriétés qui matchent les alertes.
    Retourne une liste de notifications à envoyer.
    
    À appeler périodiquement (toutes les heures par exemple).
    """
    notifications = []
    
    try:
        alerts_collection = get_alerts_collection()
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        properties_collection = client[MONGO_DB]["listings"]
        
        # Récupérer toutes les alertes actives
        active_alerts = list(alerts_collection.find({
            "status": "active",
            "notifications_sent": {"$lt": 10}  # Limite atteinte ?
        }))
        
        for alert in active_alerts:
            criteria = alert.get("criteria", {})
            last_check = alert.get("last_property_check", datetime.utcnow() - timedelta(days=1))
            
            # Construire la requête MongoDB
            query = {"scraped_at": {"$gt": last_check}}  # Seulement les nouveaux
            
            # Appliquer les critères
            if criteria.get("property_type"):
                query["$or"] = [
                    {"property_type": {"$regex": criteria["property_type"], "$options": "i"}},
                    {"title": {"$regex": criteria["property_type"], "$options": "i"}}
                ]
            
            if criteria.get("location"):
                loc_query = {"$regex": criteria["location"], "$options": "i"}
                if "$or" in query:
                    query["$and"] = [
                        {"$or": query.pop("$or")},
                        {"$or": [
                            {"location": loc_query},
                            {"adresse": loc_query},
                            {"title": loc_query}
                        ]}
                    ]
                else:
                    query["$or"] = [
                        {"location": loc_query},
                        {"adresse": loc_query}
                    ]
            
            # Chercher les nouvelles propriétés
            new_properties = list(properties_collection.find(query).limit(5))
            
            # Filtrer par prix
            matching_properties = []
            for prop in new_properties:
                price = clean_price(prop.get("price", 0))
                
                if criteria.get("min_price") and price < criteria["min_price"]:
                    continue
                if criteria.get("max_price") and price > criteria["max_price"]:
                    continue
                
                matching_properties.append({
                    "id": str(prop["_id"]),
                    "title": prop.get("title", "Bien immobilier"),
                    "price": price,
                    "location": prop.get("adresse", prop.get("location", "")),
                    "url": prop.get("url", "")
                })
            
            if matching_properties:
                notifications.append({
                    "phone_number": alert["phone_number"],
                    "user_name": alert.get("user_name", ""),
                    "alert_id": str(alert["_id"]),
                    "criteria": criteria,
                    "properties": matching_properties[:3]  # Max 3 biens par notification
                })
                
                # Mettre à jour l'alerte
                alerts_collection.update_one(
                    {"_id": alert["_id"]},
                    {
                        "$set": {"last_property_check": datetime.utcnow()},
                        "$inc": {"notifications_sent": 1}
                    }
                )
        
        return notifications
        
    except Exception as e:
        logger.error(f"Erreur vérification alertes: {e}")
        return []


def format_alert_message(criteria: Dict[str, Any]) -> str:
    """Formater les critères d'alerte en message lisible"""
    parts = []
    
    if criteria.get("property_type"):
        parts.append(f"Type: {criteria['property_type']}")
    if criteria.get("transaction_type"):
        parts.append(f"{'Location' if criteria['transaction_type'] == 'location' else 'Achat'}")
    if criteria.get("location"):
        parts.append(f"📍 {criteria['location']}")
    if criteria.get("min_price") or criteria.get("max_price"):
        min_p = criteria.get("min_price", 0)
        max_p = criteria.get("max_price", "∞")
        parts.append(f"💰 {int(min_p):,} - {max_p} MAD".replace(",", " "))
    if criteria.get("bedrooms"):
        parts.append(f"🛏️ {criteria['bedrooms']}+ ch")
    
    return " | ".join(parts) if parts else "Critères personnalisés"


def format_notification_message(notification: Dict[str, Any]) -> str:
    """Formater le message de notification WhatsApp"""
    user_name = notification.get("user_name", "")
    criteria = notification.get("criteria", {})
    properties = notification.get("properties", [])
    
    greeting = f"Hey {user_name} ! 👋\n\n" if user_name else "Hey ! 👋\n\n"
    
    message = f"""{greeting}🎉 *Bonne nouvelle !* De nouveaux biens correspondent à ta recherche :

🔍 *Tes critères :* {format_alert_message(criteria)}

"""
    
    for prop in properties[:3]:
        price_str = f"{int(prop['price']):,} MAD".replace(",", " ") if prop['price'] > 0 else "Prix sur demande"
        message += f"""🏡 *{prop['title'][:50]}*
📍 {prop['location'][:30]}
💰 {price_str}
🆔 `{prop['id']}`
---
"""
    
    message += "\n💬 Réponds avec l'ID pour plus de détails !"
    
    return message
