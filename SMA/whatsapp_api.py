# whatsapp_api.py
from fastapi import FastAPI, Form, Response
from pydantic import BaseModel
import logging
import os
import httpx
import base64
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

# NOUVEAUX IMPORTS TWILIO
from twilio.rest import Client 

# Import Google Generative AI pour l'analyse d'images
import google.generativeai as genai

# Import de votre graphe d'agents compilé et de l'état
from superviseur_fluent import build_fluent_graph
from state import AgentState
from langchain_core.messages import HumanMessage, AIMessage

# Charger les variables d'environnement (nécessaire pour Twilio et Gemini)
# load_dotenv()

# Chemin vers ton fichier .env
dotenv_path = r"C:\Users\hp\Fidelis\DomusIA\.env"

load_dotenv(dotenv_path)

# --- Configuration et Initialisation ---

app = FastAPI(title="DomusIA WhatsApp API", version="2.0.0")

# Configuration du logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Récupération des identifiants Twilio
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER") # Ex: +14155238886

# URL de l'interface web pour la vérification d'abonnement
WEB_API_URL = os.getenv("WEB_BASE_URL", "http://localhost:8080")

# Initialisation du client Twilio (hors des fonctions pour l'efficacité)
TWILIO_CLIENT: Optional[Client] = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_WHATSAPP_NUMBER:
    TWILIO_CLIENT = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    logger.info("✅ Client Twilio initialisé.")
else:
    logger.warning("⚠️ Identifiants Twilio manquants. L'envoi de messages sera simulé.")

# Configuration Gemini Vision pour l'analyse d'images
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
    VISION_MODEL = genai.GenerativeModel('gemini-2.0-flash')
    logger.info("✅ Gemini Vision configuré pour l'analyse d'images.")
else:
    VISION_MODEL = None
    logger.warning("⚠️ GOOGLE_API_KEY manquant. L'analyse d'images sera désactivée.")


# Initialisation du graphe (sera fait au démarrage de l'app)
try:
    SMA_APP = build_fluent_graph()
    logger.info("✅ Graphe d'agents (SMA) compilé.")
except Exception as e:
    logger.error(f"❌ Erreur critique lors de la compilation du SMA: {e}")
    SMA_APP = None

# Dictionnaire pour stocker l'historique de conversation par utilisateur (Numéro de téléphone)
# UTILISER REDIS EN PRODUCTION pour la persistance
CHAT_HISTORY_STORE: Dict[str, Dict[str, Any]] = {}

# Modèle pour l'état initial
INITIAL_STATE: AgentState = {
    "messages": [],
    "active_property_id": None,
    "next_agent": None,
    "delegation_query": None,
    "last_search_results": None
}

# Message pour les utilisateurs non abonnés
SUBSCRIPTION_REQUIRED_MESSAGE = """🏠 *Bienvenue sur DomusIA !*

Je suis votre assistant immobilier intelligent, mais il semble que vous n'ayez pas encore de compte actif.

✨ Pour profiter de mes services :
1️⃣ Inscrivez-vous sur notre site web
2️⃣ Souscrivez à un abonnement
3️⃣ Liez votre numéro WhatsApp

🔗 *Inscrivez-vous ici :* {web_url}/register

Une fois votre compte activé, vous pourrez :
🔍 Rechercher des biens immobiliers
💬 Négocier les prix avec mon aide
⚖️ Obtenir des conseils juridiques

À très bientôt ! 🏡"""

PHONE_NOT_VERIFIED_MESSAGE = """📱 *Numéro non vérifié*

Votre numéro WhatsApp n'est pas encore lié à votre compte DomusIA.

Pour utiliser l'assistant, veuillez :
1️⃣ Connectez-vous sur {web_url}/login
2️⃣ Allez dans "Lier WhatsApp"
3️⃣ Entrez ce numéro et le code de vérification

🔗 *Lien : * {web_url}/link-whatsapp"""


