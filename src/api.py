"""API REST de prédiction des prix immobiliers — Laplace Immo."""

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import dill
import numpy as np
import pandas as pd
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

PROJECT_DIR = Path(__file__).parent.parent
MODEL_DIR = PROJECT_DIR / "models"
METRICS_PATH = PROJECT_DIR / "metrics.json"

def _load_model():
    # Priorité aux modèles standard sklearn (sans transformers custom des notebooks)
    # qui sont compatibles avec tous les contextes d'exécution (API, tests, CI).
    standard_models = sorted(MODEL_DIR.glob("*model_house_price*.dill"))
    all_models = sorted(MODEL_DIR.glob("*.dill"))
    candidates = standard_models if standard_models else all_models
    if not candidates:
        raise FileNotFoundError(f"Aucun modèle trouvé dans {MODEL_DIR}")
    latest = candidates[-1]
    with open(latest, "rb") as f:
        pipeline = dill.load(f)
    log_scale = "optimized" in latest.name
    return pipeline, latest.name, log_scale


def _patch_pipeline(pipeline):
    """
    Reconfigure les transformers custom (définis dans les notebooks Jupyter) pour
    éviter les incompatibilités avec le wrapper set_output de sklearn en contexte API.
    Seuls les transformers (pas le modèle final) sont patchés.
    """
    BUILTIN_MODULES = {"sklearn", "lightgbm", "xgboost", "catboost"}

    for _, step in pipeline.steps[:-1]:  # skip the final estimator
        module = getattr(step.__class__, "__module__", "") or ""
        is_custom = not any(module.startswith(m) for m in BUILTIN_MODULES)

        if is_custom and hasattr(step.__class__, "transform"):
            original_transform = step.__class__.transform
            def _make_transform(orig):
                def safe_transform(self, X):
                    return orig(self, X)
                return safe_transform
            step.__class__.transform = _make_transform(original_transform)

    return pipeline


# Chargement du modèle au démarrage du module
_pipeline, _model_name, _log_scale = _load_model()
_pipeline = _patch_pipeline(_pipeline)


@asynccontextmanager
async def lifespan(application: "FastAPI"):
    yield  # modèle déjà chargé au niveau module


app = FastAPI(
    lifespan=lifespan,
    title="Laplace Immo — Prédiction des Prix Immobiliers",
    description=(
        "API de prédiction du prix de vente d'une maison basée sur le dataset **Ames Housing** "
        "(Iowa, USA). Modèle final : **LightGBM** avec prétraitement avancé.\n\n"
        "| Métrique | Valeur |\n|----------|--------|\n"
        "| RMSE test | **26 338 $** |\n"
        "| MAE test | 17 058 $ |\n"
        "| R² test | **0.891** |\n\n"
        "**Endpoints principaux :**\n"
        "- `POST /predict` — Prédire le prix d'une maison\n"
        "- `POST /predict/batch` — Prédiction en batch (jusqu'à 100 maisons)\n"
        "- `GET /health` — Santé de l'API\n"
        "- `GET /model-info` — Métriques du modèle"
    ),
    version="1.0.0",
    contact={"name": "Laplace Immo", "email": "contact@laplace-immo.fr"},
)


# ── Schémas Pydantic ────────────────────────────────────────────────────────

class HouseFeatures(BaseModel):
    """Caractéristiques d'une maison pour la prédiction du prix de vente."""

    # ── Numériques ──────────────────────────────────────────────────────────
    garagecars: int = Field(2, ge=0, le=5, description="Capacité garage (nombre de voitures)")
    fullbath: int = Field(2, ge=0, le=5, description="Nombre de salles de bain complètes")
    building_age: float = Field(20.0, description="Âge du bâtiment en années (yrsold - yearbuilt)")
    garagearea: float = Field(500.0, ge=0, description="Surface du garage (sq ft)")
    totrmsabvgrd: int = Field(8, ge=1, le=20, description="Nombre total de pièces au-dessus du sol")
    remodel_age: float = Field(20.0, description="Années depuis dernière rénovation (yrsold - yearremodadd)")
    garage_age: float = Field(20.0, description="Âge du garage en années (yrsold - garageyrblt)")
    grlivarea: float = Field(1500.0, ge=0, description="Surface habitable au-dessus du sol (sq ft)")
    fireplaces: int = Field(1, ge=0, le=4, description="Nombre de cheminées")
    totalbsmtsf: float = Field(800.0, ge=0, description="Surface totale du sous-sol (sq ft)")

    # ── Catégorielles ───────────────────────────────────────────────────────
    overallqual: str = Field("7", description="Qualité générale matériaux/finitions (1=Très mauvais → 10=Excellent)")
    neighborhood: str = Field("CollgCr", description="Quartier (CollgCr, OldTown, Edwards, Somerst, ...)")
    exterqual: str = Field("Gd", description="Qualité extérieure (Ex/Gd/TA/Fa/Po)")
    bsmtqual: str = Field("Gd", description="Hauteur sous-sol (Ex/Gd/TA/Fa/Po/NoBsmt)")
    kitchenqual: str = Field("Gd", description="Qualité cuisine (Ex/Gd/TA/Fa/Po)")
    alley: str = Field("NoAlley", description="Type d'accès ruelle (Grvl/Pave/NoAlley)")
    garagefinish: str = Field("RFn", description="Finition intérieure garage (Fin/RFn/Unf/NoGarage)")
    foundation: str = Field("PConc", description="Type de fondation (BrkTil/CBlock/PConc/Slab/Stone/Wood)")
    mssubclass: str = Field("60", description="Type de logement (20=1-Story, 60=2-Story 1946+, ...)")
    garagetype: str = Field("Attchd", description="Emplacement garage (Attchd/Detchd/BuiltIn/CarPort/NA/...)")
    heatingqc: str = Field("Ex", description="Qualité chauffage (Ex/Gd/TA/Fa/Po)")
    exterior1st: str = Field("VinylSd", description="Revêtement extérieur principal")
    bsmtfintype1: str = Field("GLQ", description="Qualité surface finie sous-sol (GLQ/ALQ/BLQ/Rec/LwQ/Unf/NoBsmt)")
    exterior2nd: str = Field("VinylSd", description="Revêtement extérieur secondaire")
    masvnrtype: str = Field("BrkFace", description="Type revêtement maçonnerie (BrkCmn/BrkFace/CBlock/None/Stone)")
    mszoning: str = Field("RL", description="Zonage (RL/RM/C(all)/FV/RH)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "garagecars": 2,
                "fullbath": 2,
                "building_age": 5.0,
                "garagearea": 548.0,
                "totrmsabvgrd": 8,
                "remodel_age": 5.0,
                "garage_age": 5.0,
                "grlivarea": 1710.0,
                "fireplaces": 1,
                "totalbsmtsf": 856.0,
                "overallqual": "7",
                "neighborhood": "CollgCr",
                "exterqual": "Gd",
                "bsmtqual": "Gd",
                "kitchenqual": "Gd",
                "alley": "NoAlley",
                "garagefinish": "RFn",
                "foundation": "PConc",
                "mssubclass": "60",
                "garagetype": "Attchd",
                "heatingqc": "Ex",
                "exterior1st": "VinylSd",
                "bsmtfintype1": "GLQ",
                "exterior2nd": "VinylSd",
                "masvnrtype": "BrkFace",
                "mszoning": "RL",
            }
        }
    }


