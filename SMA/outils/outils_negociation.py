# outils/outils_negociation.py
from langchain_core.tools import tool
from pymongo import MongoClient
from bson import ObjectId
import json
import os
import re
from dotenv import load_dotenv

load_dotenv()

# --- Configuration MongoDB ---
MONGO_USER = os.getenv("MONGO_USER")
MONGO_PASSWORD = os.getenv("MONGO_PASSWORD")
MONGO_HOST = os.getenv("MONGO_HOST", "localhost")
MONGO_PORT = os.getenv("MONGO_PORT", "27017") 
MONGO_DB = os.getenv("MONGO_DB", "listings")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "listings")

# Construction de l'URI
if MONGO_USER and MONGO_PASSWORD:
    MONGODB_URI = f"mongodb://{MONGO_USER}:{MONGO_PASSWORD}@{MONGO_HOST}:{MONGO_PORT}/?authSource=admin"
else:
    MONGODB_URI = f"mongodb://{MONGO_HOST}:{MONGO_PORT}/"

DB_NAME = MONGO_DB
COLLECTION_NAME = MONGO_COLLECTION

def clean_price(price_value):
    """
    Fonction utilitaire pour extraire un nombre propre depuis "600 DH" ou "1 200 €"
    """
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
        except ValueError:
            return 0.0
    return 0.0

@tool
def get_property_negotiation_details(property_id: str) -> str:
    """
    Récupère les détails d'un bien spécifique par son ID pour la négociation.
    Retourne le prix affiché et calcule le prix minimum (marge) accepté.
    """
    client = None
    try:
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        db = client[DB_NAME]
        collection = db[COLLECTION_NAME]
        
        clean_id = str(property_id).strip()
        prop = None
        
        # Recherche Robuste (ObjectId OU String)
        try:
            if ObjectId.is_valid(clean_id):
                prop = collection.find_one({"_id": ObjectId(clean_id)})
        except:
            pass

        if not prop:
            prop = collection.find_one({"_id": clean_id})
            
        if not prop:
            return json.dumps({
                "error": f"Bien introuvable avec l'ID : {clean_id}", 
                "suggestion": "Vérifiez l'ID dans la base de données."
            })

        # --- LOGIQUE DE MARGE & PRIX ---
        raw_price = prop.get('price', 0)
        listing_price = clean_price(raw_price)
        
        location = str(prop.get('location', '')).lower()
        prop_type = str(prop.get('property_type', '')).lower()
        
        margin_percent = 0.07 
        
        if "marrakech" in location or "casablanca" in location:
            margin_percent = 0.05 
        elif "villa" in prop_type:
            margin_percent = 0.10 
            
        min_price = listing_price * (1 - margin_percent)
        
        # Gestion des extras
        extras = []
        for k, v in prop.items():
            if k in ["piscine", "balcon", "ascenseur", "jardin", "parking"]:
                if v is True or str(v).lower() in ['true', '1', 'yes', 'oui']:
                    extras.append(k)

        # Contexte pour l'agent
        context = {
            "property_title": prop.get('title', 'Bien Immobilier'),
            "location_raw": prop.get('location', 'Non spécifiée'),
            "listing_price": listing_price,
            "currency": "DH",
            "floor_price": int(min_price), 
            "features": {
                "surface": prop.get('surface', 'N/A'),
                "rooms": prop.get('rooms', 'N/A'),
                "extras_list": extras
            },
            "negotiation_strategy": (
                f"Le prix affiché est {int(listing_price)} DH. "
                f"Tu peux descendre jusqu'à {int(min_price)} DH maximum (ton 'floor_price'). "
                f"Si le client propose moins, refuse en mettant en avant les atouts : {', '.join(extras)}."
            )
        }
        
        return json.dumps(context, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"error": f"Erreur système : {str(e)}"})
        
    finally:
        if client:
            client.close()