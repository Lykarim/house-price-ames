# Documentation complète — Laplace Immo

## Présentation du projet

**Objectif** : prédire le prix de vente de maisons individuelles à partir de leurs caractéristiques physiques et contractuelles.

**Dataset** : Ames Housing (Iowa, USA) — 1 460 observations, 81 variables (surface habitable, qualité générale, type de garage, année de construction, etc.). Chargé automatiquement via OpenML (`fetch_openml`), sans téléchargement manuel.

**Résultat final** : RMSE = **26 338 $** sur le jeu de test, R² = **0.891** — le modèle explique 89 % de la variance des prix.

---

## Structure du projet

```
house_price/
├── .github/
│   └── workflows/
│       └── ci.yml                   # Pipeline CI/CD : 3 jobs automatiques
├── notebooks/
│   ├── house_price_01_analyse.ipynb # Analyse exploratoire (EDA)
│   ├── house_price_02_modeling.ipynb# Benchmark 20+ modèles + MLFlow
│   ├── house_price_03_optimization.ipynb # Optuna + ensembles
│   └── house_price_04_preprocessing.ipynb# Comparaison 6 stratégies preprocessing
├── src/
│   ├── make_dataset.py              # Chargement + feature engineering temporel
│   ├── trainer.py                   # Classe Trainer (pipeline sklearn)
│   ├── train_pipeline.py            # Script DVC d'entraînement
│   ├── api.py                       # API REST FastAPI (endpoints predict)
│   └── monitoring.py                # Détection de drift (Evidently + KS-test)
├── settings/
│   └── params.py                    # Paramètres centralisés (seed, features, etc.)
├── tests/
│   ├── test_make_dataset.py         # 5 tests unitaires make_dataset
│   ├── test_trainer.py              # 6 tests unitaires Trainer
│   └── test_api.py                  # 9 tests intégration FastAPI
├── models/
│   ├── 20260523_model_house_price.dill
│   ├── 20260608_model_house_price.dill   # Modèle standard sklearn (Ridge)
│   └── 20260608_model_optimized_preprocessing.dill # LightGBM optimisé
├── reports/
│   ├── benchmark_top25.png
│   ├── feature_importances_best.png
│   ├── mlflow_benchmark_table.png
│   ├── mlflow_model_comparison.png
│   ├── mlflow_optuna_lgbm.png
│   ├── optimization_comparison.png
│   ├── preprocessing_comparison.png
│   └── residuals_best.png
├── data/
│   └── output/
│       └── house_prices.parquet     # Données nettoyées (produit DVC)
├── Dockerfile                       # Image Docker Python 3.11-slim
├── docker-compose.yml               # Orchestration locale (port 8000)
├── dvc.yaml                         # Pipeline reproductible DVC
├── metrics.json                     # Métriques finales (lu par DVC)
├── requirements.txt                 # Toutes les dépendances Python
└── docs/
    └── PROJET.md                    # Ce fichier
```

---

## Notebooks — déroulement de la démarche

### Notebook 01 — Analyse exploratoire (`house_price_01_analyse.ipynb`)

**Objectif** : comprendre les données avant de modéliser.

**Ce qui a été fait** :

