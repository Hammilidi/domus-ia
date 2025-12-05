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
HEADERS = {"User-Agent": "Mozilla/5.0"}
SOURCE_SITE = BASE_URL
# Cible la catégorie de votre script précédent
CATEGORY_SLUG = "appartements-a-vendre" 

# Liste des villes à scraper (nettoyée des doublons)
CITIES_TO_SCRAPE = sorted(list(set([
    "marrakech", "casablanca", "rabat", "tanger", "fes", "mohammedia",
    "oujda", "tetouan", "settat", "khouribga", "benguerir", "youssoufia",
    "safi", "sale", "temara", "bouskoura", "agadir", "meknes", "kenitra",
    "el_jadida", "nador", "berrechid", "khemisset", "larache", "guelmim",
    "taourirt", "sidi_kacem", "taza", "azrou", "ouarzazate", "beni_mellal",
    "midelt", "aita_azza", "sidi_slimane", "sidi_kaouki", "imouzzer_kandar",
    "oued_zem", "ain_sefra", "tiflet", "sidi_bel_abbes", "bouznika",
    "sidi_ifni", "azemmour", "tafraout", "sidi_rahhal", "ouazzane",
    "sidi_hajji", "sidi_yaala", "ifrane", "azilal", "tiznit",
    "oued_edaoud", "berrchid", "berkane", "essaouira", "dakhla",
])))


def fetch_mubawab_page(city_slug: str, page_number: int) -> str | None:
    """
    Récupère le contenu HTML d'une page de résultats pour une ville, 
    la catégorie et une page données.
    """
    if page_number == 1:
        # URL pour la première page
        url = f"{BASE_URL}/fr/st/{city_slug}/{CATEGORY_SLUG}"
    else:
        # URL pour les pages suivantes
        url = f"{BASE_URL}/fr/st/{city_slug}/{CATEGORY_SLUG}:p:{page_number}"
    
    print(f"Fetching: {url}")
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status() 
        
        # Pause de politesse pour éviter le blocage IP
        time.sleep(1) 
        
        # Vérifier si la page est une page d'erreur
        if "Cette page n'est plus disponible" in response.text:
             print(f"    INFO: Page {page_number} pour {city_slug} n'existe pas. Arrêt pour cette ville.")
             return None # Condition d'arrêt de pagination
             
        return response.text
        
    except requests.exceptions.HTTPError as e:
        # Gère les 404 (ville non trouvée) ou autres erreurs
        print(f"    ATTENTION: Erreur HTTP {e.response.status_code} pour {url}. Passage à la ville suivante.")
        return None # Condition d'arrêt de pagination
    except requests.exceptions.RequestException as e:
        print(f"    ERREUR: La requête a échoué pour {url}: {e}. Passage à la ville suivante.")
        return None # Condition d'arrêt de pagination

