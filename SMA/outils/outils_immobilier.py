from langchain_core.tools import tool
from pymongo import MongoClient
import json
from dotenv import load_dotenv
import os
import re

load_dotenv()

# Configuration Robuste
MONGO_USER = os.getenv("MONGO_USER")
MONGO_PASSWORD = os.getenv("MONGO_PASSWORD")
MONGO_HOST = os.getenv("MONGO_HOST", "localhost")
MONGO_PORT = os.getenv("MONGO_PORT", "27017")
MONGO_DB = os.getenv("MONGO_DB", "listings")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "listings")

if MONGO_USER and MONGO_PASSWORD:
    MONGODB_URI = f"mongodb://{MONGO_USER}:{MONGO_PASSWORD}@{MONGO_HOST}:{MONGO_PORT}/?authSource=admin"
else:
    MONGODB_URI = f"mongodb://{MONGO_HOST}:{MONGO_PORT}/"

def clean_price(price_value):
    """Extrait un nombre flottant propre depuis '8000 DH'."""
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

def clean_int(value):
    """Extrait un entier propre (ex: '3 ch' -> 3)."""
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if not value:
        return 0
    
    str_val = str(value)
    match = re.search(r"(\d+)", str_val)
    if match:
        try:
            return int(match.group(1))
        except:
            return 0
    return 0


def detect_transaction_type(text: str) -> str:
    """Détecte si c'est une location ou un achat depuis le texte."""
    text_lower = text.lower() if text else ""
    
    # Mots clés pour location
    rent_keywords = ["louer", "location", "à louer", "loue", "mensuel", "/mois", "dh/mois", "mad/mois"]
    # Mots clés pour achat
    buy_keywords = ["acheter", "achat", "vente", "à vendre", "vends"]
    
    for kw in rent_keywords:
        if kw in text_lower:
            return "location"
    for kw in buy_keywords:
        if kw in text_lower:
            return "vente"
    
    return None  # Non déterminé


@tool
def search_properties(
    property_type: str = None,
    transaction_type: str = None,
    min_price: float = None,
    max_price: float = None,
    location: str = None,
    min_surface: float = None,
    bedrooms: int = None,
    standing: str = None,
    limit: int = 5
) -> str:
    """
    Recherche des biens immobiliers dans la base de données.
    
    Args:
        property_type: Type de bien (appartement, villa, bureau, terrain, maison, studio)
        transaction_type: 'location' pour louer, 'vente' pour acheter. Si non spécifié, cherche les deux.
        min_price: Prix minimum en MAD/DH
        max_price: Prix maximum en MAD/DH
        location: Ville ou quartier (Casablanca, Rabat, Marrakech, Salé, Tanger...)
        min_surface: Surface minimum en m²
        bedrooms: Nombre minimum de chambres
        standing: Niveau de standing (luxe, haut standing, moyen, économique)
        limit: Nombre maximum de résultats (défaut: 5)
    
    Returns:
        JSON avec les biens trouvés incluant titre, prix, surface, chambres, images
    """
    client = None
    try:
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        db = client[MONGO_DB]
        collection = db[MONGO_COLLECTION]
        
        # 1. Construction de la requête MongoDB
        query = {}
        
        # Type de bien
        if property_type:
            query["$or"] = [
                {"property_type": {"$regex": property_type, "$options": "i"}},
                {"title": {"$regex": property_type, "$options": "i"}}
            ]
        
        # Transaction (location/vente)
        if transaction_type:
            if transaction_type.lower() in ["location", "louer", "rent"]:
                query["$or"] = query.get("$or", []) + [
                    {"title": {"$regex": "louer|location", "$options": "i"}},
                    {"url": {"$regex": "louer|location", "$options": "i"}}
                ]
            elif transaction_type.lower() in ["vente", "acheter", "achat", "buy"]:
                query["$or"] = query.get("$or", []) + [
                    {"title": {"$regex": "vendre|vente|acheter", "$options": "i"}},
                    {"url": {"$regex": "vendre|vente", "$options": "i"}}
                ]
        
        # Localisation
        if location:
            loc_query = {"$regex": location, "$options": "i"}
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
                    {"adresse": loc_query},
                    {"title": loc_query}
                ]
        
        # Standing/Luxe
        if standing:
            standing_patterns = {
                "luxe": "luxe|prestige|haut.standing|premium",
                "haut": "haut.standing|standing|moderne",
                "moyen": "standard|classique",
                "economique": "économique|pas.cher|bon.prix"
            }
            pattern = standing_patterns.get(standing.lower(), standing)
            # Ajouter au $or ou $and existant
            
        # Récupération (plus de résultats pour filtrer en Python)
        cursor = collection.find(query).limit(limit * 10)
        
        results = []
        for doc in cursor:
            # --- Filtrage Python Robuste ---
            
            # 1. PRIX
            raw_price = doc.get("price", doc.get("prix", 0))
            real_price = clean_price(raw_price)
            if min_price is not None and real_price < min_price: continue
            if max_price is not None and real_price > max_price: continue
                
            # 2. SURFACE
            raw_surface = doc.get("surface", 0)
            real_surface = clean_price(raw_surface)
            if min_surface is not None and real_surface < min_surface: continue

            # 3. CHAMBRES
            if bedrooms is not None:
                raw_rooms = doc.get("rooms", doc.get("chambres", 0))
                real_rooms = clean_int(raw_rooms)
                if real_rooms < bedrooms: 
                    continue

            # Préparation du résultat
            property_result = {
                "id": str(doc["_id"]),
                "titre": doc.get("title", "Bien immobilier"),
                "prix": f"{int(real_price):,} MAD".replace(",", " ") if real_price > 0 else "Prix sur demande",
                "prix_numeric": real_price,
                "surface": f"{int(real_surface)} m²" if real_surface > 0 else None,
                "chambres": clean_int(doc.get("rooms", doc.get("chambres", 0))),
                "adresse": doc.get("adresse", doc.get("location", "")),
                "url": doc.get("url", ""),
            }
            
            # Images (chercher dans différents champs possibles)
            images = doc.get("images", doc.get("image", doc.get("photos", [])))
            if isinstance(images, str):
                images = [images]
            if images and len(images) > 0:
                # Prendre les 3 premières images
                property_result["images"] = images[:3]
            
            # Type de transaction détecté
            detected_type = detect_transaction_type(doc.get("title", "") + " " + doc.get("url", ""))
            if detected_type:
                property_result["type_transaction"] = detected_type
            
            results.append(property_result)
            
            if len(results) >= limit:
                break
        
        if not results:
            suggestions = []
            if location:
                suggestions.append(f"Essaie d'élargir à d'autres quartiers de {location}")
            if max_price:
                suggestions.append(f"Augmente ton budget de 20-30%")
            suggestions.append("Enlève certains critères pour voir plus de biens")
            
            # Préparer les critères pour une alerte (sera utilisé par l'agent)
            alert_criteria = {}
            if property_type: alert_criteria["property_type"] = property_type
            if transaction_type: alert_criteria["transaction_type"] = transaction_type
            if location: alert_criteria["location"] = location
            if min_price: alert_criteria["min_price"] = min_price
            if max_price: alert_criteria["max_price"] = max_price
            if bedrooms: alert_criteria["bedrooms"] = bedrooms
            if standing: alert_criteria["standing"] = standing
            
            return json.dumps({
                "message": "Aucun bien trouvé avec ces critères 😕",
                "count": 0,
                "suggestions": suggestions,
                "can_create_alert": True,
                "alert_criteria": alert_criteria,
                "alert_message": "💡 Tu veux que je te prévienne dès qu'un bien correspondant arrive ? Réponds 'Oui' pour créer une alerte !"
            }, ensure_ascii=False, indent=2)
        
        return json.dumps({
            "message": f"🎉 {len(results)} bien(s) trouvé(s) !",
            "count": len(results),
            "results": results
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"error": str(e), "message": "Erreur lors de la recherche"})
    finally:
        if client: client.close()


