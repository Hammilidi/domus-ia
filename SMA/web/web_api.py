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
from web.models import UserCreate, UserLogin, Token, SubscriptionPlan
from web.services.auth_service import create_access_token, decode_access_token
from web.services.user_service import (
    create_user, authenticate_user, get_user_by_id, 
    update_phone_number, verify_phone, get_user_by_phone
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
    phone_number: Optional[str] = Form(None)
):
    """Traitement de l'inscription"""
    user_data = UserCreate(
        email=email,
        password=password,
        full_name=full_name,
        phone_number=phone_number
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
    
    # Rediriger vers la page de paiement
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
    """Traitement de la connexion"""
    user = await authenticate_user(email, password)
    
    if not user:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Email ou mot de passe incorrect."
        })
    
    token = create_access_token({"user_id": str(user.id), "email": user.email})
    request.session["access_token"] = token
    
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


# ==================== EXÉCUTION ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
