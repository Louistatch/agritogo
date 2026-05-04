# AgriTogo — Guide d'utilisation

**Plateforme d'intelligence décisionnelle pour l'agriculture au Togo et en Afrique de l'Ouest.**

---

## Qu'est-ce qu'AgriTogo ?

AgriTogo est un outil d'aide à la décision agricole qui combine intelligence artificielle, modèles de machine learning et données de terrain pour répondre à une question simple : **que faire, quand, et pourquoi ?**

La plateforme s'adresse aux agriculteurs, coopératives, ONG, institutions de microfinance et décideurs publics opérant dans le contexte agricole togolais.

---

## Interface — Vue d'ensemble

L'interface est organisée en **5 onglets** accessibles depuis la barre de navigation en haut de page.

---

## Onglet 1 — Tableau de bord (Dashboard)

**Point d'entrée principal. Vue synthétique du marché en temps réel.**

### Ticker de prix
Une barre défilante en haut affiche les prix actuels des 12 produits agricoles avec leur variation en pourcentage par rapport à la période précédente.

- Vert = prix en hausse
- Rouge = prix en baisse
- Gris = stable

### Cartes métriques
Les 4 premières cultures affichent leur prix en FCFA/kg avec la tendance.

### Graphique de tendance des prix
Sélectionnez un produit et un marché dans les menus déroulants pour afficher l'historique des prix sur les 12 derniers mois.

### Graphiques à chargement différé
Trois graphiques se chargent automatiquement au démarrage (ou manuellement via le bouton ▶) :

| Graphique | Description |
|-----------|-------------|
| **30-Day Forecast** | Prévision de volatilité GARCH sur 30 jours pour le produit sélectionné |
| **Regional Heatmap** | Carte thermique des rendements par région du Togo |
| **Portfolio Risk** | Jauge de risque financier global du portefeuille agricole |

### Panneau Décision rapide
Posez une question directement depuis le tableau de bord. Le moteur multi-agents analyse et retourne une recommandation structurée en quelques secondes.

---

## Onglet 2 — Marchés (Markets)

**Consultation des prix historiques par produit et par marché.**

### Comment l'utiliser
1. Sélectionnez un produit dans la liste (Maïs, Riz, Sorgho, Mil, Haricot, Soja, Arachide, Igname, Manioc, Tomate, Piment, Oignon)
2. Sélectionnez un marché ou laissez "Tous les marchés"
3. Cliquez sur **Consulter**

### Marchés couverts
- Lomé-Adawlato
- Kara
- Sokodé
- Atakpamé
- Dapaong

Les données affichées couvrent les 20 dernières entrées disponibles avec date, prix en FCFA/kg et marché d'origine.

---

## Onglet 3 — Prévisions (Forecasts)

**Modèles quantitatifs de prédiction. Trois modules disponibles.**

### Module 1 — Prédiction de rendement par culture

Sélectionnez une culture parmi : Maïs, Riz, Sorgho, Soja, Manioc, Igname.

Le modèle retourne :
- Rendement moyen en tonnes/hectare
- Score R² des modèles Random Forest et XGBoost (précision du modèle)
- Importance des variables (température, pluviométrie, pesticides, engrais)
- Rendement par région du Togo
- Interprétation automatique par l'agent IA

> Un R² proche de 1.0 indique un modèle très précis. En dessous de 0.5, les prédictions sont indicatives.

### Module 2 — Volatilité GARCH

Sélectionnez un produit agricole. Le modèle GARCH(1,1) calcule :
- Prix actuel et volatilité historique
- Prévision de volatilité sur 30 jours
- Fourchette de prix probable (min/max) par jour
- Résumé de la situation de marché

> Utilisez ce module avant de vendre ou stocker pour évaluer le risque de fluctuation des prix.

### Module 3 — KPIs Agriculture

Tableau de bord des indicateurs clés nationaux :
- Surface cultivée totale (hectares)
- Rendement national moyen (kg/ha)
- Coût des intrants par hectare (FCFA)
- Top cultures par ROI (retour sur investissement)
- Rendement par région
- Score de risque climatique par région

Trois graphiques interactifs se chargent automatiquement : bulle ROI, radar des cultures, prévision GARCH.

---

## Onglet 4 — Risque (Risk)

**Évaluation du risque financier et segmentation des agriculteurs.**

### Module 1 — Risque financier

Analyse de 4 981 dossiers de crédit agricole. Le modèle Random Forest retourne :
- Précision globale et score F1 du modèle
- Taux de risque élevé/moyen/faible par région
- Taux de risque par taille d'entreprise (petite, moyenne, grande)
- Montant moyen des prêts par segment
- Facteurs de risque les plus déterminants
- Région la plus risquée et la plus sûre

> Utilisé par les institutions de microfinance pour calibrer leurs critères d'octroi de crédit.

### Module 2 — Segmentation des agriculteurs

Clustering K-Means + réduction dimensionnelle PCA sur 186 000+ profils d'agriculteurs. Le modèle identifie 4 segments :

| Segment | Profil |
|---------|--------|
| **Petits exploitants de subsistance** | Faible revenu, risque climatique élevé |
| **Commerciaux émergents** | Revenu intermédiaire, en croissance |
| **Producteurs intensifs** | Rendement élevé, coûts importants |
| **Grands diversifiés** | Forte marge, diversification des cultures |

