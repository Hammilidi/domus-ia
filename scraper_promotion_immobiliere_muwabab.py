import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
import time
import re
import os
import json
# --- Configuration ---
BASE_URL = "https://www.mubawab.ma"
SOURCE_SITE = BASE_URL
WAIT_TIMEOUT = 120  # Timeout plus long pour l'API

# --- METTEZ VOTRE CLÉ API SCRAPERAPI ICI ---
API_KEY = "eefb5085c775492b866f3e8894894dbcff0b8f47c08" 
# -------------------------------------------

if API_KEY == "eefb5085c775492b866f3e8894894dbcff0b8f47c08":
    print("ERREUR : Veuillez remplacer 'VOTRE_CLE_API_SCRAPERAPI' par votre véritable clé API ScraperAPI.")
    exit()

def fetch_page_with_scraperapi(target_url, api_key):
    """
    Utilise ScraperAPI pour charger la page et exécuter le JavaScript.
    """
    print(f"Fetching avec ScraperAPI : {target_url}")
    
    # Paramètres pour ScraperAPI
    payload = {
        'api_key': api_key,
        'url': target_url,
        'render': 'true', # Demande l'exécution du JavaScript
        'country_code': 'ma' # Spécifie une IP marocaine
    }
    
    api_url = "http://api.scraperapi.com"
    
    try:
        response = requests.get(api_url, params=payload, timeout=WAIT_TIMEOUT)
        response.raise_for_status() # Lève une exception si le statut n'est pas 200
        
        print("✅ HTML de la page chargée avec succès.")
        return response.text
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Erreur lors de l'appel à ScraperAPI : {e}")
        return None

# --- Fonction de parsing (inchangée, elle est correcte) ---
def parse_ad_data(ad_element, source_site, date_scraped):
    """
    Extrait les informations d'une seule annonce de promotion (élément BeautifulSoup).
    """
    
    # --- URL et Titre ---
    title = None
    annonce_url = None
    try:
        link_tag = ad_element.find("a")
        if link_tag:
            relative_url = link_tag.get('href')
            if relative_url:
                annonce_url = source_site + relative_url
        
        title_tag = ad_element.select_one("h4")
        if title_tag:
            title = title_tag.get_text(strip=True)
    except Exception:
        pass

    # --- Prix ---
    price = None
    try:
        price_tag = ad_element.select_one("span.price")
        if price_tag:
            price = re.sub(r'\s+', ' ', price_tag.get_text(strip=True)).replace("\u00a0", " ")
    except Exception:
        pass

    # --- Localisation ---
    location = None
    try:
        location_tag = ad_element.select_one("span.location")
        if location_tag:
            location = location_tag.get_text(strip=True)
    except Exception:
        pass
        
    # --- Type de propriété ---
    property_type = None
    try:
        type_tag = ad_element.select_one("span.types")
        if type_tag:
            property_type = type_tag.get_text(strip=True)
    except Exception:
        pass

    # --- Description ---
    description = None
    try:
        desc_tag = ad_element.select_one("p.desc")
        if desc_tag:
            description = desc_tag.get_text(strip=True)
    except Exception:
        pass

    # --- Caractéristiques ---
    caracteristiques_supp_list = []
    try:
        features_elements = ad_element.select("div.proDetails span")
        for feat in features_elements:
            feat_text = feat.get_text(strip=True)
            if feat_text: 
                caracteristiques_supp_list.append(feat_text)
    except Exception:
        pass

    # --- Images ---
    images = []
    try:
        img_tag = ad_element.select_one("div.imgBox img")
        if img_tag and img_tag.get('src'):
            images = [img_tag.get('src')]
    except Exception:
        pass

    # --- Champs non disponibles ---
    adresse = ""
    surface = None
    rooms = None
    balcon = False
    piscine = False
    ascenseur = False
    etage = None
    age_bien = None
    contact = None
    date_pub = None

    # --- Assemblage du dictionnaire final ---
    return {
        "title": title,
        "price": price,
        "location": location,
        "adresse": adresse,
        "property_type": property_type or "Promotion Immobilière", # Fallback
        "url": annonce_url,
        "source_site": source_site,
        "surface": surface,
        "rooms": rooms,
        "description": description,
        "balcon": str(balcon),
        "piscine": str(piscine),
        "ascenseur": str(ascenseur),
        "etage": etage,
        "age_bien": age_bien,
        "caracteristiques_supp": ";".join(caracteristiques_supp_list),
        "images": ";".join(images),
        "contact": contact,
        "date_scraped": date_scraped,
        "date_publication": date_pub
    }

# --- Script principal (mis à jour) ---
def main():
    all_annonces = []
    date_scraped = datetime.now().isoformat()
    page_number = 1
    
    print("🚀 Démarrage du scraping des promotions immobilières...")
    
    # Boucle de pagination
    while True:
        if page_number == 1:
            target_url = f"{BASE_URL}/fr/listing-promotion"
        else:
            target_url = f"{BASE_URL}/fr/listing-promotion:p:{page_number}"
        
        # Utiliser ScraperAPI pour charger la page
        html_content = fetch_page_with_scraperapi(target_url, API_KEY)
        
        if not html_content:
            print(f"Impossible de charger la page {page_number}. Arrêt de la pagination.")
            break

        # Enregistrer le HTML (pour débogage)
        with open("page_test.html", "w", encoding="utf-8") as f:
            f.write(html_content)

        soup = BeautifulSoup(html_content, "html.parser")

        # Trouve tous les conteneurs d'annonces de promotion
        listings = soup.find_all("div", class_="promotionBox")
        
        if not listings:
            print(f"⏹️  Aucune annonce trouvée sur la page {page_number}. Fin du scraping.")
            break # Condition d'arrêt
            
        print(f"    ✅ {len(listings)} annonces de promotion trouvées sur la page {page_number}.")

        for ad in listings:
            ad_data = parse_ad_data(ad, SOURCE_SITE, date_scraped)
            all_annonces.append(ad_data)
        
        page_number += 1
        
        # Sécurité
        if page_number > 50: # Limite de 50 pages
            print("Limite de 50 pages atteinte. Arrêt.")
            break

    # --- Sauvegarde en JSON ---
    

    # Création du dossier 'data' s'il n'existe pas
    output_dir = "data"
    os.makedirs(output_dir, exist_ok=True)

    output_filename = "mubawab_listing_promotion.json"
    output_filename = os.path.join(output_dir, "mubawab_terrains.json")

    try:
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(all_annonces, f, indent=4, ensure_ascii=False)
        print(f"✅ Les données ont été enregistrées dans '{output_filename}'.")

        if all_annonces:
            print("\n--- EXEMPLE DE LA PREMIÈRE ANNONCE ---")
            print(json.dumps(all_annonces[0], indent=2, ensure_ascii=False))
            print("---------------------------------------")

    except Exception as e:
        print(f"❌ Erreur lors de l'écriture du fichier JSON : {e}")    

if __name__ == "__main__":
    main()