# subscription_service.py - Service de gestion des abonnements
from datetime import datetime, timedelta
from typing import Optional, List
from bson import ObjectId

from web.database import get_subscriptions_collection
from web.models import (
    SubscriptionCreate, SubscriptionInDB, SubscriptionResponse,
    SubscriptionStatus, SubscriptionPlan
)


# Durée des plans en jours
PLAN_DURATIONS = {
    SubscriptionPlan.MONTHLY: 30,
    SubscriptionPlan.YEARLY: 365,
    SubscriptionPlan.TRIAL: 30  # Période d'essai gratuite de 30 jours
}

# Prix des plans en MAD (Dirham Marocain)
PLAN_PRICES = {
    SubscriptionPlan.MONTHLY: 99.00,
    SubscriptionPlan.YEARLY: 999.00,
    SubscriptionPlan.TRIAL: 0.00
}


async def create_subscription(user_id: str, plan: SubscriptionPlan) -> SubscriptionInDB:
    """Créer un nouvel abonnement"""
    subscriptions = get_subscriptions_collection()
    
    subscription_dict = {
        "user_id": user_id,
        "plan": plan.value,
        "status": SubscriptionStatus.PENDING.value,
        "started_at": None,
        "expires_at": None,
        "stripe_subscription_id": None,
        "stripe_customer_id": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    result = await subscriptions.insert_one(subscription_dict)
    subscription_dict["_id"] = result.inserted_id
    
    return SubscriptionInDB(**subscription_dict)


async def activate_subscription(subscription_id: str, stripe_subscription_id: Optional[str] = None) -> bool:
    """Activer un abonnement après paiement"""
    subscriptions = get_subscriptions_collection()
    
    # Récupérer l'abonnement
    subscription = await subscriptions.find_one({"_id": ObjectId(subscription_id)})
    if not subscription:
        return False
    
    plan = SubscriptionPlan(subscription["plan"])
    duration_days = PLAN_DURATIONS.get(plan, 30)
    
    now = datetime.utcnow()
    expires_at = now + timedelta(days=duration_days)
    
    update_data = {
        "status": SubscriptionStatus.ACTIVE.value,
        "started_at": now,
        "expires_at": expires_at,
        "updated_at": now
    }
    
    if stripe_subscription_id:
        update_data["stripe_subscription_id"] = stripe_subscription_id
    
    result = await subscriptions.update_one(
        {"_id": ObjectId(subscription_id)},
        {"$set": update_data}
    )
    
    return result.modified_count > 0


async def get_subscription_by_id(subscription_id: str) -> Optional[SubscriptionInDB]:
    """Récupérer un abonnement par ID"""
    subscriptions = get_subscriptions_collection()
    
    try:
        subscription = await subscriptions.find_one({"_id": ObjectId(subscription_id)})
        if subscription:
            return SubscriptionInDB(**subscription)
    except:
        pass
    
    return None


async def get_user_active_subscription(user_id: str) -> Optional[SubscriptionInDB]:
    """Récupérer l'abonnement actif d'un utilisateur"""
    subscriptions = get_subscriptions_collection()
    
    # Chercher un abonnement actif non expiré
    subscription = await subscriptions.find_one({
        "user_id": user_id,
        "status": SubscriptionStatus.ACTIVE.value,
        "expires_at": {"$gt": datetime.utcnow()}
    })
    
    if subscription:
        return SubscriptionInDB(**subscription)
    
    return None


async def has_active_subscription(user_id: str) -> bool:
    """Vérifier si un utilisateur a un abonnement actif"""
    subscription = await get_user_active_subscription(user_id)
    return subscription is not None


async def get_user_subscriptions(user_id: str) -> List[SubscriptionInDB]:
    """Récupérer tous les abonnements d'un utilisateur"""
    subscriptions = get_subscriptions_collection()
    
    cursor = subscriptions.find({"user_id": user_id}).sort("created_at", -1)
    result = []
    
    async for subscription in cursor:
        result.append(SubscriptionInDB(**subscription))
    
    return result


async def cancel_subscription(subscription_id: str) -> bool:
    """Annuler un abonnement"""
    subscriptions = get_subscriptions_collection()
    
    result = await subscriptions.update_one(
        {"_id": ObjectId(subscription_id)},
        {
            "$set": {
                "status": SubscriptionStatus.CANCELLED.value,
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    return result.modified_count > 0


async def check_and_expire_subscriptions():
    """Vérifier et expirer les abonnements dépassés (à exécuter périodiquement)"""
    subscriptions = get_subscriptions_collection()
    
    result = await subscriptions.update_many(
        {
            "status": SubscriptionStatus.ACTIVE.value,
            "expires_at": {"$lt": datetime.utcnow()}
        },
        {
            "$set": {
                "status": SubscriptionStatus.EXPIRED.value,
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    return result.modified_count


def get_plan_price(plan: SubscriptionPlan) -> float:
    """Retourner le prix d'un plan"""
    return PLAN_PRICES.get(plan, 0.0)


async def start_free_trial(user_id: str) -> Optional[SubscriptionInDB]:
    """
    Démarrer une période d'essai gratuite de 30 jours pour un utilisateur.
    Vérifie d'abord si l'utilisateur n'a pas déjà eu d'essai gratuit.
    """
    subscriptions = get_subscriptions_collection()
    
    # Vérifier si l'utilisateur a déjà eu un essai gratuit
    existing_trial = await subscriptions.find_one({
        "user_id": user_id,
        "plan": SubscriptionPlan.TRIAL.value
    })
    
    if existing_trial:
        # L'utilisateur a déjà eu un essai, on ne peut pas en créer un nouveau
        return None
    
    # Créer l'abonnement d'essai
    now = datetime.utcnow()
    expires_at = now + timedelta(days=PLAN_DURATIONS[SubscriptionPlan.TRIAL])
    
    subscription_dict = {
        "user_id": user_id,
        "plan": SubscriptionPlan.TRIAL.value,
        "status": SubscriptionStatus.ACTIVE.value,  # Actif immédiatement
        "started_at": now,
        "expires_at": expires_at,
        "stripe_subscription_id": None,
        "stripe_customer_id": None,
        "created_at": now,
        "updated_at": now
    }
    
    result = await subscriptions.insert_one(subscription_dict)
    subscription_dict["_id"] = result.inserted_id
    
    return SubscriptionInDB(**subscription_dict)


async def has_used_free_trial(user_id: str) -> bool:
    """Vérifier si un utilisateur a déjà utilisé son essai gratuit"""
    subscriptions = get_subscriptions_collection()
    
    existing_trial = await subscriptions.find_one({
        "user_id": user_id,
        "plan": SubscriptionPlan.TRIAL.value
    })
    
    return existing_trial is not None