class PredictionResponse(BaseModel):
    predicted_price: float = Field(..., description="Prix de vente prédit en dollars (USD)")
    currency: str = Field("USD", description="Devise")
    model_used: str = Field(..., description="Nom du fichier modèle utilisé")


class BatchPredictionRequest(BaseModel):
    houses: list[HouseFeatures] = Field(..., min_length=1, max_length=100, description="Liste de maisons à évaluer")


class BatchPredictionResponse(BaseModel):
    predictions: list[float] = Field(..., description="Prix prédits en USD")
    count: int
    currency: str = "USD"
    model_used: str


# ── Helpers ─────────────────────────────────────────────────────────────────

def _predict_price(df: pd.DataFrame) -> list[float]:
    # Appel manuel des étapes pour éviter les incompatibilités du wrapper set_output
    # avec les transformers custom (SemanticImputer, OutlierClipper, FeatureEngineer)
    # définis dans les notebooks Jupyter et sérialisés via dill.
    Xt = df.copy()
    for _, _, step in _pipeline._iter(with_final=False):
        Xt = step.transform(Xt)
    raw = _pipeline.steps[-1][1].predict(Xt)
    if _log_scale:
        raw = np.expm1(raw)
    return [round(float(p), 2) for p in raw]


# ── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/", tags=["Info"], summary="Bienvenue")
def root():
    return {
        "message": "Laplace Immo — API Prédiction Prix Immobiliers",
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health",
        "model_info": "/model-info",
    }


@app.get("/health", tags=["Info"], summary="Vérification de l'état de l'API")
def health():
    return {"status": "ok", "model_loaded": _pipeline is not None, "model": _model_name}


@app.get("/model-info", tags=["Info"], summary="Informations sur le modèle et ses métriques de performance")
def model_info():
    metrics = {}
    if METRICS_PATH.exists():
        metrics = json.loads(METRICS_PATH.read_text())
    return {
        "model": _model_name,
        "metrics": metrics,
        "dataset": "Ames Housing (Iowa, USA)",
        "n_features": 26,
        "log_scale_output": _log_scale,
    }


@app.post(
    "/predict",
    response_model=PredictionResponse,
    tags=["Prédiction"],
    summary="Prédire le prix de vente d'une maison",
)
def predict(features: HouseFeatures):
    """
    Prédit le prix de vente d'une maison à partir de ses caractéristiques.

    Retourne le prix estimé en **dollars américains (USD)**.
    """
    if _pipeline is None:
        raise HTTPException(status_code=503, detail="Modèle non chargé")
    try:
        df = pd.DataFrame([features.model_dump()])
        price = _predict_price(df)[0]
        return PredictionResponse(predicted_price=price, model_used=_model_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de prédiction : {e}")


@app.post(
    "/predict/batch",
    response_model=BatchPredictionResponse,
    tags=["Prédiction"],
    summary="Prédire le prix de plusieurs maisons en une seule requête",
)
def predict_batch(request: BatchPredictionRequest):
    """Prédiction en batch — jusqu'à **100 maisons** par requête."""
    if _pipeline is None:
        raise HTTPException(status_code=503, detail="Modèle non chargé")
    try:
        df = pd.DataFrame([h.model_dump() for h in request.houses])
        prices = _predict_price(df)
        return BatchPredictionResponse(predictions=prices, count=len(prices), model_used=_model_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur batch : {e}")


if __name__ == "__main__":
    uvicorn.run("src.api:app", host="0.0.0.0", port=8000, reload=True)
