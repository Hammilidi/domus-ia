# db/mongo_client_optimized.py
import os
import logging
import ijson  # pip install ijson
from dotenv import load_dotenv
from datetime import datetime, timezone
from pymongo import MongoClient, UpdateOne, ASCENDING
from pymongo.errors import BulkWriteError
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# Configuration du logging pour un suivi pro
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

# Charger les variables d'environnement
load_dotenv()

# Constantes de performance
BATCH_SIZE = 2000      # Nombre d'opérations par envoi (ajuster selon la taille des docs)
MAX_WORKERS = 4        # Nombre de threads parallèles pour l'écriture

class MongoDBHandler:
    def __init__(self):
        self.user = os.getenv("MONGO_USER")
        self.password = os.getenv("MONGO_PASSWORD")
        self.host = os.getenv("MONGO_HOST", "localhost")
        self.port = int(os.getenv("MONGO_PORT", 27017))
        self.db_name = os.getenv("MONGO_DB")
        self.collection_name = os.getenv("MONGO_COLLECTION")
        
        self.uri = f"mongodb://{self.user}:{self.password}@{self.host}:{self.port}/"
        self.client = MongoClient(
            self.uri, 
            maxPoolSize=50,  # Augmenter le pool pour le multi-threading
            connectTimeoutMS=5000
        )
        self.db = self.client[self.db_name]
        self.collection = self.db[self.collection_name]
        
        self._ensure_indexes()

    def _ensure_indexes(self):
        """
        Crée l'index unique AVANT l'insertion pour garantir la performance 
        des upserts et l'intégrité des données.
        """
        try:
            # Index unique sur l'URL pour éviter les doublons rapidement
            self.collection.create_index([("url", ASCENDING)], unique=True)
            logger.info("✅ Index sur 'url' vérifié/créé.")
        except Exception as e:
            logger.error(f"❌ Erreur indexation : {e}")

    def _process_batch(self, batch: list):
        """
        Fonction exécutée par les workers pour envoyer un lot à MongoDB.
        """
        if not batch:
            return 0

        operations = []
        scraped_at = datetime.now(timezone.utc)

        for item in batch:
            if not item.get("url"):
                continue
            
            item["scraped_at"] = scraped_at
            
            # UpdateOne est idempotent : si ça existe, on met à jour, sinon on crée.
            operations.append(
                UpdateOne(
                    {"url": item["url"]}, 
                    {"$set": item}, 
                    upsert=True
                )
            )

        if not operations:
            return 0

        try:
            # ordered=False est CRITIQUE pour la vitesse : 
            # Mongo n'arrête pas le batch si une erreur survient sur un item
            # et peut paralléliser le traitement en interne.
            result = self.collection.bulk_write(operations, ordered=False)
            return result.upserted_count + result.modified_count
        except BulkWriteError as bwe:
            logger.warning(f"⚠️ Erreur partielle dans le batch : {bwe.details['nWriteErrors']} erreurs.")
            return bwe.details['nInserted'] + bwe.details['nUpserted'] + bwe.details['nModified']
        except Exception as e:
            logger.error(f"❌ Erreur critique d'écriture : {e}")
            return 0

    def stream_parse_json(self, file_path: Path):
        """
        Générateur qui lit le fichier JSON item par item sans charger le fichier complet en RAM.
        Gère les listes simples ou les listes de listes.
        """
        with open(file_path, 'rb') as f:
            # 'item' correspond à chaque élément du tableau JSON principal
            # ijson.items est un générateur paresseux
            try:
                for item in ijson.items(f, 'item'):
                    if isinstance(item, list):
                        # Cas où le JSON est une liste de listes [[{},{}], [{},{}]]
                        for sub_item in item:
                            yield sub_item
                    elif isinstance(item, dict):
                        # Cas standard [{}]
                        yield item
            except ijson.common.IncompleteJSONError:
                logger.error("❌ Erreur : JSON malformé ou incomplet.")

    def import_data(self, json_path: str | Path):
        json_path = Path(json_path)
        if not json_path.exists():
            raise FileNotFoundError(f"Fichier introuvable : {json_path}")

        logger.info(f"🚀 Démarrage de l'import optimisé depuis {json_path.name}")
        
        batch = []
        total_processed = 0
        
        # ThreadPoolExecutor gère l'envoi parallèle des batchs
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            
            # Lecture en streaming
            for item in self.stream_parse_json(json_path):
                batch.append(item)
                
                # Dès que le batch est plein, on l'envoie à un thread
                if len(batch) >= BATCH_SIZE:
                    futures.append(executor.submit(self._process_batch, list(batch)))
                    batch = []  # Reset du batch
                    
                    # Nettoyage des tâches terminées pour éviter de saturer la mémoire des futures
                    if len(futures) > MAX_WORKERS * 2:
                        completed = [f for f in futures if f.done()]
                        for f in completed:
                            total_processed += f.result()
                            futures.remove(f)

            # Traiter le dernier batch restant
            if batch:
                futures.append(executor.submit(self._process_batch, batch))

            # Attendre la fin de tous les threads
            for f in futures:
                if not f.done():
                    total_processed += f.result()
                else:
                    # Si déjà fait mais pas comptabilisé
                    total_processed += f.result()

        logger.info(f"🏁 Import terminé. Total opérations réussies : {total_processed}")

if __name__ == "__main__":
    # Ajustement du chemin pour correspondre à votre structure
    current_dir = Path(__file__).resolve().parent
    # On remonte d'un cran si le script est dans /db, sinon ajustez selon votre structure
    json_file = current_dir.parent / "data" / "combined_data.json"
    
    if not json_file.exists():
        # Fallback si exécuté depuis la racine
        json_file = Path("data/combined_data.json")

    handler = MongoDBHandler()
    handler.import_data(json_file)