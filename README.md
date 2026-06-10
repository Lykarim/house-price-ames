# Laplace Immo — Prédiction des Prix Immobiliers

Projet Data Science — prédiction du prix de vente de maisons individuelles sur le dataset **Ames Housing** (Iowa, USA, 1 460 observations × 81 variables).

[![CI](https://github.com/Lykarim/house-price-ames/actions/workflows/ci.yml/badge.svg)](https://github.com/Lykarim/house-price-ames/actions/workflows/ci.yml)
[![API](https://img.shields.io/badge/API-Railway-live-green)](https://clever-harmony-production-ced2.up.railway.app/docs)

---

## Résultats

| Métrique | Valeur |
|----------|--------|
| RMSE (test) | **26 338 $** |
| MAE (test) | 17 058 $ |
| R² (test) | **0.891** |
| RMSE CV (5-fold) | 26 418 $ |

Modèle final : **LightGBM** avec prétraitement avancé (TargetEncoder, interactions de features, Yeo-Johnson).

---

## Structure du projet

```
house_price/
├── .github/workflows/ci.yml              # CI/CD : 3 jobs (tests → pipeline → API+Docker)
├── notebooks/
│   ├── house_price_01_analyse.ipynb      # EDA & analyse exploratoire
│   ├── house_price_02_modeling.ipynb     # Benchmark 20+ modèles (54 runs MLFlow)
│   ├── house_price_03_optimization.ipynb # Optuna 60 trials/modèle
│   └── house_price_04_preprocessing.ipynb# 6 axes de prétraitement comparés
├── src/
│   ├── make_dataset.py                   # Chargement & feature engineering temporel
│   ├── trainer.py                        # Classe Trainer (pipeline sklearn)
│   ├── train_pipeline.py                 # Script DVC — entraînement reproductible
│   ├── api.py                            # API REST FastAPI (predict + batch)
│   └── monitoring.py                     # Détection de drift (Evidently + KS-test)
├── settings/params.py                    # Paramètres centralisés
├── tests/
│   ├── test_make_dataset.py              # 5 tests unitaires
│   ├── test_trainer.py                   # 6 tests unitaires
│   └── test_api.py                       # 9 tests d'intégration FastAPI
├── reports/                              # Graphiques (benchmark, résidus, features)
├── models/                               # Modèles sérialisés (.dill)
├── Dockerfile                            # Image Python 3.11-slim + uvicorn
├── docker-compose.yml                    # Orchestration locale (port 8000)
├── dvc.yaml                              # Pipeline DVC (load_data → train)
├── metrics.json                          # Métriques finales (RMSE, MAE, R²)
└── requirements.txt
```

---

## Démarche

### 1. EDA (`notebook 01`)
- Analyse des valeurs manquantes, distributions et corrélations
- Rapport automatique avec `ydata-profiling`
- Identification des variables à fort pouvoir prédictif via **PPS**

### 2. Benchmark de modèles (`notebook 02`)
54 runs MLFlow comparant 20+ algorithmes sur deux espaces cibles (cible brute vs `log1p`) :

| Famille | Modèles |
|---------|---------|
| Linéaires | Ridge, Lasso, ElasticNet, BayesianRidge, Huber |
| Arbres | DecisionTree, ExtraTrees, RandomForest, GradBoost, HistGradBoost |
| Boosting | XGBoost, LightGBM, CatBoost, AdaBoost |
| Autres | SVR, KNN, MLP |
| Ensembles | VotingRegressor, StackingRegressor |

**Découverte clé** : `log1p(saleprice)` améliore SVR de **54 000 $** et XGBoost de **6 700 $**.

### 3. Optimisation Optuna (`notebook 03`)
- 60 trials par modèle avec pruning Median
- Nested runs MLFlow (chaque trial = run enfant)
- 5 modèles optimisés : LightGBM, XGBoost, CatBoost, SVR, HistGradBoost

### 4. Ingénierie des prétraitements (`notebook 04`)
6 axes évalués par CV 5-fold :

| Axe | Gain RMSE |
|-----|-----------|
| Imputation sémantique | +129 $ |
| Winsorizing (outliers P1/P99) | +102 $ |
| Yeo-Johnson | +101 $ |
| OrdinalEncoder (variables ordonnées) | +101 $ |
| **TargetEncoder (haute cardinalité)** | **+556 $** |
| **Feature interactions** | **+949 $** |

Pipeline final : CV-RMSE **26 418 $** (+1 237 $ vs baseline).

---

## Installation

```bash
git clone https://github.com/Lykarim/house-price-ames.git
cd house-price-ames
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Reproduire le pipeline

```bash
python src/train_pipeline.py
```

## Lancer les tests (20 tests)

```bash
pytest tests/ -v
```

## API REST

```bash
# Démarrage local
uvicorn src.api:app --reload --port 8000
# Swagger UI → http://127.0.0.1:8000/docs

# Via Docker
docker compose up
```

**Endpoints** :

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/health` | Statut + modèle chargé |
| GET | `/model-info` | Métriques du modèle |
| POST | `/predict` | Prédiction d'une maison |
| POST | `/predict/batch` | Batch jusqu'à 100 maisons |

**Exemple** :
```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"garagecars":2,"fullbath":2,"building_age":5.0,"grlivarea":1710.0,
       "garagearea":548.0,"totrmsabvgrd":8,"remodel_age":5.0,"garage_age":5.0,
       "fireplaces":1,"totalbsmtsf":856.0,"overallqual":"7","neighborhood":"CollgCr",
       "exterqual":"Gd","bsmtqual":"Gd","kitchenqual":"Gd","alley":"NoAlley",
       "garagefinish":"RFn","foundation":"PConc","mssubclass":"60","garagetype":"Attchd",
       "heatingqc":"Ex","exterior1st":"VinylSd","bsmtfintype1":"GLQ",
       "exterior2nd":"VinylSd","masvnrtype":"BrkFace","mszoning":"RL"}'
# → {"predicted_price": 214758.50, "currency": "USD", ...}
```

## Monitoring de drift

```bash
python src/monitoring.py
# Rapport HTML → reports/monitoring_drift_report.html
```

## MLFlow

```bash
cd notebooks && mlflow ui --port 5001
# → http://127.0.0.1:5001  (528 runs, 4 expériences)
```

---

## CI/CD — 4 jobs séquentiels

```
push → tests unitaires (11 tests)
          → pipeline DVC (entraînement + metrics.json)
               → tests API (9 tests) + docker build
                    → déploiement Railway (main uniquement)
```

**API déployée :** https://clever-harmony-production-ced2.up.railway.app/docs

---

## Stack technique

| Catégorie | Outils |
|-----------|--------|
| ML | scikit-learn, XGBoost, LightGBM, CatBoost |
| Optimisation | Optuna (60 trials, pruning bayésien) |
| MLOps | MLFlow (528 runs), DVC (pipeline reproductible) |
| API | FastAPI, Pydantic, uvicorn |
| Monitoring | Evidently, scipy (KS-test) |
| Containerisation | Docker, docker-compose |
| Feature selection | ppscore |
| Encodage | category-encoders (TargetEncoder) |
| Sérialisation | dill |
| Tests | pytest (20 tests) |
| CI/CD | GitHub Actions (4 jobs) + Railway |
