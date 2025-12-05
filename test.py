import requests
from bs4 import BeautifulSoup

base_url = "https://www.mubawab.ma"
headers = {"User-Agent": "Mozilla/5.0"}

# https://www.mubawab.ma/fr/listing-promotion

# url = f"{base_url}/fr/st/casablanca/appartements-vacational"
url = f"{base_url}/fr/listing-promotion"
res = requests.get(url, headers=headers)
soup = BeautifulSoup(res.text, "html.parser")

# Enregistrer le contenu HTML dans un fichier local
with open("page_test.html", "w", encoding="utf-8") as f:
    f.write(soup.prettify())

print("✅ Le contenu HTML de la page a été enregistré dans 'page_test.html'.")