# --- Fonction de vérification d'abonnement ---
async def check_user_subscription(phone_number: str) -> dict:
    """
    Vérifie si un utilisateur a un abonnement actif en appelant l'API web.
    Retourne: {"has_access": bool, "reason": str, "user_name": str|None}
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{WEB_API_URL}/api/check-subscription/{phone_number}",
                timeout=5.0
            )
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        logger.error(f"❌ Erreur lors de la vérification d'abonnement: {e}")
    
    # En cas d'erreur, on refuse l'accès par défaut
    return {"has_access": False, "reason": "service_unavailable"}


# --- Fonction d'envoi de réponse WhatsApp (Mise à jour) ---
def send_whatsapp_response(to_number: str, message: str) -> None:
    """
    Envoie la réponse de l'IA à l'utilisateur via l'API WhatsApp de Twilio.
    Gère les messages longs en les découpant (limite Twilio: 1600 caractères).
    """
    MAX_LENGTH = 1500  # Garde une marge de sécurité
    
    if not TWILIO_CLIENT or not TWILIO_WHATSAPP_NUMBER:
        # Fallback si Twilio n'est pas configuré (mode simulation)
        logger.info(f"🤖 SIMULATION ENVOI WHATSAPP à {to_number}: {message[:100]}...")
        return
    
    from_whatsapp = f'whatsapp:{TWILIO_WHATSAPP_NUMBER}'
    to_whatsapp = f'whatsapp:{to_number}'
    
    # Découper le message si trop long
    if len(message) <= MAX_LENGTH:
        messages_to_send = [message]
    else:
        # Découper intelligemment (sur les sauts de ligne ou ----)
        messages_to_send = []
        current_chunk = ""
        
        # Essayer de couper sur les séparateurs naturels
        parts = message.replace("---", "\n---\n").split("\n")
        
        for part in parts:
            if len(current_chunk) + len(part) + 1 <= MAX_LENGTH:
                current_chunk += part + "\n"
            else:
                if current_chunk.strip():
                    messages_to_send.append(current_chunk.strip())
                current_chunk = part + "\n"
        
        if current_chunk.strip():
            messages_to_send.append(current_chunk.strip())
        
        # Si toujours un seul message trop long, couper brutalement
        final_messages = []
        for msg in messages_to_send:
            while len(msg) > MAX_LENGTH:
                final_messages.append(msg[:MAX_LENGTH])
                msg = msg[MAX_LENGTH:]
            if msg:
                final_messages.append(msg)
        messages_to_send = final_messages
    
    # Envoyer chaque partie
    for i, msg_part in enumerate(messages_to_send):
        try:
            # Ajouter indicateur de partie si plusieurs messages
            if len(messages_to_send) > 1:
                msg_part = f"({i+1}/{len(messages_to_send)})\n{msg_part}"
            
            TWILIO_CLIENT.messages.create(
                body=msg_part,
                from_=from_whatsapp,
                to=to_whatsapp
            )
            logger.info(f"✅ ENVOI WHATSAPP réussi à {to_number} (partie {i+1}/{len(messages_to_send)})")
        except Exception as e:
            logger.error(f"❌ Erreur lors de l'envoi Twilio à {to_number}: {e}")

        # En cas d'erreur (ex: numéro invalide, pas dans la fenêtre de 24h)
        

def extract_text_from_content(content) -> str:
    """
    Extrait le texte propre depuis les différents formats de réponse LLM.
    Gère: str, list de dict avec 'text', dict avec 'text', etc.
    """
    if content is None:
        return ""
    
    # Si c'est déjà une string propre
    if isinstance(content, str):
        # Vérifier si c'est un string qui ressemble à une repr de list/dict
        if content.startswith("[{") or content.startswith("{'"):
            try:
                import ast
                parsed = ast.literal_eval(content)
                return extract_text_from_content(parsed)
            except:
                pass
        return content
    
    # Si c'est une liste (format Gemini: [{'type': 'text', 'text': '...'}])
    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict):
                # Format: {'type': 'text', 'text': 'message'}
                if 'text' in item:
                    texts.append(item['text'])
                elif 'content' in item:
                    texts.append(str(item['content']))
            elif isinstance(item, str):
                texts.append(item)
        return "\n".join(texts) if texts else ""
    
    # Si c'est un dict avec une clé 'text'
    if isinstance(content, dict):
        if 'text' in content:
            return str(content['text'])
        if 'content' in content:
            return str(content['content'])
        # Sinon retourner la représentation string
        return ""
    
    # Fallback
    return str(content)

# ==================== 2. ENDPOINT WHATSAPP (Webhook) ====================

# Fonction d'analyse d'image avec Gemini Vision
async def analyze_property_image(image_url: str) -> str:
    """
    Analyse une image de bien immobilier avec Gemini Vision.
    Retourne une description du bien et des suggestions de recherche.
    """
    if not VISION_MODEL:
        return "Je ne peux pas analyser les images pour le moment."
    
    try:
        # Télécharger l'image depuis Twilio (avec authentification)
        async with httpx.AsyncClient() as client:
            response = await client.get(
                image_url,
                auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
                timeout=30.0
            )
            
            if response.status_code != 200:
                logger.error(f"Erreur téléchargement image: {response.status_code}")
                return "Je n'ai pas pu télécharger l'image."
            
            image_data = response.content
            content_type = response.headers.get('content-type', 'image/jpeg')
        
        # Préparer l'image pour Gemini
        image_part = {
            "mime_type": content_type,
            "data": base64.b64encode(image_data).decode('utf-8')
        }
        
        # Prompt pour l'analyse immobilière
        analysis_prompt = """Tu es un expert immobilier. Analyse cette image de bien immobilier.

