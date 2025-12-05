from pymongo import MongoClient
from bson import ObjectId
import os
from dotenv import load_dotenv
import sys

# Chargement des variables d'environnement
load_dotenv()

def test_authenticated_connection():
    print("🔍 Lecture de la configuration .env ...")
    
    # Récupération des identifiants (avec valeurs par défaut si absentes)
    user = os.getenv("MONGO_USER")
    password = os.getenv("MONGO_PASSWORD")
    host = os.getenv("MONGO_HOST", "localhost")
    port = os.getenv("MONGO_PORT", "27017")
    db_name = os.getenv("MONGO_DB", "listings")
    collection_name = os.getenv("MONGO_COLLECTION", "listings")

    if not user or not password:
        print("⚠️  ATTENTION : MONGO_USER ou MONGO_PASSWORD manquant dans le fichier .env")
        print("   Le script va tenter de se connecter sans, mais cela risque d'échouer.")
        uri = f"mongodb://{host}:{port}/"
    else:
        # Construction de l'URI sécurisée
        # On encode les caractères spéciaux si nécessaire, mais ici on reste simple
        uri = f"mongodb://{user}:{password}@{host}:{port}/?authSource=admin"

    print(f"🔌 Connexion vers : mongodb://{user}:****@{host}:{port}/")

    try:
        # Connexion avec un timeout court pour ne pas bloquer si erreur
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        
        # Test réel d'authentification (commande ping)
        client.admin.command('ping')
        print("✅ AUTHENTIFICATION RÉUSSIE ! Python est connecté à Docker.")

        db = client[db_name]
        collection = db[collection_name]

        # Comptage des documents
        count = collection.count_documents({})
        print(f"\n📂 Base de données : '{db_name}'")
        print(f"📄 Collection : '{collection_name}'")
        print(f"Hs Nombre de biens trouvés : {count}")

        if count > 0:
            print("\n📋 Voici des IDs VALIDES à copier pour votre agent :")
            print("-" * 50)
            # On récupère title et location pour être sûr de ce qu'on copie
            cursor = collection.find({}, {"title": 1, "location": 1, "price": 1}).limit(3)
            for doc in cursor:
                print(f"🆔 ID : {doc['_id']}")
                print(f"   Titre : {doc.get('title', 'N/A')}")
                print(f"   Prix  : {doc.get('price', 'N/A')} DH")
                print("-" * 50)
        else:
            print("\n⚠️  La base est vide. L'agent ne trouvera rien.")
            print("   Voulez-vous insérer un bien de test ? (Modifiez ce script pour le faire)")

    except Exception as e:
        print("\n❌ ÉCHEC DE CONNEXION")
        print(f"Erreur : {e}")
        print("\n💡 Conseil : Vérifiez que MONGO_USER et MONGO_PASSWORD dans votre fichier .env")
        print("   correspondent exactement à ceux définis lors de la création du conteneur Docker.")

if __name__ == "__main__":
    test_authenticated_connection()