@tool
def get_property_details(property_id: str) -> str:
    """
    Récupère tous les détails d'un bien immobilier par son ID.
    Utile pour avoir plus d'informations avant la négociation.
    
    Args:
        property_id: L'ID du bien (24 caractères hexadécimaux)
    
    Returns:
        Toutes les informations détaillées du bien
    """
    from bson import ObjectId
    client = None
    try:
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        collection = client[MONGO_DB][MONGO_COLLECTION]
        
        doc = collection.find_one({"_id": ObjectId(property_id)})
        
        if not doc:
            return json.dumps({"error": "Bien non trouvé", "message": f"Aucun bien avec l'ID {property_id}"})
        
        # Formater la réponse
        result = {
            "id": str(doc["_id"]),
            "titre": doc.get("title", ""),
            "prix": doc.get("price", ""),
            "surface": doc.get("surface", ""),
            "chambres": doc.get("rooms", doc.get("chambres", "")),
            "adresse": doc.get("adresse", doc.get("location", "")),
            "description": doc.get("description", ""),
            "url": doc.get("url", ""),
            "source": doc.get("source_site", ""),
        }
        
        # Images
        images = doc.get("images", doc.get("image", doc.get("photos", [])))
        if isinstance(images, str):
            images = [images]
        if images:
            result["images"] = images
            
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"error": str(e)})
    finally:
        if client: client.close()


@tool
def get_property_statistics(location: str = None) -> str:
    """
    Statistiques sur les biens disponibles dans une ville/région.
    
    Args:
        location: Ville ou quartier (optionnel)
    
    Returns:
        Nombre de biens, fourchettes de prix, types disponibles
    """
    client = None
    try:
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        collection = client[MONGO_DB][MONGO_COLLECTION]
        
        query = {}
        if location:
            query["$or"] = [
                {"location": {"$regex": location, "$options": "i"}},
                {"adresse": {"$regex": location, "$options": "i"}},
                {"title": {"$regex": location, "$options": "i"}}
            ]
        
        total = collection.count_documents(query)
        
        # Échantillon pour statistiques
        sample = list(collection.find(query).limit(100))
        
        prices = [clean_price(d.get("price", 0)) for d in sample if clean_price(d.get("price", 0)) > 0]
        
        stats = {
            "location": location or "Tout le Maroc",
            "total_biens": total,
            "prix_min": f"{int(min(prices)):,} MAD".replace(",", " ") if prices else "N/A",
            "prix_max": f"{int(max(prices)):,} MAD".replace(",", " ") if prices else "N/A",
            "prix_moyen": f"{int(sum(prices)/len(prices)):,} MAD".replace(",", " ") if prices else "N/A"
        }
        
        return json.dumps(stats, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"error": str(e)})
    finally:
        if client: client.close()
