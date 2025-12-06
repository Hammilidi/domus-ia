# web_api.py - Application FastAPI principale pour l'interface web
import os
from datetime import timedelta
from typing import Optional
from fastapi import FastAPI, Request, Form, Depends, HTTPException, status, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

# Imports locaux
from web.database import Database
from web.models import UserCreate, UserLogin, Token, SubscriptionPlan, UserRole
from web.services.auth_service import create_access_token, decode_access_token
from web.services.user_service import (
    create_user, authenticate_user, get_user_by_id, 
    update_phone_number, verify_phone, get_user_by_phone,
    create_admin_if_not_exists, get_all_users, update_user_role, count_users_by_role
)
from web.services.subscription_service import (
    get_user_active_subscription, has_active_subscription, 
    get_plan_price, PLAN_PRICES, start_free_trial, has_used_free_trial
)
from web.services.payment_service import (
    create_checkout_session, handle_successful_payment,
    verify_webhook_signature, get_stripe_publishable_key, get_payment_by_session
)

# Charger les variables d'environnement
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", ".env")
load_dotenv(dotenv_path)

# Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-super-secret-key-change-in-production")
WEB_BASE_URL = os.getenv("WEB_BASE_URL", "http://localhost:8080")

# Initialisation de l'application
app = FastAPI(title="DomusIA - Interface Web", version="1.0.0")

# Middleware de session
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# Configuration des templates et fichiers statiques
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


# ==================== ÉVÉNEMENTS DE DÉMARRAGE ====================

@app.on_event("startup")
async def startup_event():
    await Database.connect()
    # Créer l'admin par défaut s'il n'existe pas
    await create_admin_if_not_exists()
    print("🌐 Interface Web DomusIA démarrée")


@app.on_event("shutdown")
async def shutdown_event():
    await Database.disconnect()


# ==================== DÉPENDANCES ====================

async def get_current_user(request: Request):
    """Récupérer l'utilisateur actuel depuis la session"""
    token = request.session.get("access_token")
    if not token:
        return None
    
    payload = decode_access_token(token)
    if not payload:
        return None
    
    user_id = payload.get("user_id")
    if not user_id:
        return None
    
    user = await get_user_by_id(user_id)
    return user


async def require_auth(request: Request):
    """Exiger une authentification"""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"}
        )
    return user


# ==================== ROUTES PUBLIQUES ====================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Page d'accueil"""
    user = await get_current_user(request)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user,
        "plans": PLAN_PRICES
    })


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Page d'inscription"""
    user = await get_current_user(request)
    if user:
        return RedirectResponse(url="/dashboard", status_code=303)
    
    return templates.TemplateResponse("register.html", {
        "request": request,
        "error": None
    })


@app.post("/register")
async def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
    phone_number: Optional[str] = Form(None),
    role: str = Form("user")
):
    """Traitement de l'inscription avec rôle"""
    # Convertir le role string en enum
    user_role = UserRole.OWNER if role == "owner" else UserRole.USER
    
    user_data = UserCreate(
        email=email,
        password=password,
        full_name=full_name,
        phone_number=phone_number,
        role=user_role
    )
    
    user = await create_user(user_data)
    
    if not user:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Cet email est déjà utilisé."
        })
    
    # Connecter l'utilisateur automatiquement
    token = create_access_token({"user_id": str(user.id), "email": user.email})
    request.session["access_token"] = token
    
    # Rediriger selon le rôle
    if user_role == UserRole.OWNER:
        return RedirectResponse(url="/owner/dashboard", status_code=303)
    else:
        return RedirectResponse(url="/payment", status_code=303)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Page de connexion"""
    user = await get_current_user(request)
    if user:
        return RedirectResponse(url="/dashboard", status_code=303)
    
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": None
    })


@app.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...)
):
    """Traitement de la connexion avec redirection basée sur le rôle"""
    user = await authenticate_user(email, password)
    
    if not user:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Email ou mot de passe incorrect."
        })
    
    token = create_access_token({"user_id": str(user.id), "email": user.email})
    request.session["access_token"] = token
    
    # Redirection basée sur le rôle
    if user.role == UserRole.ADMIN:
        return RedirectResponse(url="/admin", status_code=303)
    elif user.role == UserRole.OWNER:
        return RedirectResponse(url="/owner/dashboard", status_code=303)
    else:
        return RedirectResponse(url="/dashboard", status_code=303)


@app.get("/logout")
async def logout(request: Request):
    """Déconnexion"""
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)


# ==================== ROUTES PROTÉGÉES ====================

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Tableau de bord utilisateur"""
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    subscription = await get_user_active_subscription(str(user.id))
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "subscription": subscription
    })


