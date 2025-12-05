import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
import time
import os   
import json


# --- Configuration ---
base_url = "https://www.avito.ma"
headers = {"User-Agent": "Mozilla/5.0"}

# Mettez ici les slugs URL des villes que vous voulez scraper
CITIES_TO_SCRAPE = [
    "marrakech",
    "casablanca",
    "rabat",
    "tanger",
    "fes",
    "mohammedia",
    "oujda",
    "tetouan",
    "settat",
    "khouribga",
    "benguerir",  
    "youssoufia", 
    "safi",
    "sale",       
    "temara",
    "bouskoura",
    "agadir",
    "meknes",
    "kenitra",
    "el_jadida",
    "nador",
    "berrechid",
    "khemisset",
    "larache",
    "guelmim",
    "taourirt",
    "sidi_kacem",
    "taza",
    "azrou",
    "ouarzazate",
    "beni_mellal",
    "midelt",
    "aita_azza",
    "sidi_slimane",
    "sidi_kaouki",
    "imouzzer_kandar",
    "oued_zem",
    "ain_sefra",
    "tiflet",
    "sidi_bel_abbes",
    "bouznika",
    "sidi_ifni",
    "azemmour",
    "tafraout",
    "sidi_rahhal",
    "ouazzane",
    "sidi_hajji",
    "sidi_yaala"
    "ifrane",
    "azilal",
    "larache",
    "tiznit",
    "oued_edaoud",
    "berrchid",
    "berkane",
    "essaouira",
    "dakhla",
]

# --- Fonction d'analyse (Parsing) ---

def parse_ad(ad_element, source_site, date_scraped):
    """
    Extrait les informations d'une seule annonce (élément BeautifulSoup).
    """
    
    # --- URL ---
    try:
        annonce_url = ad_element.get('href')
        if annonce_url and not annonce_url.startswith('http'):
            annonce_url = base_url + annonce_url
    except Exception:
        annonce_url = None

    # --- Titre ---
    try:
        title = ad_element.find("p", class_="iHApav").get('title')
    except Exception:
        title = None

    # --- Prix (Logique améliorée) ---
    price = None
    try:
        price_element = ad_element.find("p", class_="dJAfqm")
        if price_element:
            # Vérifier s'il s'agit de "Demander le prix"
            ask_for_price = price_element.find("span", class_="fftEKO")
            if ask_for_price:
                price = "Demander le prix"
            else:
                # Sinon, extraire le prix et la devise
                price_span = price_element.find("span", class_="PuYkS")
                currency_span = price_element.find("span", class_="eHXozK") # Devise
                
                if price_span and currency_span:
                    price_value = price_span.text.strip().replace("\u202f", "")
                    price_currency = currency_span.text.strip()
                    price = f"{price_value} {price_currency}"
                else:
                    # Fallback si la structure est inattendue
                    price = price_element.get_text(strip=True, separator=" ")
    except Exception:
        price = None

    # --- Localisation et Type de propriété ---
    property_type = None
    location = None
    try:
        location_p = ad_element.find("div", class_="fHMeoC").find("p", class_="layWaX")
        if location_p:
            full_location_text = location_p.text.strip()
            # Sépare "Appartements dans Casablanca, Maarif"
            parts = full_location_text.split(" dans ")
            if len(parts) == 2:
                property_type = parts[0].strip()
                location = parts[1].strip()
            else:
                location = full_location_text # Fallback
    except Exception:
        pass # Les variables restent None

    # --- Caractéristiques (Surface, Chambres, etc.) ---
    surface = None
    rooms = None
    caracteristiques_supp_list = []
    try:
        features_spans = ad_element.select(".sc-b57yxx-2.cCLvhv > span.cAiIZZ")
        for span in features_spans:
            inner_span = span.find("span", title=True)
            if inner_span:
                feature_title = inner_span.get('title')
                feature_value = inner_span.get_text(strip=True).replace("\u202f", "")
                
                caracteristiques_supp_list.append(f"{feature_title}: {feature_value}")
                
                if feature_title == "Chambres":
                    rooms = feature_value
                elif feature_title == "Surface totale":
                    surface = feature_value # ex: "109 m²"
                    
    except Exception:
        pass # Les variables restent None

    # --- Images ---
    try:
        main_image = ad_element.find("img", class_="kdSDie").get('src')
        images = [main_image]
    except Exception:
        images = []

    # --- Date de Publication ---
    try:
        date_pub = ad_element.find("div", class_="jDipnj").find("p", class_="layWaX").text.strip()
    except Exception:
        date_pub = None

    # --- Champs non disponibles sur la page de résultats ---
    description = None
    adresse = ""
    balcon = False
    piscine = False
    ascenseur = False
    etage = None
    age_bien = None
    contact = None

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

# --- Fonction principale (Main) ---

def main():
    all_annonces = []
    source_site = "https://www.avito.ma"
    date_scraped = datetime.now().isoformat()
    
    # Boucle N°1: Itérer sur chaque ville
    for city in CITIES_TO_SCRAPE:
        print(f"\n--- 🚀 Démarrage du scraping pour la ville : {city} ---")
        page_number = 1
        
        # Boucle N°2: Itérer sur chaque page (pagination)
        while True:
            url = f"{base_url}/fr/{city}/locaux-a-louer?o={page_number}"
            print(f"Scraping {url} ...")
            
            try:
                res = requests.get(url, headers=headers)
                res.raise_for_status() # Lève une exception si le statut n'est pas 200
                
                # Ajout d'une pause pour être respectueux et éviter le blocage IP
                time.sleep(2) 

                soup = BeautifulSoup(res.text, "html.parser")
                
                listings = soup.find_all("a", class_="sc-1jge648-0")
                
                # Condition d'arrêt : si la page est vide, on arrête
                if not listings:
                    print(f"⏹️  Aucune annonce trouvée sur la page {page_number} pour {city}. Passage à la ville suivante.")
                    break # Sort de la boucle 'while' (pagination)

                print(f"    ✅ Trouvé {len(listings)} annonces sur la page {page_number}.")

                # Boucle N°3: Itérer sur chaque annonce de la page
                for ad in listings:
                    annonce_data = parse_ad(ad, source_site, date_scraped)
                    all_annonces.append(annonce_data)
                
                # Passer à la page suivante
                page_number += 1
                
            except requests.exceptions.HTTPError as e:
                print(f"❌ Erreur HTTP {e.response.status_code} pour {url}. Passage à la ville suivante.")
                break # Sort de la boucle 'while'
            except requests.exceptions.RequestException as e:
                print(f"❌ Erreur de requête pour {url}: {e}. Passage à la ville suivante.")
                break # Sort de la boucle 'while'
            except Exception as e:
                print(f"❌ Erreur inattendue lors de l'analyse de {url}: {e}")
                # On continue à la page suivante par précaution
                page_number += 1 
                if page_number > 99: # Sécurité pour éviter une boucle infinie
                    print("⚠️ Limite de 99 pages atteinte. Passage à la ville suivante.")
                    break

    print("\n--- ✅ Scraping de toutes les villes terminé ! ---")
    print(f"Nombre total d'annonces extraites : {len(all_annonces)}")

    # --- Enregistrer le résultat final dans un fichier JSON ---
    
    
    # Création du dossier 'data' s'il n'existe pas
    output_dir = "data"
    os.makedirs(output_dir, exist_ok=True)

    output_filename = "locaux_de_commerce_a_louer_avito.json"
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