Décris en FRANÇAIS et de manière CONCISE (max 200 mots) :

1. **Type de bien** : (appartement, villa, bureau, terrain, etc.)
2. **Standing** : (luxe, haut standing, moyen, économique)
3. **Caractéristiques visibles** : (nombre de pièces estimé, piscine, jardin, terrasse, vue, etc.)
4. **Style architectural** : (moderne, traditionnel marocain, contemporain, etc.)
5. **État général** : (neuf, rénové, à rénover)

Termine par une phrase du type :
"Tu cherches un bien similaire ? Dis-moi la ville et ton budget !"

Si ce n'est PAS une image de bien immobilier, dis simplement :
"Cette image ne semble pas être un bien immobilier. Envoie-moi une photo d'appartement, villa ou local que tu aimes !"
"""
        
        # Appel à Gemini Vision
        response = VISION_MODEL.generate_content([analysis_prompt, image_part])
        
        return response.text
        
    except Exception as e:
        logger.error(f"Erreur analyse image: {e}")
        return "Désolé, je n'ai pas pu analyser cette image. Réessaie avec une autre photo !"


@app.post("/whatsapp")
async def whatsapp_webhook(
    # Twilio envoie le numéro du client dans 'From' au format whatsapp:+212...
    From: str = Form(..., alias="From"), 
    Body: str = Form(default="", alias="Body"),  # Contenu du message (peut être vide si image seule)
    NumMedia: int = Form(default=0, alias="NumMedia"),  # Nombre de médias
    MediaUrl0: Optional[str] = Form(default=None, alias="MediaUrl0"),  # URL du 1er média
    MediaContentType0: Optional[str] = Form(default=None, alias="MediaContentType0")  # Type MIME
):
    """
    Webhook pour la réception des messages entrants de WhatsApp (via Twilio).
    Vérifie l'abonnement avant de traiter les messages.
    """
    if not SMA_APP:
         return Response(content="SMA non initialisé.", status_code=500)
         
    # Le numéro de l'utilisateur est le numéro complet de 'From' (ex: whatsapp:+212...)
    # On retire le préfixe 'whatsapp:' pour l'utiliser comme clé
    user_phone = From.replace("whatsapp:", "") 
    user_input = Body
    
    logger.info(f"🟢 Message reçu de {user_phone}: {user_input}")
    
    # ==================== VÉRIFICATION D'ABONNEMENT ====================
    subscription_check = await check_user_subscription(user_phone)
    
    if not subscription_check.get("has_access", False):
        reason = subscription_check.get("reason", "unknown")
        logger.info(f"🚫 Accès refusé pour {user_phone}: {reason}")
        
        if reason == "user_not_found":
            # L'utilisateur n'a pas de compte
            message = SUBSCRIPTION_REQUIRED_MESSAGE.format(web_url=WEB_API_URL)
        elif reason == "phone_not_verified":
            # Le numéro n'est pas vérifié
            message = PHONE_NOT_VERIFIED_MESSAGE.format(web_url=WEB_API_URL)
        elif reason == "no_subscription":
            # Compte existe mais pas d'abonnement actif
            message = f"""⚠️ *Abonnement expiré ou inactif*
            
Votre abonnement DomusIA n'est plus actif.

Renouvelez votre abonnement pour continuer à utiliser l'assistant immobilier IA.