@app.get("/payment", response_class=HTMLResponse)
async def payment_page(request: Request):
    """Page de choix de paiement"""
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    # Vérifier si l'utilisateur a déjà un abonnement actif
    subscription = await get_user_active_subscription(str(user.id))
    if subscription:
        return RedirectResponse(url="/dashboard", status_code=303)
    
    # Vérifier si l'utilisateur a déjà utilisé l'essai gratuit
    used_trial = await has_used_free_trial(str(user.id))
    
    return templates.TemplateResponse("payment.html", {
        "request": request,
        "user": user,
        "plans": PLAN_PRICES,
        "stripe_key": get_stripe_publishable_key(),
        "used_trial": used_trial
    })


@app.post("/payment/create-session")
async def create_payment_session(
    request: Request,
    plan: str = Form(...)
):
    """Créer une session de paiement Stripe"""
    user = await get_current_user(request)
    if not user:
        return JSONResponse({"error": "Non authentifié"}, status_code=401)
    
    try:
        plan_enum = SubscriptionPlan(plan)
    except ValueError:
        return JSONResponse({"error": "Plan invalide"}, status_code=400)
    
    try:
        session_data = await create_checkout_session(
            user_id=str(user.id),
            user_email=user.email,
            plan=plan_enum
        )
        return JSONResponse(session_data)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/payment/success", response_class=HTMLResponse)
async def payment_success(request: Request, session_id: str):
    """Page de succès de paiement"""
    user = await get_current_user(request)
    
    # Traiter le paiement
    await handle_successful_payment(session_id)
    
    return templates.TemplateResponse("payment_success.html", {
        "request": request,
        "user": user
    })


@app.get("/payment/cancel", response_class=HTMLResponse)
async def payment_cancel(request: Request):
    """Page d'annulation de paiement"""
    return templates.TemplateResponse("payment_cancel.html", {
        "request": request
    })


@app.post("/payment/webhook")
async def stripe_webhook(request: Request):
    """Webhook Stripe pour les notifications de paiement"""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    if not sig_header:
        return Response(status_code=400)
    
    event = await verify_webhook_signature(payload, sig_header)
    if not event:
        return Response(status_code=400)
    
    # Traiter l'événement
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        await handle_successful_payment(session["id"])
    
    return Response(status_code=200)


@app.post("/start-trial")
async def start_trial_route(request: Request):
    """Démarrer une période d'essai gratuite de 30 jours"""
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    # Démarrer l'essai gratuit
    subscription = await start_free_trial(str(user.id))
    
    if subscription:
        # Essai démarré avec succès, rediriger vers dashboard
        return RedirectResponse(url="/dashboard?trial=started", status_code=303)
    else:
        # L'utilisateur a déjà utilisé son essai
        return RedirectResponse(url="/payment?error=trial_used", status_code=303)


# ==================== LIAISON WHATSAPP ====================

@app.get("/link-whatsapp", response_class=HTMLResponse)
async def link_whatsapp_page(request: Request):
    """Page de liaison du numéro WhatsApp"""
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    return templates.TemplateResponse("link_whatsapp.html", {
        "request": request,
        "user": user,
        "error": None,
        "success": None,
        "code_sent": False
    })


@app.post("/link-whatsapp")
async def link_whatsapp_submit(
    request: Request,
    phone_number: str = Form(...)
):
    """Soumettre le numéro WhatsApp pour liaison"""
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    # Normaliser le numéro
    phone = phone_number.strip().replace(" ", "")
    if not phone.startswith("+"):
        phone = f"+{phone}"
    
    # Mettre à jour le numéro et générer le code
    success, code = await update_phone_number(str(user.id), phone)
    
    if not success:
        return templates.TemplateResponse("link_whatsapp.html", {
            "request": request,
            "user": user,
            "error": "Erreur lors de la mise à jour du numéro.",
            "success": None,
            "code_sent": False
        })
    
    # TODO: Envoyer le code via WhatsApp avec Twilio
    # Pour le développement, on affiche le code
    print(f"📱 Code de vérification pour {phone}: {code}")
    
    return templates.TemplateResponse("link_whatsapp.html", {
        "request": request,
        "user": await get_user_by_id(str(user.id)),  # Refresh user
        "error": None,
        "success": f"Code envoyé à {phone}. Vérifiez votre WhatsApp.",
        "code_sent": True,
        "debug_code": code  # À retirer en production
    })