def parse_ad_data(ad_element, source_site, date_scraped):
    """
    Extrait les informations d'une seule annonce (élément BeautifulSoup).
    """
    
    # --- URL et Titre ---
    title = None
    annonce_url = None
    try:
        title_link_tag = ad_element.select_one("h2.listingTit a")
        if title_link_tag:
            title = title_link_tag.get_text(strip=True)
            annonce_url = title_link_tag.get('href')
    except Exception:
        pass

    # --- Prix ---
    price = None
    try:
        price_tag = ad_element.select_one("span.priceTag")
        if price_tag:
            price = re.sub(r'\s+', ' ', price_tag.get_text(strip=True)).replace("\u00a0", " ")
    except Exception:
        pass

    # --- Localisation ---
    location = None
    try:
        location_tag = ad_element.select_one("span.listingH3")
        if location_tag:
            location = " ".join(location_tag.get_text(strip=True).split())
    except Exception:
        pass
        
    # --- Type de propriété (Inféré depuis votre demande) ---
    property_type = "Appartement" # Défini selon vos instructions

    # --- Surface, Pièces, Chambres ---
    surface = None
    pieces = None
    bedrooms = None
    
    try:
        details = ad_element.select("div.adDetailFeature")
        for detail in details:
            icon_tag = detail.select_one("i")
            if not icon_tag: continue
            
            icon_class = icon_tag.get("class", [])
            span_text = " ".join(detail.select_one("span").get_text(strip=True).split())
            
            if "icon-triangle" in icon_class:
                surface = span_text
            elif "icon-house-boxes" in icon_class:
                pieces = span_text.split(" ")[0]
            elif "icon-bed" in icon_class:
                bedrooms = span_text.split(" ")[0]
                
    except Exception as e:
        print(f"    Erreur (détails): {e}")
        
    # --- Description ---
    description = None
    try:
        desc_tag = ad_element.select_one("p.listingP")
        if desc_tag:
            description = desc_tag.get_text(strip=True)
    except Exception:
        pass

    # --- Caractéristiques (Balcon, Piscine, Ascenseur, etc.) ---
    caracteristiques_supp_list = []
    balcon = False
    piscine = False
    ascenseur = False
    try:
        features_elements = ad_element.select("div.adFeatures div.adFeature span")
        for feat in features_elements:
            feat_text = feat.get_text(strip=True).lower()
            if feat_text: 
                caracteristiques_supp_list.append(feat_text.capitalize())
                
                if "terrasse" in feat_text or "balcon" in feat_text:
                    balcon = True
                if "piscine" in feat_text:
                    piscine = True
                if "ascenseur" in feat_text:
                    ascenseur = True
    except Exception:
        pass

    # --- Images ---
    images = []
    try:
        images_tags = ad_element.select("div.adSlider img[data-lazy]")
        images = [img.get("data-lazy") for img in images_tags if img.get("data-lazy")]
    except Exception:
        pass

    # --- Champs non disponibles sur la page liste ---
    adresse = ""
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
        "property_type": property_type,
        "url": annonce_url,
        "source_site": source_site,
        "surface": surface,
        "rooms": pieces or bedrooms,  # Priorise "Pièces" ou "Chambres"
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

def main():
    """
    Fonction principale pour orchestrer le scraping de plusieurs villes et pages.
    """
    all_annonces = []
    date_scraped = datetime.now().isoformat()
    
    # Boucle N°1: Itérer sur chaque ville
    for city in CITIES_TO_SCRAPE:
        print(f"\n--- 🚀 Démarrage du scraping pour les {CATEGORY_SLUG} à : {city} ---")
        page_number = 1
        
        # Boucle N°2: Itérer sur chaque page (pagination)
        while True:
            html_content = fetch_mubawab_page(city, page_number)
            
            # Arrêter la pagination si la page est vide ou inaccessible
            if not html_content:
                break 

            soup = BeautifulSoup(html_content, "html.parser")
            
            listings = soup.find_all("div", class_="listingBox")
            
            # Filtrer pour ne garder que les vraies annonces (/fr/a/)
            valid_ads = []
            for ad in listings:
                link_ref = ad.get('linkref')
                if link_ref and link_ref.startswith(f'{BASE_URL}/fr/a/'):
                    valid_ads.append(ad)
            
            # Condition d'arrêt : si la page est vide (pas d'annonces)
            if not valid_ads:
                print(f"    ⏹️  Aucune annonce valide trouvée sur la page {page_number} pour {city}. Fin de la pagination.")
                break 

            print(f"    ✅ Page {page_number}: {len(valid_ads)} annonces trouvées.")

            # Boucle N°3: Itérer sur chaque annonce de la page
            for ad in valid_ads:
                ad_data = parse_ad_data(ad, SOURCE_SITE, date_scraped)
                all_annonces.append(ad_data)
            
            page_number += 1
            
            # Sécurité anti-boucle infinie
            if page_number > 200: # 200 pages par ville max
                print(f"    ATTENTION: Limite de 200 pages atteinte pour {city}. Passage à la ville suivante.")
                break

    # --- 5. Sauvegarde Finale ---
    print(f"\n--- ✅ Scraping de toutes les villes terminé ! ---")
    print(f"Nombre total d'annonces extraites : {len(all_annonces)}")



    # Création du dossier 'data' s'il n'existe pas
    output_dir = "data"
    os.makedirs(output_dir, exist_ok=True)

    output_filename = "mubawab_appartements_a_vendre.json"
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

# Point d'entrée du script
if __name__ == "__main__":
    main()