- **Valeurs manquantes** : visualisation avec `missingno`. Certaines variables comme `PoolQC`, `Alley`, `Fence` ont plus de 80 % de valeurs manquantes — ces absences ont une signification métier (absence de piscine, pas d'allée), pas une erreur de collecte.
- **Variable cible `saleprice`** : distribution fortement asymétrique à droite (quelques maisons très chères tirent la moyenne vers le haut). Cette observation motive la **log-transformation** utilisée dans les notebooks suivants.
- **Variables catégorielles** : analyse des fréquences et boxplots par rapport à `saleprice`. On observe par exemple que `OverallQual` (qualité générale 1-10) est très discriminante.
- **Variables numériques** : distributions univariées (histogrammes) et bivariées (scatter plots vs `saleprice`). `GrLivArea` (surface habitable) est la variable la plus linéairement corrélée au prix.
- **Matrice de corrélation** : identification des variables redondantes et des variables à fort lien avec la cible.
- **Rapport de profiling** : `ydata-profiling` génère automatiquement un rapport HTML complet (`reports/house_price_profiling.html`) avec statistiques, alertes d'interactions, et détection de variables quasi-constantes.

**Motivation** : l'EDA (Exploratory Data Analysis) est indispensable avant la modélisation pour éviter de traiter de façon mécanique des données qu'on ne comprend pas. Elle révèle les transformations nécessaires et les features les plus informatives.

---

### Notebook 02 — Benchmark de modèles (`house_price_02_modeling.ipynb`)

**Objectif** : comparer systématiquement 20+ algorithmes pour identifier les meilleures approches.

**Sélection des features via PPS (Predictive Power Score)**

Le PPS mesure la capacité prédictive d'une variable X vers une variable Y, en tenant compte des relations non linéaires (contrairement à la corrélation de Pearson qui ne détecte que les relations linéaires). Seules les features avec un score ≥ 0.05 sont conservées.

**Double version de la cible**
Chaque modèle est testé deux fois :
- `y_raw` : `saleprice` brut
- `y_log` : `log1p(saleprice)` — transformation logarithmique pour normaliser la distribution

**Résultat clé** : la log-transformation améliore massivement certains modèles :
- SVR (noyau RBF) : gain de **54 000 $** de RMSE
- XGBoost : gain de **6 700 $** de RMSE

**Modèles testés** :

| Famille | Algorithmes |
|---------|------------|
| Baseline | DummyRegressor (moyenne) |
| Linéaires | Ridge, Lasso, ElasticNet, BayesianRidge, HuberRegressor |
| Arbres | DecisionTree, ExtraTrees, RandomForest |
| Gradient Boosting | GradientBoosting, HistGradientBoosting, AdaBoost |
| Boosting avancé | XGBoost, LightGBM, CatBoost |
| Autres | SVR (RBF), KNN, MLP (réseau de neurones) |
| Ensembles | VotingRegressor, StackingRegressor |

**Comparaison des scalers** : RobustScaler vs StandardScaler vs MinMaxScaler. Le RobustScaler (utilise médiane et IQR au lieu de moyenne/écart-type) est plus robuste aux outliers — important sur des données immobilières où quelques maisons très chères faussent la normalisation.

**54 runs MLFlow** loggués automatiquement pour traçabilité complète.

**Meilleur résultat** : SVR RBF avec log-transform, RMSE ≈ 28 600 $.

**Motivation** : tester un seul modèle est une erreur méthodologique. Seul un benchmark exhaustif permet de justifier le choix final de l'algorithme avec des données empiriques.

---

### Notebook 03 — Optimisation des hyperparamètres (`house_price_03_optimization.ipynb`)

**Objectif** : pousser les performances des meilleurs modèles en cherchant leurs hyperparamètres optimaux.

**Optuna** — framework d'optimisation bayésienne des hyperparamètres. Contrairement à une GridSearch qui teste toutes les combinaisons de façon exhaustive, Optuna apprend des essais précédents pour diriger la recherche vers les zones prometteuses de l'espace des hyperparamètres.

- **60 trials** par modèle avec pruning (arrêt anticipé des essais non prometteurs)
- **5 modèles optimisés** : LightGBM, XGBoost, CatBoost, SVR, HistGradientBoosting
- **Nested runs MLFlow** : chaque trial Optuna est un run enfant dans l'expérience du modèle parent

**Exemple d'espace de recherche pour LightGBM** :

| Hyperparamètre | Plage | Description |
|----------------|-------|-------------|
| `n_estimators` | 200–1200 | Nombre d'arbres |
| `learning_rate` | 0.005–0.3 (log) | Taux d'apprentissage |
| `max_depth` | 3–10 | Profondeur maximale des arbres |
| `num_leaves` | 20–150 | Nombre de feuilles par arbre |
| `min_child_samples` | 5–50 | Nombre min d'échantillons par feuille |
| `subsample` | 0.5–1.0 | Fraction de données par arbre |
| `colsample_bytree` | 0.5–1.0 | Fraction de features par arbre |
| `reg_alpha` | 1e-8–1.0 | Régularisation L1 |
| `reg_lambda` | 1e-8–1.0 | Régularisation L2 |

**Ensembles** :
- `VotingRegressor` : moyenne pondérée des prédictions des meilleurs modèles
- `StackingRegressor` : un méta-modèle (Ridge) apprend à combiner les prédictions des modèles de base

**Analyse du meilleur modèle** :
- Feature importances (gain d'information LightGBM) : `OverallQual`, `GrLivArea`, `TotalBsmtSF` sont les variables les plus importantes
- Analyse des résidus : vérification que les erreurs sont bien distribuées autour de zéro sans pattern systématique

**Modèle sauvegardé** avec `dill` (sérialisation du pipeline sklearn complet, préprocesseur inclus).

**Motivation** : les hyperparamètres par défaut sont rarement optimaux. Optuna permet une exploration intelligente en 10× moins de temps qu'une GridSearch exhaustive.

---

### Notebook 04 — Ingénierie des prétraitements (`house_price_04_preprocessing.ipynb`)

**Objectif** : aller au-delà du prétraitement de base pour extraire plus d'information des données.

**6 axes évalués par validation croisée 5-fold** (CV-RMSE = métrique objective, indépendante du jeu de test) :

| Axe | Description | Gain RMSE |
|-----|-------------|-----------|
| **Baseline** | Imputation médiane + OneHotEncoder | référence |
| Axe 1 | Imputation sémantique (NaN = "absent" pour PoolQC, etc.) | +129 $ |
| Axe 2 | Winsorizing — écrêtage des outliers à P1/P99 | +102 $ |
| Axe 3 | Yeo-Johnson — correction d'asymétrie des variables numériques | +101 $ |
| Axe 4 | OrdinalEncoder pour variables de qualité (Ex > Gd > TA > Fa > Po) | +101 $ |
| **Axe 5** | **TargetEncoder pour variables haute cardinalité (Neighborhood, etc.)** | **+556 $** |
| **Axe 6** | **Feature interactions : `qual_x_surface`, `total_sf`, `bath_score`** | **+949 $** |

**Pipeline combiné final** : CV-RMSE **26 418 $** — gain de **+1 237 $** par rapport au baseline.

**Détail des motivations** :

- *Imputation sémantique* : pour `PoolQC`, une valeur manquante signifie "pas de piscine", pas une donnée inconnue. Imputer par "absent" est plus fidèle à la réalité qu'imputer par la valeur la plus fréquente.
- *Winsorizing* : les outliers (maisons à 750k$ dans un dataset médian à 180k$) perturbent l'apprentissage. Les écrêter à P99 limite leur influence sans les supprimer.
- *Yeo-Johnson* : les variables numériques comme `LotArea` ou `GrLivArea` sont très asymétriques. Les normaliser aide les modèles linéaires et le SVR.
- *OrdinalEncoder* : `OverallQual` = "Excellent" > "Good" > "Average" a un ordre naturel. L'encoder numériquement (5 > 4 > 3) est plus informative qu'un OneHotEncoding.
- *TargetEncoder* : `Neighborhood` a 25 modalités. OneHotEncoding crée 25 colonnes sparse. TargetEncoder remplace chaque modalité par la moyenne de `saleprice` dans ce quartier — une information directement pertinente.
- *Feature interactions* : `qual_x_surface = OverallQual × GrLivArea` capture le fait qu'une grande maison de mauvaise qualité peut valoir moins qu'une petite maison de très bonne qualité.

---

## Code source

### `src/make_dataset.py` — Chargement des données

Fonction unique `load_data()` qui :
1. Valide que le nom du dataset n'est pas vide (sinon `ValueError`)
2. Charge les données depuis OpenML via `fetch_openml`
3. Met les colonnes en minuscules si demandé
4. Ajoute 3 features temporelles calculées :
   - `building_age` = année de vente − année de construction
   - `remodel_age` = année de vente − année de la dernière rénovation
   - `garage_age` = année de vente − année de construction du garage

**Motivation** : centraliser le chargement dans une fonction testable évite la duplication de code entre les notebooks et le pipeline de production. Les features temporelles captent la dépréciation des biens.

---

### `src/trainer.py` — Classe `Trainer`

Abstraction du pipeline d'entraînement sklearn. Reçoit un estimateur quelconque + des transformeurs + les données, et gère automatiquement :

- Détection des colonnes numériques vs catégorielles
- Construction d'un `ColumnTransformer` (préprocesseur séparé par type de variable)
- Assemblage du `Pipeline` (préprocesseur → estimateur)
- Split train/test
- Calcul des métriques (RMSE, MAE, R²)

**Méthodes** :

| Méthode | Description |
|---------|-------------|
| `define_pipeline()` | Construit le pipeline sklearn sans entraîner |
| `fit()` | Entraîne le pipeline sur le train set |
| `train()` | `fit()` + retourne `(pipeline, métriques_train, métriques_test)` |
| `predict(X)` | Prédit sur de nouvelles données |
| `score(X, y)` | Retourne le R² sur le jeu fourni |

**Motivation** : éviter de réécrire le même code sklearn à chaque notebook. Un seul appel `Trainer(...).train()` remplace 30 lignes de boilerplate.

---

### `src/train_pipeline.py` — Script DVC

Script autonome exécuté par DVC (`dvc repro` ou directement `python src/train_pipeline.py`). Reproduit l'entraînement de bout en bout :

1. Charge les données avec `load_data()`
2. Sauvegarde les données en Parquet (`data/output/house_prices.parquet`)
3. Sélectionne les features via PPS
4. Entraîne un pipeline Ridge avec `Trainer`
5. Calcule les métriques et les log dans MLFlow
6. Sauvegarde le modèle avec `dill` (`models/YYYYMMDD_model_house_price.dill`)
7. Écrit `metrics.json` (lu par DVC pour le suivi des métriques)

**Format `metrics.json`** :
```json
{
  "rmse_train": 18423.12,
  "rmse_test": 26337.89,
  "mae_test": 17058.34,
  "r2_test": 0.891
}
```

**Motivation** : séparer l'expérimentation (notebooks) de la reproductibilité (script). DVC peut comparer les métriques entre deux runs et détecter si un changement de code dégrade le modèle.

---

### `src/api.py` — API REST FastAPI

API de prédiction exposée via **FastAPI**, accessible via Swagger UI à `/docs`.

#### Chargement du modèle

```python
def _load_model():
    # Priorité aux modèles standard sklearn (sans transformers custom des notebooks)
    standard_models = sorted(MODEL_DIR.glob("*model_house_price*.dill"))
    all_models = sorted(MODEL_DIR.glob("*.dill"))
    candidates = standard_models if standard_models else all_models
    latest = candidates[-1]
    with open(latest, "rb") as f:
        pipeline = dill.load(f)
    log_scale = "optimized" in latest.name
    return pipeline, latest.name, log_scale
```

Le modèle est chargé **au niveau module** (au démarrage), pas dans chaque requête. La priorité est donnée aux modèles `*model_house_price*.dill` (pipeline sklearn standard, sans transformeurs personnalisés définis dans les notebooks Jupyter) pour garantir la compatibilité en contexte API et tests.

#### Prédiction manuelle step-by-step

```python
def _predict_price(df: pd.DataFrame) -> list[float]:
    Xt = df.copy()
    for _, _, step in _pipeline._iter(with_final=False):
        Xt = step.transform(Xt)
    raw = _pipeline.steps[-1][1].predict(Xt)
    if _log_scale:
        raw = np.expm1(raw)
    return [round(float(p), 2) for p in raw]
```

Cette approche contourne l'incompatibilité du wrapper `set_output` de sklearn avec les transformeurs custom définis dans les notebooks (`SemanticImputer`, `OutlierClipper`, `FeatureEngineer` avec `__module__ = "__main__"`), qui échouent lorsqu'on appelle `pipeline.predict()` directement via FastAPI TestClient.

#### Schéma Pydantic — 26 features

**Features numériques (10)** :

| Feature | Type | Défaut | Description |
|---------|------|--------|-------------|
| `garagecars` | int (0–5) | 2 | Capacité garage (nb de voitures) |
| `fullbath` | int (0–5) | 2 | Salles de bain complètes |
| `building_age` | float | 20.0 | Âge du bâtiment (yrsold − yearbuilt) |
| `garagearea` | float ≥0 | 500.0 | Surface du garage (sq ft) |
| `totrmsabvgrd` | int (1–20) | 8 | Total pièces au-dessus du sol |
| `remodel_age` | float | 20.0 | Années depuis dernière rénovation |
| `garage_age` | float | 20.0 | Âge du garage (yrsold − garageyrblt) |
| `grlivarea` | float ≥0 | 1500.0 | Surface habitable au-dessus du sol (sq ft) |
| `fireplaces` | int (0–4) | 1 | Nombre de cheminées |
| `totalbsmtsf` | float ≥0 | 800.0 | Surface totale du sous-sol (sq ft) |

**Features catégorielles (16)** :

| Feature | Défaut | Valeurs possibles |
|---------|--------|------------------|
| `overallqual` | "7" | "1" à "10" (qualité générale) |
| `neighborhood` | "CollgCr" | CollgCr, OldTown, Edwards, Somerst, ... |
| `exterqual` | "Gd" | Ex / Gd / TA / Fa / Po |
| `bsmtqual` | "Gd" | Ex / Gd / TA / Fa / Po / NoBsmt |
| `kitchenqual` | "Gd" | Ex / Gd / TA / Fa / Po |
| `alley` | "NoAlley" | Grvl / Pave / NoAlley |
| `garagefinish` | "RFn" | Fin / RFn / Unf / NoGarage |
| `foundation` | "PConc" | BrkTil / CBlock / PConc / Slab / Stone / Wood |
| `mssubclass` | "60" | 20 / 60 / 120 / ... (type logement) |
| `garagetype` | "Attchd" | Attchd / Detchd / BuiltIn / CarPort / NA |
| `heatingqc` | "Ex" | Ex / Gd / TA / Fa / Po |
| `exterior1st` | "VinylSd" | VinylSd / HdBoard / MetalSd / ... |
| `bsmtfintype1` | "GLQ" | GLQ / ALQ / BLQ / Rec / LwQ / Unf / NoBsmt |
| `exterior2nd` | "VinylSd" | VinylSd / HdBoard / MetalSd / ... |
| `masvnrtype` | "BrkFace" | BrkCmn / BrkFace / CBlock / None / Stone |
| `mszoning` | "RL" | RL / RM / C(all) / FV / RH |

#### Endpoints

| Méthode | Route | Description | Code succès |
|---------|-------|-------------|-------------|
| GET | `/` | Bienvenue + liens | 200 |
| GET | `/health` | Statut API + modèle chargé | 200 |
| GET | `/model-info` | Métriques + info modèle | 200 |
| POST | `/predict` | Prédiction d'une maison | 200 |
| POST | `/predict/batch` | Prédiction en batch (max 100) | 200 |
| GET | `/docs` | Swagger UI interactif | 200 |
| GET | `/redoc` | Documentation ReDoc | 200 |

**Exemple de réponse `/predict`** :
```json
{
  "predicted_price": 214758.50,
  "currency": "USD",
  "model_used": "20260608_model_house_price.dill"
}
```

**Exemple de réponse `/predict/batch`** :
```json
{
  "predictions": [214758.50, 189320.00],
  "count": 2,
  "currency": "USD",
  "model_used": "20260608_model_house_price.dill"
}
```

---

### `src/monitoring.py` — Monitoring & Détection de drift

Module de surveillance des données en production, basé sur **Evidently** (rapport HTML complet) avec fallback **KS-test scipy** pour une détection légère.

#### Fonctions principales

**`load_reference_data()`** — Charge les données de référence depuis `data/output/house_prices.parquet`. Ces données correspondent à la distribution des données d'entraînement, utilisée comme baseline.

**`simulate_current_data(reference, drift_fraction=0.3)`** — Simule un jeu de données en production avec drift artificiel sur 30% des features numériques (multiplication par un facteur aléatoire entre 1.2 et 1.5). En production réelle, remplacer par les données reçues via l'API.

**`run_evidently_report(reference, current)`** — Génère un rapport HTML complet avec :
- `DataDriftPreset` : détecte les changements de distribution pour chaque feature
- `DataQualityPreset` : vérifie la qualité des données (valeurs manquantes, outliers, etc.)
- `TargetDriftPreset` : surveille le drift de la variable cible `saleprice`

Sauvegarde dans `reports/monitoring_drift_report.html`.

**`run_basic_drift_report(reference, current)`** — Détection rapide via test de Kolmogorov-Smirnov (KS) pour chaque feature numérique :
```python
stat, p_value = stats.ks_2samp(ref_vals, cur_vals)
drift_detected = p_value < 0.05
```

Retourne un dict avec statistiques par feature (KS stat, p-value, moyennes ref/current, drift détecté).

**Features surveillées** :

| Type | Features |
|------|---------|
| Numériques | bsmtfinsf1, bsmtunfsf, garagecars, lotarea, masvnrarea, totalbsmtsf, building_age, remodel_age |
| Catégorielles | overallqual, mssubclass, condition2, exterqual, foundation, garagetype, heating, heatingqc, housestyle, masvnrtype, miscfeature, saletype, street |

---

### `settings/params.py` — Paramètres centralisés

Contient toutes les constantes partagées :

| Constante | Valeur | Usage |
|-----------|--------|-------|
| `SEED` | 43 | Reproductibilité (train/test split, modèles) |
| `TARGET` | "saleprice" | Variable cible |
| `TEST_SIZE` | 0.2 | 20% des données pour le test set |
| `MODEL_NAME` | "model_house_price" | Préfixe du nom de fichier modèle |
| `MODEL_PARAMS["FEATURES"]` | Liste 21 features | Features par défaut (fallback si PPS non disponible) |

**Motivation** : un seul fichier à modifier pour changer un paramètre global. Évite les "magic numbers" éparpillés dans le code.

---

## Tests unitaires

**20 tests** répartis en 3 fichiers, exécutés automatiquement à chaque push.

### `tests/test_make_dataset.py` (5 tests)

| Test | Ce qu'il vérifie |
|------|-----------------|
| `test_load_data_returns_dataframe` | Retourne bien un `pd.DataFrame` |
| `test_load_data_lowercase_columns` | Colonnes en minuscules si `columns_to_lower=True` |
| `test_load_data_feature_engineering` | Colonnes `building_age`, `remodel_age`, `garage_age` présentes |
| `test_load_data_raises_on_empty_name` | `ValueError` levée si `dataset_name=""` |
| `test_load_data_raises_on_none_name` | `ValueError` levée si `dataset_name=None` |

Les tests utilisent `unittest.mock.patch` pour simuler `fetch_openml` sans appel réseau.

### `tests/test_trainer.py` (6 tests)

| Test | Ce qu'il vérifie |
|------|-----------------|
| `test_define_pipeline_returns_pipeline` | `define_pipeline()` retourne un `Pipeline` sklearn |
| `test_fit_splits_data` | Après `fit()`, `X_train` et `X_test` sont non nuls |
| `test_train_returns_metrics` | `train()` retourne un dict avec `rmse`, `mae`, `r2` |
| `test_predict_returns_correct_shape` | `predict()` retourne un tableau de la bonne longueur |
| `test_train_test_size_respected` | Taille du test set correspond au `test_size` configuré |
| `test_score_returns_float` | `score()` retourne un flottant (le R²) |

### `tests/test_api.py` (9 tests d'intégration)

Ces tests utilisent `fastapi.testclient.TestClient` avec un fixture `scope="module"` — le modèle est chargé une seule fois pour toute la suite de tests.

| Test | Ce qu'il vérifie |
|------|-----------------|
| `test_root` | GET `/` renvoie 200 avec clé `docs` |
| `test_health` | GET `/health` : status `ok`, `model_loaded=True` |
| `test_model_info` | GET `/model-info` : contient `model` et `metrics` |
| `test_predict_returns_positive_price` | POST `/predict` : prix > 0, devise USD |
| `test_predict_high_quality_house_costs_more` | Maison qualité 9 > qualité 3 (sanity check métier) |
| `test_predict_batch` | POST `/predict/batch` avec 2 maisons : count=2, tous prix > 0 |
| `test_predict_batch_single_house` | Batch avec 1 maison : count=1 |
| `test_docs_available` | GET `/docs` : Swagger UI accessible (200) |
| `test_openapi_schema` | GET `/openapi.json` : schéma présent avec `/predict` et `/predict/batch` |

**Motivation** : les tests d'intégration vérifient le comportement end-to-end, pas seulement les fonctions isolées. Un test de "sanity check" (maison chère > maison pas chère) détecte les régressions logiques que les tests unitaires ne voient pas.

---

## MLOps

### MLFlow — Tracking des expériences

MLFlow enregistre automatiquement pour chaque run :
- Les **hyperparamètres** (`alpha`, `n_estimators`, `learning_rate`, etc.)
- Les **métriques** (RMSE, MAE, R²)
- Les **artefacts** (graphiques, modèles)

**528 runs** enregistrés dans 4 expériences :
1. Benchmark initial (54 runs, notebook 02)
2. Optimisation LightGBM (60 trials Optuna)
3. Optimisation XGBoost (60 trials Optuna)
4. Pipeline DVC (runs de reproductibilité)

L'interface graphique (`mlflow ui --port 5001` depuis le dossier `notebooks/`) permet de :
- Comparer visuellement tous les runs
- Filtrer par métrique pour trouver le meilleur modèle
- Visualiser l'évolution des métriques pendant l'optimisation Optuna

Les runs Optuna utilisent des **nested runs** : chaque trial est un run enfant dans le run parent du modèle.

**Motivation** : sans tracking, on perd les résultats des expériences passées. MLFlow est l'équivalent d'un cahier de laboratoire structuré et automatique.

---

### DVC — Versionnage du pipeline

DVC (Data Version Control) fonctionne comme git mais pour les fichiers lourds (données, modèles) et les pipelines.

Le fichier `dvc.yaml` définit deux étapes :

```yaml
stages:
  load_data:
    cmd: python src/make_dataset.py
    deps: [src/make_dataset.py, settings/params.py]
    outs: [data/output/house_prices.parquet]

  train:
    cmd: python src/train_pipeline.py
    deps: [src/train_pipeline.py, src/trainer.py, data/output/house_prices.parquet]
    outs: [models/]
    metrics: [metrics.json]
```

DVC :
- Détecte automatiquement si les dépendances ont changé et ne ré-exécute que ce qui est nécessaire
- Permet de comparer `metrics.json` entre deux branches git (`dvc metrics diff`)
- Assure la reproductibilité : en clonant le repo et en exécutant `dvc repro`, on obtient exactement le même modèle

---

### Docker — Containerisation

#### `Dockerfile`

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y gcc g++ libgomp1 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir dill numpy pandas scikit-learn lightgbm fastapi uvicorn httpx

COPY src/ ./src/
COPY settings/ ./settings/
COPY models/ ./models/
COPY metrics.json .

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

**Choix techniques** :
- `python:3.11-slim` : image légère (pas de Jupyter, pas de dev tools)
- `gcc g++ libgomp1` : compilateurs requis par LightGBM pour le build natif
- `--workers 2` : deux workers uvicorn pour la parallélisation des requêtes

#### `docker-compose.yml`

```yaml
services:
  api:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./models:/app/models:ro
      - ./metrics.json:/app/metrics.json:ro
    restart: unless-stopped
```

Les volumes en `:ro` (read-only) permettent de mettre à jour le modèle sans reconstruire l'image Docker.

---

## CI/CD — GitHub Actions (3 jobs)

Le fichier `.github/workflows/ci.yml` déclenche automatiquement à chaque `git push` trois jobs séquentiels :

```
push
 └── tests (unitaires)
      └── dvc-pipeline (entraînement)
           └── api-tests (API + Docker)
```

### Job 1 — Tests unitaires

```bash
pytest tests/ -v --tb=short --ignore=tests/test_api.py
```

Lance les 11 tests unitaires (`test_make_dataset.py` + `test_trainer.py`). Les tests API sont ignorés ici car ils nécessitent un modèle entraîné.

Si un test échoue → les jobs 2 et 3 ne démarrent pas.

### Job 2 — Pipeline DVC (entraînement)

```bash
python src/train_pipeline.py
```

Exécute l'entraînement complet (chargement OpenML → preprocessing → Ridge → sauvegarde modèle + `metrics.json`).

Uploade `metrics.json` comme artefact GitHub Actions (téléchargeable depuis l'interface GitHub).

### Job 3 — Tests API + Docker (conditionnel au Job 2)

```bash
python src/train_pipeline.py    # Réentraîne le modèle (nécessaire pour les tests API)
pytest tests/test_api.py -v --tb=short
docker build -t laplace-immo-api . && echo "Docker build OK"
```

Valide que :
1. L'API fonctionne correctement avec le modèle fraîchement entraîné
2. L'image Docker se construit sans erreur

**Motivation** : la CI garantit que le code reste fonctionnel à tout moment. Si un collaborateur pousse une modification qui casse les tests ou fait planter le pipeline, l'équipe est alertée immédiatement.

---

## Choix techniques et leurs motivations

| Choix | Alternative | Motivation |
|-------|-------------|------------|
| `log1p(saleprice)` comme cible | cible brute | Normalise la distribution asymétrique, améliore SVR de 54k$ |
| PPS pour la sélection de features | corrélation Pearson | Capture les relations non linéaires |
| RobustScaler | StandardScaler | Plus résistant aux outliers immobiliers |
| TargetEncoder pour haute cardinalité | OneHotEncoder | Évite l'explosion dimensionnelle (25 colonnes → 1) |
| `dill` pour la sérialisation | `pickle` | Supporte les lambdas et objets Python complexes |
| `loguru` pour les logs | `print()` | Format structuré avec niveau (INFO/WARNING), timestamp automatique |
| `pendulum` pour les dates | `datetime` | API plus intuitive, gestion des fuseaux horaires simplifiée |
| FastAPI + Pydantic | Flask / Django REST | Validation automatique, Swagger UI intégré, async natif |
| `dill.load` + itération manuelle | `pipeline.predict()` | Contourne l'incompatibilité sklearn `set_output` avec les transformeurs custom Jupyter |
| Evidently + KS-test fallback | monitoring custom | Rapport HTML riche pour Evidently, dépendance légère via KS-test |
| Docker multi-worker (2 workers) | 1 worker | Parallélisation des requêtes API sans Kubernetes |

---

## Résultats détaillés

### Évolution des performances

| Étape | RMSE | MAE | R² |
|-------|------|-----|-----|
| Baseline (DummyRegressor — moyenne) | ~79 000 $ | — | 0.00 |
| Meilleur modèle brut (SVR RBF, sans log) | ~83 000 $ | — | — |
| Meilleur modèle avec log-transform (SVR RBF) | ~28 600 $ | — | 0.857 |
| Après optimisation Optuna (LightGBM) | ~28 624 $ | — | 0.871 |
| **Après ingénierie prétraitement (LightGBM)** | **26 338 $** | **17 058 $** | **0.891** |

### Features les plus importantes (LightGBM, gain d'information)

| Rang | Feature | Description |
|------|---------|-------------|
| 1 | `overallqual` | Qualité générale des matériaux (1–10) |
| 2 | `grlivarea` | Surface habitable au-dessus du sol |
| 3 | `totalbsmtsf` | Surface totale du sous-sol |
| 4 | `qual_x_surface` | Interaction qualité × surface (engineered) |
| 5 | `neighborhood_enc` | Quartier (TargetEncoded) |
| 6 | `garagecars` | Capacité du garage |

---

## Comment reproduire

### Installation

```bash
git clone https://github.com/kira9292/house-price.git
cd house-price
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Lancer les tests unitaires

```bash
pytest tests/test_make_dataset.py tests/test_trainer.py -v
```

### Réentraîner le modèle

```bash
python src/train_pipeline.py
```

### Lancer les tests de l'API (modèle requis)

```bash
pytest tests/test_api.py -v
```

### Démarrer l'API localement

```bash
uvicorn src.api:app --reload --port 8000
# Swagger UI disponible sur http://127.0.0.1:8000/docs
```

### Démarrer via Docker

```bash
docker build -t laplace-immo-api .
docker run -p 8000:8000 laplace-immo-api
# ou
docker compose up
```

### Tester l'API avec curl

```bash
# Prédiction simple
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "garagecars": 2, "fullbath": 2, "building_age": 5.0,
    "garagearea": 548.0, "totrmsabvgrd": 8, "remodel_age": 5.0,
    "garage_age": 5.0, "grlivarea": 1710.0, "fireplaces": 1,
    "totalbsmtsf": 856.0, "overallqual": "7", "neighborhood": "CollgCr",
    "exterqual": "Gd", "bsmtqual": "Gd", "kitchenqual": "Gd",
    "alley": "NoAlley", "garagefinish": "RFn", "foundation": "PConc",
    "mssubclass": "60", "garagetype": "Attchd", "heatingqc": "Ex",
    "exterior1st": "VinylSd", "bsmtfintype1": "GLQ",
    "exterior2nd": "VinylSd", "masvnrtype": "BrkFace", "mszoning": "RL"
  }'
```

### Lancer le monitoring de drift

```bash
python src/monitoring.py
# Rapport HTML généré dans reports/monitoring_drift_report.html
```

### Visualiser les expériences MLFlow

```bash
cd notebooks
mlflow ui --port 5001
# Ouvrir http://127.0.0.1:5001
```

### Vérifier les métriques

```bash
cat metrics.json
```