@app.post("/verify-phone")
async def verify_phone_submit(
    request: Request,
    code: str = Form(...)
):
    """Vérifier le code OTP"""
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    success = await verify_phone(str(user.id), code)
    
    if success:
        return templates.TemplateResponse("link_whatsapp.html", {
            "request": request,
            "user": await get_user_by_id(str(user.id)),
            "error": None,
            "success": "✅ Numéro WhatsApp vérifié avec succès! Vous pouvez maintenant utiliser l'assistant IA.",
            "code_sent": False
        })
    else:
        return templates.TemplateResponse("link_whatsapp.html", {
            "request": request,
            "user": user,
            "error": "Code invalide ou expiré.",
            "success": None,
            "code_sent": True
        })


# ==================== API POUR WHATSAPP ====================

@app.get("/api/check-subscription/{phone_number}")
async def check_subscription_api(phone_number: str):
    """API pour vérifier l'abonnement d'un numéro WhatsApp"""
    user = await get_user_by_phone(phone_number)
    
    if not user:
        return JSONResponse({
            "has_access": False,
            "reason": "user_not_found"
        })
    
    if not user.phone_verified:
        return JSONResponse({
            "has_access": False,
            "reason": "phone_not_verified"
        })
    
    has_sub = await has_active_subscription(str(user.id))
    
    return JSONResponse({
        "has_access": has_sub,
        "reason": "active" if has_sub else "no_subscription",
        "user_name": user.full_name if has_sub else None
    })


# ==================== SOUMISSION DE BIENS ====================

@app.get("/submit-property", response_class=HTMLResponse)
async def submit_property_page(request: Request):
    """Page de soumission d'un bien immobilier"""
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    return templates.TemplateResponse("submit_property.html", {
        "request": request,
        "user": user,
        "success": None,
        "error": None
    })


@app.post("/submit-property")
async def submit_property_submit(
    request: Request,
    title: str = Form(...),
    property_type: str = Form(...),
    transaction_type: str = Form(...),
    price: str = Form(...),
    city: str = Form(...),
    adresse: Optional[str] = Form(None),
    surface: Optional[str] = Form(None),
    rooms: Optional[str] = Form(None),
    etage: Optional[str] = Form(None),
    age_bien: Optional[str] = Form(None),
    ascenseur: Optional[str] = Form(None),
    piscine: Optional[str] = Form(None),
    balcon: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    caracteristiques_supp: Optional[str] = Form(None),
    contact: Optional[str] = Form(None),
    url: Optional[str] = Form(None)
):
    """Traitement de la soumission d'un bien avec upload d'images"""
    from datetime import datetime
    from pymongo import MongoClient
    from fastapi import UploadFile, File
    import uuid
    import shutil
    
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    # Configuration MongoDB
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
    
    try:
        # Traiter les fichiers uploadés
        form = await request.form()
        images_list = []
        
        # Créer le dossier uploads si nécessaire
        upload_dir = os.path.join(BASE_DIR, "static", "uploads", "properties")
        os.makedirs(upload_dir, exist_ok=True)
        
        # Récupérer tous les fichiers images
        for key, value in form.multi_items():
            if key == "images" and hasattr(value, 'filename') and value.filename:
                # Générer un nom unique
                file_ext = os.path.splitext(value.filename)[1].lower()
                if file_ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
                    unique_name = f"{uuid.uuid4().hex}{file_ext}"
                    file_path = os.path.join(upload_dir, unique_name)
                    
                    # Sauvegarder le fichier
                    with open(file_path, "wb") as buffer:
                        content = await value.read()
                        buffer.write(content)
                    
                    # URL relative pour accès web
                    image_url = f"/static/uploads/properties/{unique_name}"
                    images_list.append(image_url)
        
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        db = client[MONGO_DB]
        collection = db[MONGO_COLLECTION]
        
        # Préparer le document
        location = f"{city}, {adresse}" if adresse else city
        
        property_doc = {
            "title": title,
            "property_type": property_type,
            "transaction_type": transaction_type,
            "price": price,
            "location": location,
            "adresse": adresse or "",
            "surface": surface,
            "rooms": rooms,
            "etage": etage,
            "age_bien": age_bien,
            "ascenseur": ascenseur or "False",
            "piscine": piscine or "False",
            "balcon": balcon or "False",
            "description": description,
            "caracteristiques_supp": caracteristiques_supp,
            "contact": contact,
            "url": url or "",
            "images": images_list[0] if len(images_list) == 1 else images_list if images_list else None,
            "source_site": "DomusIA - Contribution utilisateur",
            "date_publication": datetime.now().strftime("%Y-%m-%d"),
            "scraped_at": datetime.utcnow(),
            "submitted_by": str(user.id),
            "submitted_by_email": user.email
        }
        
        # Insérer dans MongoDB
        result = collection.insert_one(property_doc)
        
        client.close()
        
        return templates.TemplateResponse("submit_property.html", {
            "request": request,
            "user": user,
            "success": True,
            "error": None
        })
        
    except Exception as e:
        return templates.TemplateResponse("submit_property.html", {
            "request": request,
            "user": user,
            "success": None,
            "error": f"Erreur lors de l'ajout : {str(e)}"
        })


