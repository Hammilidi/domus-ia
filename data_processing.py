import os
import json

# Dossier contenant les fichiers JSON
data_dir = "data"
combined_filename = os.path.join(data_dir, "combined_data.json")

all_data = []

# Parcours de tous les fichiers dans le dossier data/
for filename in os.listdir(data_dir):
    if filename.endswith(".json") and filename != "combined_data.json":  # éviter le fichier combiné lui-même
        file_path = os.path.join(data_dir, filename)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    all_data.extend(data)  # ajoute toutes les annonces
                else:
                    print(f"⚠️ Le fichier {filename} n'est pas une liste JSON")
        except Exception as e:
            print(f"❌ Erreur lors de la lecture de {filename} : {e}")

# Sauvegarde du fichier combiné
try:
    with open(combined_filename, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=4, ensure_ascii=False)
    print(f"✅ Tous les fichiers JSON ont été combinés dans '{combined_filename}'")
    print(f"Nombre total d'annonces : {len(all_data)}")
except Exception as e:
    print(f"❌ Erreur lors de l'écriture du fichier combiné : {e}")
