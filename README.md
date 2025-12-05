# 🏠 DomusIA - Assistant Immobilier IA WhatsApp

DomusIA est un assistant immobilier intelligent accessible via WhatsApp, propulsé par un système multi-agents (SMA) basé sur LangGraph et Google Gemini.

## 📋 Table des matières

- [Fonctionnalités](#-fonctionnalités)
- [Architecture](#-architecture)
- [Prérequis](#-prérequis)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Démarrage](#-démarrage)
- [Utilisation](#-utilisation)
- [Structure du projet](#-structure-du-projet)

---

## ✨ Fonctionnalités

- 🔍 **Recherche immobilière** : Appartements, villas, bureaux, terrains (location/vente)
- 💰 **Négociation assistée** : Conseils de négociation basés sur le marché
- ⚖️ **Conseils juridiques** : RAG sur le droit immobilier marocain
- 🖼️ **Analyse d'images** : Envoyez une photo de bien pour trouver des similaires
- 🔔 **Alertes** : Notifications quand un bien correspondant arrive
- 📱 **Interface WhatsApp** : Conversation naturelle via Twilio

---

## 🏗️ Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  WhatsApp   │────▶│ Twilio API   │────▶│ whatsapp_api.py │
│  (Client)   │◀────│  (Webhook)   │◀────│    (FastAPI)    │
└─────────────┘     └──────────────┘     └────────┬────────┘
                                                  │
                    ┌─────────────────────────────▼──────────────────────────┐
                    │              LangGraph Multi-Agent System               │
                    │  ┌──────────────────────────────────────────────────┐  │
                    │  │                  Superviseur                      │  │
                    │  └──────────────────────────────────────────────────┘  │
                    │         ▼              ▼              ▼                │
                    │  ┌──────────┐   ┌──────────┐   ┌──────────┐           │
                    │  │ Recherche│   │  Négo    │   │ Juridique│           │
                    │  │  Agent   │   │  Agent   │   │  Agent   │           │
                    │  └──────────┘   └──────────┘   └──────────┘           │
                    └───────────────────────────────────────────────────────┘
                                         │
                    ┌────────────────────┼────────────────────┐
                    ▼                    ▼                    ▼
            ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
            │   MongoDB    │    │   ChromaDB   │    │   Stripe     │
            │  (Listings)  │    │  (RAG Droit) │    │  (Paiements) │
            └──────────────┘    └──────────────┘    └──────────────┘
```

---

## 📦 Prérequis

- **Python 3.11+**
- **MongoDB** (local ou Docker)
- **Compte Twilio** (WhatsApp Sandbox gratuit pour dev)
- **Clé API Google** (Gemini)
- **Compte Stripe** (optionnel, pour les paiements)
- **ngrok** (pour exposer le webhook en local)

---

## 🚀 Installation

### 1. Cloner le projet

```bash
git clone https://github.com/votre-repo/DomusIA.git
cd DomusIA
```

### 2. Créer l'environnement virtuel

```bash
python -m venv env3.12
# Windows
.\env3.12\Scripts\activate
# Linux/Mac
source env3.12/bin/activate
```

### 3. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 4. Démarrer MongoDB

```bash
# Avec Docker (recommandé)
docker run -d -p 27017:27017 --name mongo \
  -e MONGO_INITDB_ROOT_USERNAME=admin \
  -e MONGO_INITDB_ROOT_PASSWORD=secret \
  mongo:7.0
```

---

## ⚙️ Configuration

### Créer le fichier `.env`

```bash
cp .env.example .env
# Éditer avec vos valeurs
```

### Variables d'environnement requises

```env
# Google Gemini API
GOOGLE_API_KEY=votre_cle_gemini

# MongoDB
MONGO_USER=admin
MONGO_PASSWORD=secret
MONGO_HOST=localhost
MONGO_PORT=27017
MONGO_DB=listings
MONGO_COLLECTION=listings

# Twilio (WhatsApp)
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxx
TWILIO_WHATSAPP_NUMBER=+14155238886

# JWT (pour l'interface web)
JWT_SECRET_KEY=votre_secret_jwt_fort
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24

# Stripe (optionnel)
STRIPE_SECRET_KEY=sk_test_xxx
STRIPE_PUBLISHABLE_KEY=pk_test_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx

# URLs
WEB_BASE_URL=http://localhost:8080
```

---

## 🚀 Démarrage

### Terminal 1 : Interface Web (port 8080)

```bash
cd SMA
python -m uvicorn web.web_api:app --port 8080 --reload
```

### Terminal 2 : API WhatsApp (port 8000)

```bash
cd SMA
python -m uvicorn whatsapp_api:app --host 0.0.0.0 --port 8000 --reload
```

### Terminal 3 : Tunnel ngrok (pour Twilio)

```bash
ngrok http 8000
# Copier l'URL https://xxx.ngrok.io
```

### Configuration Twilio Sandbox

1. Aller sur [Twilio Console](https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn)
2. Configurer le webhook : `https://xxx.ngrok.io/whatsapp`
3. Envoyer `join <sandbox-name>` au numéro Twilio depuis WhatsApp

---

## 💬 Utilisation

### Commandes WhatsApp

| Message | Action |
|---------|--------|
| `Bonjour` | Présentation du bot |
| `Je cherche un appartement à Casablanca` | Recherche de biens |
| `Je veux louer une villa à Marrakech max 20000/mois` | Recherche location |
| `Le 2 m'intéresse` | Sélectionner un bien par numéro |
| `Je veux négocier` | Lancer la négociation |
| `Quels sont les frais de notaire ?` | Question juridique |
| `Mes alertes` | Voir ses alertes actives |
| *Envoyer une photo* | Analyse d'image et suggestions |

### Interface Web

- **Accueil** : http://localhost:8080
- **Inscription** : http://localhost:8080/register
- **Connexion** : http://localhost:8080/login
- **Tableau de bord** : http://localhost:8080/dashboard

---

## 📁 Structure du projet

```
DomusIA/
├── SMA/                          # Système Multi-Agents
│   ├── agents/                   # Agents spécialisés
│   │   ├── agent_recherche.py    # Recherche immobilière
│   │   ├── agent_negociation.py  # Négociation
│   │   └── agent_juridique.py    # Conseils juridiques
│   ├── outils/                   # Outils des agents
│   │   ├── outils_immobilier.py  # Recherche MongoDB
│   │   ├── outils_negociation.py # Calculs de prix
│   │   ├── outils_droit.py       # RAG juridique
│   │   └── outils_alertes.py     # Gestion des alertes
│   ├── services/                 # Services métier
│   │   └── alert_service.py      # Service d'alertes
│   ├── web/                      # Interface web
│   │   ├── web_api.py            # FastAPI (port 8080)
│   │   ├── templates/            # Templates Jinja2
│   │   ├── static/               # CSS, JS
│   │   └── services/             # Auth, Stripe, etc.
│   ├── whatsapp_api.py           # API WhatsApp (port 8000)
│   ├── superviseur_fluent.py     # Orchestrateur LangGraph
│   └── state.py                  # État partagé
├── data/                         # Données scrapées
├── RAG/                          # Documents juridiques
├── scraper_*.py                  # Scripts de scraping
├── requirements.txt              # Dépendances Python
├── .env                          # Configuration (non versionné)
└── .gitignore
```

---

## 🧪 Tests

```bash
# Tester l'API WhatsApp
curl http://localhost:8000/health

# Tester l'interface web
curl http://localhost:8080/health
```

---

## 🐛 Troubleshooting

### Erreur MongoDB

```bash
# Vérifier que MongoDB tourne
docker ps | grep mongo
# Si non
docker start mongo
```

### Erreur Twilio 21617 (message trop long)

Les messages sont automatiquement découpés en parties de 1500 caractères max.

### Erreur "No module named..."

```bash
pip install -r requirements.txt
```

---

## 📄 Licence

Ce projet est sous licence MIT.

---

## 👥 Contributeurs

- **YONLI Fidèle** - Développeur principal

---

**🎉 Prêt à démarrer ? Suivez la section [Installation](#-installation) !**