# models.py - Modèles Pydantic pour la gestion des utilisateurs et abonnements
from datetime import datetime
from typing import Optional
from enum import Enum
from pydantic import BaseModel, Field, EmailStr
from bson import ObjectId


class PyObjectId(str):
    """Custom ObjectId type for Pydantic"""
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, field=None):
        if isinstance(v, ObjectId):
            return str(v)
        if isinstance(v, str) and ObjectId.is_valid(v):
            return v
        raise ValueError("Invalid ObjectId")


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    PENDING = "pending"


class SubscriptionPlan(str, Enum):
    MONTHLY = "monthly"
    YEARLY = "yearly"
    TRIAL = "trial"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


# ==================== USER MODELS ====================

class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    phone_number: Optional[str] = None
    

class UserCreate(UserBase):
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserInDB(UserBase):
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    password_hash: str
    phone_verified: bool = False
    phone_verification_code: Optional[str] = None
    phone_verification_expires: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True

    class Config:
        populate_by_name = True
        json_encoders = {ObjectId: str}


class UserResponse(UserBase):
    id: str
    phone_verified: bool
    created_at: datetime
    is_active: bool

    class Config:
        from_attributes = True


# ==================== SUBSCRIPTION MODELS ====================

class SubscriptionBase(BaseModel):
    plan: SubscriptionPlan
    

class SubscriptionCreate(SubscriptionBase):
    user_id: str


class SubscriptionInDB(SubscriptionBase):
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    user_id: str
    status: SubscriptionStatus = SubscriptionStatus.PENDING
    started_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    stripe_subscription_id: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        json_encoders = {ObjectId: str}


class SubscriptionResponse(SubscriptionBase):
    id: str
    user_id: str
    status: SubscriptionStatus
    started_at: Optional[datetime]
    expires_at: Optional[datetime]

    class Config:
        from_attributes = True


# ==================== PAYMENT MODELS ====================

class PaymentBase(BaseModel):
    amount: float
    currency: str = "MAD"  # Dirham Marocain


class PaymentCreate(PaymentBase):
    user_id: str
    subscription_id: str


class PaymentInDB(PaymentBase):
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    user_id: str
    subscription_id: str
    status: PaymentStatus = PaymentStatus.PENDING
    stripe_payment_id: Optional[str] = None
    stripe_session_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {ObjectId: str}


class PaymentResponse(PaymentBase):
    id: str
    user_id: str
    status: PaymentStatus
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== TOKEN MODELS ====================

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: Optional[str] = None
    email: Optional[str] = None
