# payment_service.py - Service de paiement avec Stripe
import os
import stripe
import logging
from datetime import datetime
from typing import Optional
from bson import ObjectId
from dotenv import load_dotenv

from web.database import get_payments_collection
from web.models import PaymentInDB, PaymentStatus, SubscriptionPlan
from web.services.subscription_service import (
    create_subscription, activate_subscription, get_plan_price, PLAN_PRICES
)

# Configuration du logger
logger = logging.getLogger(__name__)

# Charger les variables d'environnement
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "..", ".env")
load_dotenv(dotenv_path)

# Configuration Stripe
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
WEB_BASE_URL = os.getenv("WEB_BASE_URL", "http://localhost:8080")

# Currency: Stripe ne supporte pas MAD directement, on utilise EUR
# Les prix seront convertis (approximativement 1 EUR = 11 MAD)
STRIPE_CURRENCY = "eur"

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY
    logger.info("✅ Stripe API configurée")
else:
    logger.warning("⚠️ STRIPE_SECRET_KEY non configurée")


async def create_checkout_session(user_id: str, user_email: str, plan: SubscriptionPlan) -> Optional[dict]:
    """Créer une session Stripe Checkout"""
    if not STRIPE_SECRET_KEY:
        raise ValueError("Stripe n'est pas configuré. Ajoutez STRIPE_SECRET_KEY dans .env")
    
    # Créer l'abonnement en attente
    subscription = await create_subscription(user_id, plan)
    
    # Créer le paiement en attente
    payments = get_payments_collection()
    price_mad = get_plan_price(plan)
    
    # Conversion approximative MAD -> EUR (1 EUR ≈ 11 MAD)
    price_eur = round(price_mad / 11, 2)
    
    payment_dict = {
        "user_id": user_id,
        "subscription_id": str(subscription.id),
        "amount": price_mad,  # Garder le prix en MAD pour référence
        "currency": "MAD",
        "status": PaymentStatus.PENDING.value,
        "stripe_payment_id": None,
        "stripe_session_id": None,
        "created_at": datetime.utcnow(),
        "completed_at": None
    }
    
    payment_result = await payments.insert_one(payment_dict)
    payment_id = str(payment_result.inserted_id)
    
    # Créer la session Stripe
    try:
        # Convertir en centimes pour Stripe
        amount_cents = int(price_eur * 100)
        
        logger.info(f"📦 Création session Stripe: {plan.value}, {price_eur} EUR ({price_mad} MAD)")
        
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": STRIPE_CURRENCY,
                    "product_data": {
                        "name": f"Abonnement {plan.value.capitalize()} - DomusIA",
                        "description": f"Assistant immobilier IA via WhatsApp ({price_mad} MAD)"
                    },
                    "unit_amount": amount_cents,
                },
                "quantity": 1,
            }],
            mode="payment",
            customer_email=user_email,
            success_url=f"{WEB_BASE_URL}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{WEB_BASE_URL}/payment/cancel",
            metadata={
                "user_id": user_id,
                "subscription_id": str(subscription.id),
                "payment_id": payment_id,
                "plan": plan.value
            }
        )
        
        logger.info(f"✅ Session Stripe créée: {session.id}")
        
        # Mettre à jour le paiement avec l'ID de session
        await payments.update_one(
            {"_id": ObjectId(payment_id)},
            {"$set": {"stripe_session_id": session.id}}
        )
        
        return {
            "session_id": session.id,
            "checkout_url": session.url,
            "subscription_id": str(subscription.id),
            "payment_id": payment_id
        }
        
    except stripe.error.StripeError as e:
        logger.error(f"❌ Erreur Stripe: {e}")
        # En cas d'erreur, marquer le paiement comme échoué
        await payments.update_one(
            {"_id": ObjectId(payment_id)},
            {"$set": {"status": PaymentStatus.FAILED.value}}
        )
        raise e


async def handle_successful_payment(session_id: str) -> bool:
    """Traiter un paiement réussi (appelé par le webhook Stripe)"""
    payments = get_payments_collection()
    
    # Récupérer les détails de la session Stripe
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except:
        return False
    
    if session.payment_status != "paid":
        return False
    
    # Récupérer le paiement local
    payment = await payments.find_one({"stripe_session_id": session_id})
    if not payment:
        return False
    
    # Activer l'abonnement
    subscription_id = payment.get("subscription_id")
    if subscription_id:
        await activate_subscription(subscription_id, session.get("subscription"))
    
    # Marquer le paiement comme complété
    await payments.update_one(
        {"_id": payment["_id"]},
        {
            "$set": {
                "status": PaymentStatus.COMPLETED.value,
                "stripe_payment_id": session.payment_intent,
                "completed_at": datetime.utcnow()
            }
        }
    )
    
    return True


async def verify_webhook_signature(payload: bytes, sig_header: str) -> Optional[dict]:
    """Vérifier la signature du webhook Stripe"""
    if not STRIPE_WEBHOOK_SECRET:
        return None
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
        return event
    except ValueError:
        return None
    except stripe.error.SignatureVerificationError:
        return None


async def get_payment_by_session(session_id: str) -> Optional[PaymentInDB]:
    """Récupérer un paiement par son ID de session Stripe"""
    payments = get_payments_collection()
    
    payment = await payments.find_one({"stripe_session_id": session_id})
    if payment:
        return PaymentInDB(**payment)
    
    return None


def get_stripe_publishable_key() -> Optional[str]:
    """Retourner la clé publique Stripe"""
    return STRIPE_PUBLISHABLE_KEY
