# user_service.py - Service de gestion des utilisateurs
from datetime import datetime, timedelta
from typing import Optional
from bson import ObjectId

from web.database import get_users_collection
from web.models import UserCreate, UserInDB, UserResponse
from web.services.auth_service import get_password_hash, verify_password, generate_verification_code


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


async def get_user_by_email(email: str) -> Optional[UserInDB]:
    """Récupérer un utilisateur par son email"""
    users = get_users_collection()
    user = await users.find_one({"email": email})
    
    if user:
        return UserInDB(**user)
    return None


async def get_user_by_id(user_id: str) -> Optional[UserInDB]:
    """Récupérer un utilisateur par son ID"""
    users = get_users_collection()
    
    try:
        user = await users.find_one({"_id": ObjectId(user_id)})
        if user:
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
        return UserInDB(**user)
    return None


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


def user_to_response(user: UserInDB) -> UserResponse:
    """Convertir UserInDB en UserResponse"""
    return UserResponse(
        id=str(user.id) if user.id else "",
        email=user.email,
        full_name=user.full_name,
        phone_number=user.phone_number,
        phone_verified=user.phone_verified,
        created_at=user.created_at,
        is_active=user.is_active
    )
