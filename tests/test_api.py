"""Tests unitaires pour l'API FastAPI — Laplace Immo."""

import pytest
from fastapi.testclient import TestClient

from src.api import app

SAMPLE_HOUSE = {
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


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "docs" in response.json()


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["model_loaded"] is True


def test_model_info(client):
    response = client.get("/model-info")
    assert response.status_code == 200
    data = response.json()
    assert "model" in data
    assert "metrics" in data


def test_predict_returns_positive_price(client):
    response = client.post("/predict", json=SAMPLE_HOUSE)
    assert response.status_code == 200
    data = response.json()
    assert "predicted_price" in data
    assert data["predicted_price"] > 0
    assert data["currency"] == "USD"


def test_predict_high_quality_house_costs_more(client):
    low_quality = {**SAMPLE_HOUSE, "overallqual": "3", "garagecars": 0, "grlivarea": 800.0}
    high_quality = {**SAMPLE_HOUSE, "overallqual": "9", "garagecars": 3, "grlivarea": 2500.0}

    resp_low = client.post("/predict", json=low_quality)
    resp_high = client.post("/predict", json=high_quality)

    assert resp_low.status_code == 200
    assert resp_high.status_code == 200
    assert resp_high.json()["predicted_price"] > resp_low.json()["predicted_price"]


def test_predict_batch(client):
    response = client.post("/predict/batch", json={"houses": [SAMPLE_HOUSE, SAMPLE_HOUSE]})
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert len(data["predictions"]) == 2
    assert all(p > 0 for p in data["predictions"])


def test_predict_batch_single_house(client):
    response = client.post("/predict/batch", json={"houses": [SAMPLE_HOUSE]})
    assert response.status_code == 200
    assert response.json()["count"] == 1


def test_docs_available(client):
    response = client.get("/docs")
    assert response.status_code == 200


def test_openapi_schema(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "paths" in schema
    assert "/predict" in schema["paths"]
    assert "/predict/batch" in schema["paths"]
