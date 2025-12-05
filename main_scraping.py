import threading
import subprocess
import sys
import os

# Python de l'env virtuel
PYTHON = sys.executable  # utilise le python actif dans l'env

scripts = [
    "scraper_appartement_a_louer_avito.py",
    "scraper_appartement_a_louer_mubawab.py",
    "scraper_appartement_a_vendre_muwabab.py",
    "scraper_appartements_vacational_muwabab.py",
    "scraper_bureaux_et_commerces_a_louer_muwabab.py",
    "scraper_bureaux_et_commerces_a_vendre_muwabab.py",
    "scraper_bureaux_muwabab.py",
    "scraper_locaux_a_vendre_muwabab.py",
    "scraper_locaux_de_commerce_a_louer_avito.py",
    "scraper_locaux_de_commerce_a_louer_muwabab.py",
    "scraper_maison_a_vendre_muwabab.py",
    "scraper_riads_a_vendre_muwabab.py",
    "scraper_terrains_a_vendre_muwabab.py",
    "scraper_villas_a_louer_muwabab.py",
    "scraper_villas_et_maisons_de_luxe_a_vendre_muwabab.py",
]

def run_script(script_name):
    if not os.path.exists(script_name):
        print(f"⚠️ Script manquant : {script_name} (passé)")
        return
    try:
        print(f"🚀 Lancement de {script_name}...")
        subprocess.run([PYTHON, script_name], check=True)
        print(f"✅ Terminé : {script_name}")
    except subprocess.CalledProcessError as e:
        print(f"❌ Erreur dans {script_name}: {e} (continuation)")

threads = []

for script in scripts:
    t = threading.Thread(target=run_script, args=(script,))
    t.start()
    threads.append(t)

for t in threads:
    t.join()

print("🏁 Tous les scripts ont été exécutés.")
