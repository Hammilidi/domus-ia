# database.py - Connexion MongoDB et opérations de base
import os
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from dotenv import load_dotenv

# Charger les variables d'environnement
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", ".env")
load_dotenv(dotenv_path)

# Configuration MongoDB
MONGO_USER = os.getenv("MONGO_USER", "")
MONGO_PASSWORD = os.getenv("MONGO_PASSWORD", "")
MONGO_HOST = os.getenv("MONGO_HOST", "localhost")
MONGO_PORT = os.getenv("MONGO_PORT", "27017")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "real_estate_db")

# Construire l'URL de connexion avec ou sans authentification
if MONGO_USER and MONGO_PASSWORD:
    MONGODB_URL = f"mongodb://{MONGO_USER}:{MONGO_PASSWORD}@{MONGO_HOST}:{MONGO_PORT}/?authSource=admin"
else:
    MONGODB_URL = f"mongodb://{MONGO_HOST}:{MONGO_PORT}"


class Database:
    """Singleton pour la connexion MongoDB"""
    client: Optional[AsyncIOMotorClient] = None
    db: Optional[AsyncIOMotorDatabase] = None

    @classmethod
    async def connect(cls):
        """Établir la connexion à MongoDB"""
        if cls.client is None:
            cls.client = AsyncIOMotorClient(MONGODB_URL)
            cls.db = cls.client[MONGODB_DB_NAME]
            # Créer les index
            await cls._create_indexes()
            print(f"✅ Connecté à MongoDB: {MONGODB_DB_NAME}")

    @classmethod
    async def disconnect(cls):
        """Fermer la connexion MongoDB"""
        if cls.client:
            cls.client.close()
            cls.client = None
            cls.db = None
            print("🔌 Déconnexion MongoDB")

    @classmethod
    async def _create_indexes(cls):
        """Créer les index nécessaires pour les collections"""
        if cls.db is not None:
            try:
                # Index unique sur l'email des utilisateurs
                await cls.db.users.create_index("email", unique=True)
                # Index sur le numéro de téléphone
                await cls.db.users.create_index("phone_number", sparse=True)
                # Index sur user_id pour les abonnements
                await cls.db.subscriptions.create_index("user_id")
                # Index sur stripe_subscription_id
                await cls.db.subscriptions.create_index("stripe_subscription_id", sparse=True)
                # Index sur user_id pour les paiements
                await cls.db.payments.create_index("user_id")
                print("✅ Index MongoDB créés")
            except Exception as e:
                print(f"⚠️ Avertissement index MongoDB: {e}")

    @classmethod
    def get_db(cls) -> AsyncIOMotorDatabase:
        """Retourner la base de données"""
        if cls.db is None:
            raise RuntimeError("Database not connected. Call Database.connect() first.")
        return cls.db


# Collections helpers
def get_users_collection():
    return Database.get_db().users


def get_subscriptions_collection():
    return Database.get_db().subscriptions


def get_payments_collection():
    return Database.get_db().payments