🔗 *Renouveler :* {WEB_API_URL}/payment"""
        else:
            # Service indisponible ou autre erreur
            message = "⚠️ Service temporairement indisponible. Veuillez réessayer plus tard."
        
        send_whatsapp_response(user_phone, message)
        return Response(status_code=200)
    
    # ==================== TRAITEMENT NORMAL (UTILISATEUR AUTORISÉ) ====================
    user_name = subscription_check.get("user_name", "")
    logger.info(f"✅ Accès autorisé pour {user_phone} ({user_name})")
    
    # ==================== ANALYSE D'IMAGE SI PRÉSENTE ====================
    if NumMedia > 0 and MediaUrl0:
        logger.info(f"📷 Image reçue de {user_phone}: {MediaContentType0}")
        
        # Vérifier que c'est une image
        if MediaContentType0 and MediaContentType0.startswith('image/'):
            # Analyser l'image
            image_analysis = await analyze_property_image(MediaUrl0)
            
            # Combiner avec le texte du message si présent
            if user_input:
                user_input = f"{user_input}\n\n[L'utilisateur a envoyé une image de bien immobilier]\nAnalyse de l'image:\n{image_analysis}"
            else:
                user_input = f"[L'utilisateur a envoyé une image de bien immobilier]\nAnalyse de l'image:\n{image_analysis}"
            
            logger.info(f"👁 Analyse image: {image_analysis[:100]}...")
        else:
            # Média non supporté
            send_whatsapp_response(user_phone, "⚠️ Je ne peux analyser que les images. Envoie-moi une photo de bien immobilier !")
            return Response(status_code=200)
    
    # Si le message est vide et pas d'image
    if not user_input or not user_input.strip():
        send_whatsapp_response(user_phone, "Hey ! 👋 Tu voulais me dire quelque chose ? Envoie-moi un message ou une photo de bien !")
        return Response(status_code=200)
    
    # --- 1. Récupération de l'historique / État ---
    current_state = CHAT_HISTORY_STORE.get(user_phone, INITIAL_STATE.copy())
    
    # Ajouter le nouveau message de l'utilisateur à l'historique
    user_message = HumanMessage(content=user_input)
    current_state["messages"] = current_state["messages"] + [user_message]

    # --- 2. Exécution du Graphe d'Agents ---
    try:
        # Le graphe commence toujours au superviseur
        result = SMA_APP.invoke(current_state, config={"recursion_limit": 30})
        
        # Extraire la réponse finale - chercher le dernier message AI avec du contenu textuel
        ai_response = None
        
        # Parcourir les messages à l'envers pour trouver une vraie réponse
        for msg in reversed(result["messages"]):
            # Ignorer les messages ToolMessage (résultats d'outils)
            if msg.__class__.__name__ == 'ToolMessage':
                continue
            # Ignorer les messages Human
            if msg.__class__.__name__ == 'HumanMessage':
                continue
                
            # Vérifier si c'est un message AI avec du contenu textuel
            if hasattr(msg, 'content') and msg.content:
                content = msg.content
                
                # Ignorer si c'est juste un tool call sans contenu
                if hasattr(msg, 'tool_calls') and msg.tool_calls and not content:
                    continue
                
                # Extraire le texte proprement - gérer les formats de réponse Gemini
                extracted_text = extract_text_from_content(content)
                
                if extracted_text and len(extracted_text) > 5:
                    ai_response = extracted_text
                    break
        
        # Si toujours pas de réponse, essayer de formater le dernier message
        if not ai_response:
            last_msg = result["messages"][-1]
            if hasattr(last_msg, 'content') and last_msg.content:
                ai_response = extract_text_from_content(last_msg.content)
            if not ai_response:
                # Fallback : message d'erreur générique
                ai_response = "Hmm 🤔 Je n'ai pas pu traiter ta demande. Peux-tu reformuler ?"
        
        logger.info(f"📤 Réponse AI: {ai_response[:100]}...")
        
        # --- 3. Mise à jour de l'état et réponse ---
        
        # Sauvegarder le nouvel historique/état
        new_state = {
             k: result[k] for k in result if k in INITIAL_STATE
        }
        CHAT_HISTORY_STORE[user_phone] = new_state

        # Envoi de la réponse à WhatsApp
        send_whatsapp_response(user_phone, ai_response)
        
    except Exception as e:
        logger.error(f"❌ Erreur lors de l'exécution du SMA pour {user_phone}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        error_message = "Désolé, une erreur interne est survenue. Peux-tu réessayer ?"
        send_whatsapp_response(user_phone, error_message)

    # Twilio/Meta s'attend à une réponse HTTP 200/204 rapide
    return Response(status_code=200)


# ==================== ENDPOINT DE SANTÉ ====================

@app.get("/health")
async def health_check():
    """Vérification de l'état du service"""
    return {
        "status": "ok",
        "sma_ready": SMA_APP is not None,
        "twilio_configured": TWILIO_CLIENT is not None
    }


# --- Exécution ---
if __name__ == "__main__":
    import uvicorn
    
    if os.getenv("GOOGLE_API_KEY") is None:
        logger.error("🛑 ERREUR : GOOGLE_API_KEY n'est pas défini. Le SMA ne peut pas fonctionner.")

    print("\n--- 🌐 Serveur WhatsApp Agent Immobilier (FastAPI) ---")
    print("Point d'entrée du Webhook : /whatsapp")
    print(f"Vérification d'abonnement via : {WEB_API_URL}")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