# ==================== ROUTES ADMIN ====================

async def require_admin(request: Request):
    """Vérifier que l'utilisateur est admin"""
    user = await get_current_user(request)
    if not user or user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    return user


@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    """Tableau de bord admin"""
    user = await get_current_user(request)
    if not user or user.role != UserRole.ADMIN:
        return RedirectResponse(url="/login", status_code=303)
    
    from pymongo import MongoClient
    
    # Statistiques utilisateurs
    stats = await count_users_by_role()
    
    # Récupérer les derniers utilisateurs
    recent_users = await get_all_users(limit=10)
    
    # Compter les biens
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
    
    try:
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        properties_count = client[MONGO_DB][MONGO_COLLECTION].count_documents({})
        client.close()
    except:
        properties_count = 0
    
    # Compter les abonnements actifs
    from web.database import get_subscriptions_collection
    subs = get_subscriptions_collection()
    subscriptions_count = await subs.count_documents({"status": "active"})
    
    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request,
        "user": user,
        "stats": stats,
        "recent_users": recent_users,
        "properties_count": properties_count,
        "subscriptions_count": subscriptions_count
    })


@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users(request: Request):
    """Liste des utilisateurs admin"""
    user = await get_current_user(request)
    if not user or user.role != UserRole.ADMIN:
        return RedirectResponse(url="/login", status_code=303)
    
    users = await get_all_users(limit=100)
    
    return templates.TemplateResponse("admin/users.html", {
        "request": request,
        "user": user,
        "users": users,
        "success": request.query_params.get("success")
    })


@app.post("/admin/users/{user_id}/role")
async def admin_change_user_role(request: Request, user_id: str, role: str = Form(...)):
    """Changer le rôle d'un utilisateur"""
    user = await get_current_user(request)
    if not user or user.role != UserRole.ADMIN:
        return RedirectResponse(url="/login", status_code=303)
    
    new_role = UserRole(role)
    await update_user_role(user_id, new_role)
    
    return RedirectResponse(url="/admin/users?success=Rôle mis à jour", status_code=303)


# ==================== ROUTES OWNER ====================

@app.get("/owner/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request):
    """Tableau de bord propriétaire"""
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    # Récupérer les biens de ce propriétaire
    from pymongo import MongoClient
    
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
    
    try:
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        properties = list(client[MONGO_DB][MONGO_COLLECTION].find({"submitted_by": str(user.id)}))
        client.close()
    except:
        properties = []
    
    return templates.TemplateResponse("owner_dashboard.html", {
        "request": request,
        "user": user,
        "properties": properties
    })


@app.post("/owner/property/{property_id}/delete")
async def owner_delete_property(request: Request, property_id: str):
    """Supprimer un bien"""
    from bson import ObjectId
    from pymongo import MongoClient
    
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
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
    
    try:
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        # Supprimer seulement si c'est le propriétaire OU si c'est un admin
        query = {"_id": ObjectId(property_id)}
        if user.role != UserRole.ADMIN:
            query["submitted_by"] = str(user.id)
        
        client[MONGO_DB][MONGO_COLLECTION].delete_one(query)
        client.close()
    except:
        pass
    
    return RedirectResponse(url="/owner/dashboard", status_code=303)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

