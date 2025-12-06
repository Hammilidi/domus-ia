# user_service.py - Service de gestion des utilisateurs
from datetime import datetime, timedelta
from typing import Optional, List
from bson import ObjectId
import os
import logging

from web.database import get_users_collection
from web.models import UserCreate, UserInDB, UserResponse, UserRole
from web.services.auth_service import get_password_hash, verify_password, generate_verification_code

logger = logging.getLogger(__name__)


async def create_user(user_data: UserCreate) -> Optional[UserInDB]:
    """Créer un nouvel utilisateur"""
    users = get_users_collection()
    
    # Vérifier si l'email existe déjà
    existing = await users.find_one({"email": user_data.email})
    if existing:
        return None
    
    # Créer l'utilisateur
    user_dict = {
        "email": user_data.email,
        "full_name": user_data.full_name,
        "password_hash": get_password_hash(user_data.password),
        "phone_number": user_data.phone_number,
        "role": user_data.role.value if hasattr(user_data, 'role') else UserRole.USER.value,
        "phone_verified": False,
        "phone_verification_code": None,
        "phone_verification_expires": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "is_active": True
    }
    
    result = await users.insert_one(user_dict)
    user_dict["_id"] = result.inserted_id
    
    return UserInDB(**user_dict)


async def create_admin_if_not_exists() -> Optional[UserInDB]:
    """Créer un admin par défaut si aucun n'existe"""
    users = get_users_collection()
    
    # Vérifier s'il y a déjà un admin
    existing_admin = await users.find_one({"role": UserRole.ADMIN.value})
    if existing_admin:
        logger.info("✅ Admin existant trouvé")
        return UserInDB(**existing_admin)
    
    # Récupérer les credentials depuis .env
    admin_email = os.getenv("ADMIN_EMAIL", "admin@domusia.com")
    admin_password = os.getenv("ADMIN_PASSWORD", "AdminDomusIA2024!")
    admin_name = os.getenv("ADMIN_NAME", "Admin DomusIA")
    
    # Créer l'admin
    admin_dict = {
        "email": admin_email,
        "full_name": admin_name,
        "password_hash": get_password_hash(admin_password),
        "phone_number": None,
        "role": UserRole.ADMIN.value,
        "phone_verified": True,  # Admin n'a pas besoin de vérifier
        "phone_verification_code": None,
        "phone_verification_expires": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "is_active": True
    }
    
    result = await users.insert_one(admin_dict)
    admin_dict["_id"] = result.inserted_id
    
    logger.info(f"🔐 Admin créé: {admin_email}")
    return UserInDB(**admin_dict)


async def get_user_by_email(email: str) -> Optional[UserInDB]:
    """Récupérer un utilisateur par son email"""
    users = get_users_collection()
    user = await users.find_one({"email": email})
    
    if user:
        # Ajouter le rôle par défaut si absent (utilisateurs legacy)
        if "role" not in user:
            user["role"] = UserRole.USER.value
        return UserInDB(**user)
    return None


async def get_user_by_id(user_id: str) -> Optional[UserInDB]:
    """Récupérer un utilisateur par son ID"""
    users = get_users_collection()
    
    try:
        user = await users.find_one({"_id": ObjectId(user_id)})
        if user:
            # Ajouter le rôle par défaut si absent (utilisateurs legacy)
            if "role" not in user:
                user["role"] = UserRole.USER.value
            return UserInDB(**user)
    except:
        pass
    
    return None


async def get_user_by_phone(phone_number: str) -> Optional[UserInDB]:
    """Récupérer un utilisateur par son numéro de téléphone"""
    users = get_users_collection()
    
    # Normaliser le numéro (retirer le + si présent)
    normalized = phone_number.lstrip("+")
    
    # Chercher avec différents formats
    user = await users.find_one({
        "$or": [
            {"phone_number": phone_number},
            {"phone_number": f"+{normalized}"},
            {"phone_number": normalized}
        ]
    })
    
    if user:
        # Ajouter le rôle par défaut si absent (utilisateurs legacy)
        if "role" not in user:
            user["role"] = UserRole.USER.value
        return UserInDB(**user)
    return None


async def get_users_by_role(role: UserRole) -> List[UserInDB]:
    """Récupérer tous les utilisateurs d'un rôle donné"""
    users = get_users_collection()
    cursor = users.find({"role": role.value})
    
    result = []
    async for user in cursor:
        result.append(UserInDB(**user))
    return result


async def get_all_users(limit: int = 100, skip: int = 0) -> List[UserInDB]:
    """Récupérer tous les utilisateurs (pour admin)"""
    users = get_users_collection()
    cursor = users.find().skip(skip).limit(limit).sort("created_at", -1)
    
    result = []
    async for user in cursor:
        result.append(UserInDB(**user))
    return result


async def update_user_role(user_id: str, new_role: UserRole) -> bool:
    """Changer le rôle d'un utilisateur"""
    users = get_users_collection()
    
    result = await users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"role": new_role.value, "updated_at": datetime.utcnow()}}
    )
    
    return result.modified_count > 0


async def authenticate_user(email: str, password: str) -> Optional[UserInDB]:
    """Authentifier un utilisateur"""
    user = await get_user_by_email(email)
    
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    
    return user


async def update_phone_number(user_id: str, phone_number: str) -> bool:
    """Mettre à jour le numéro de téléphone d'un utilisateur"""
    users = get_users_collection()
    
    # Générer un code de vérification
    code = generate_verification_code()
    expires = datetime.utcnow() + timedelta(minutes=10)
    
    result = await users.update_one(
        {"_id": ObjectId(user_id)},
        {
            "$set": {
                "phone_number": phone_number,
                "phone_verified": False,
                "phone_verification_code": code,
                "phone_verification_expires": expires,
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    return result.modified_count > 0, code


async def verify_phone(user_id: str, code: str) -> bool:
    """Vérifier le code OTP du téléphone"""
    users = get_users_collection()
    user = await get_user_by_id(user_id)
    
    if not user:
        return False
    
    # Vérifier le code et l'expiration
    if user.phone_verification_code != code:
        return False
    
    if user.phone_verification_expires and user.phone_verification_expires < datetime.utcnow():
        return False
    
    # Marquer comme vérifié
    result = await users.update_one(
        {"_id": ObjectId(user_id)},
        {
            "$set": {
                "phone_verified": True,
                "phone_verification_code": None,
                "phone_verification_expires": None,
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    return result.modified_count > 0


async def count_users_by_role() -> dict:
    """Compter les utilisateurs par rôle (pour admin dashboard)"""
    users = get_users_collection()
    
    total = await users.count_documents({})
    users_count = await users.count_documents({"role": UserRole.USER.value})
    owners_count = await users.count_documents({"role": UserRole.OWNER.value})
    admins_count = await users.count_documents({"role": UserRole.ADMIN.value})
    
    return {
        "total": total,
        "users": users_count,
        "owners": owners_count,
        "admins": admins_count
    }


def user_to_response(user: UserInDB) -> UserResponse:
    """Convertir UserInDB en UserResponse"""
    return UserResponse(
        id=str(user.id) if user.id else "",
        email=user.email,
        full_name=user.full_name,
        phone_number=user.phone_number,
        role=user.role,
        phone_verified=user.phone_verified,
        created_at=user.created_at,
        is_active=user.is_active
    )