Pour chaque segment : nombre d'agriculteurs, surface moyenne, revenu moyen, marge bénéficiaire, risque climatique, région dominante.

Un graphique 3D holographique visualise les clusters dans l'espace PCA.

---

## Onglet 5 — Analyste (Analyst)

**Interface principale d'interaction avec l'IA. Trois sous-panneaux.**

### Sous-panneau 1 — Chat Agent

Interface de conversation directe avec AgriTogo, l'agent IA spécialisé agriculture Togo.

**Deux modèles disponibles :**
- **Gemini** — Modèle Google Gemini 2.5 Flash avec rotation automatique de 3 clés API
- **Claude (illimité)** — Modèle Anthropic Claude via Puter.js, sans limite de quota

**Fonctionnalités du chat :**
- Historique de conversation persistant
- Indicateur de frappe animé pendant le traitement
- Bouton copier sur chaque réponse de l'agent
- Bouton effacer pour réinitialiser la conversation
- Bouton exporter pour sauvegarder l'historique

**Ce que vous pouvez demander :**
- Prix et tendances des marchés togolais
- Conseils de vente ou de stockage
- Analyse de risque pour un projet agricole
- Prévisions de rendement par culture et région
- Génération de formulaires KoboCollect
- Interprétation des résultats ML
- Recommandations agronomiques contextualisées

**Panneau de raisonnement (Agent Reasoning)**
Un panneau flottant en bas à droite affiche en temps réel les étapes de réflexion de l'agent : analyse, appel d'outils, résultats, décision finale.

### Sous-panneau 2 — Moteur de décision (Decision Engine)

Système multi-agents avec mécanisme de débat. Plus puissant que le chat simple.

**Sélectionnez votre profil :**
- Agriculteur
- Coopérative
- ONG
- Gouvernement

La réponse est adaptée au niveau de détail et au vocabulaire approprié à votre profil.

**Actions rapides pré-configurées :**
- Vendre maintenant ou attendre ?
- Optimiser le stockage
- Diversifier les cultures

**Mécanisme de débat (activé automatiquement pour les questions complexes) :**
1. Gemini propose une stratégie
2. Un agent quantitatif critique avec des données chiffrées
3. L'agent coordinateur arbitre et produit la décision finale

Le résultat affiche : type d'agent mobilisé, modèle utilisé, si un débat a eu lieu, et la recommandation finale structurée.

### Sous-panneau 3 — Mémoire des décisions (Decision Memory)

Historique des analyses effectuées avec possibilité d'ajouter un retour terrain :
- Résultat réel observé (bon/mauvais/neutre)
- Prix réel constaté après la décision

Ce feedback améliore la pertinence des analyses futures.

---

## Administration (/admin)

Accessible via le lien **Admin** en haut à droite. Réservé aux gestionnaires de la plateforme.

### Onglet ML Modules & Data
Gestion des fichiers de données pour chaque module ML. Indicateurs de disponibilité (vert = présent, rouge = manquant). Upload de nouveaux datasets. Téléchargement des formulaires XLSForm pour KoboCollect.

### Onglet KoboCollect
- Configuration de la connexion à votre compte KoboToolbox (URL + token API)
- Visualisation des formulaires déployés
- Téléchargement des 5 templates XLSForm prêts à l'emploi :
  - Enquête prix marché (15 champs)
  - Enquête rendement cultures (15 champs)
  - Évaluation risque financier (15 champs)
  - Profil agriculteur (12 champs)
  - Collecte prix simplifiée (8 champs)
- Statut des APIs d'enrichissement automatique (Open-Meteo, SoilGrids, WFP VAM)

### Onglet Database
- Import de données prix au format CSV (colonnes : date, produit, marche, prix)
- Import de produits au format CSV (colonnes : nom, unite, categorie)
- Ajout manuel de produits
- Consultation paginée de toutes les entrées de prix
- Export complet en CSV

---

## Langue

Basculez entre **FR** (français) et **EN** (anglais) via les boutons en haut à droite. L'interface et les réponses de l'agent s'adaptent immédiatement.

---

## Produits couverts

Maïs · Riz local · Sorgho · Mil · Haricot · Soja · Arachide · Igname · Manioc · Tomate · Piment · Oignon

## Régions couvertes

Maritime · Plateaux · Centrale · Kara · Savanes

## Marchés couverts

Lomé-Adawlato · Kara · Sokodé · Atakpamé · Dapaong

---

## API REST

Pour les intégrations B2B, une API REST est disponible à l'adresse `/api/v1`.

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/api/v1/health` | GET | Statut du système |
| `/api/v1/prix/<produit>` | GET | Prix historiques par produit |
| `/api/v1/forecast` | POST | Prévision de volatilité GARCH |
| `/api/v1/risk` | POST | Évaluation du risque financier |
| `/api/v1/segmentation` | POST | Segmentation des agriculteurs |
| `/api/v1/kpi` | GET | KPIs agriculture nationaux |

---

*AgriTogo — Decision Intelligence Engine v2.0 · Togo & Afrique de l'Ouest*
