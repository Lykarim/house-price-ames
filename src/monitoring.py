"""Dashboard de monitoring et détection de drift — Laplace Immo."""

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.append(str(Path(__file__).parent.parent))

PROJECT_DIR = Path(__file__).parent.parent
REPORT_DIR = PROJECT_DIR / "reports"
DATA_PATH = PROJECT_DIR / "data" / "output" / "house_prices.parquet"

NUMERIC_FEATURES = [
    "bsmtfinsf1", "bsmtunfsf", "garagecars",
    "lotarea", "masvnrarea", "totalbsmtsf",
    "building_age", "remodel_age",
]
CATEGORICAL_FEATURES = [
    "overallqual", "mssubclass", "condition2", "exterqual",
    "foundation", "garagetype", "heating", "heatingqc",
    "housestyle", "masvnrtype", "miscfeature", "saletype", "street",
]
TARGET = "saleprice"
ALL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


def load_reference_data() -> pd.DataFrame:
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Données introuvables : {DATA_PATH}. Lancer d'abord `python src/make_dataset.py`.")
    df = pd.read_parquet(DATA_PATH)
    df.columns = df.columns.str.lower()
    available = [c for c in ALL_FEATURES + [TARGET] if c in df.columns]
    return df[available]


def simulate_current_data(reference: pd.DataFrame, drift_fraction: float = 0.3) -> pd.DataFrame:
    """
    Simule un jeu de données courant avec drift artificiel sur une fraction des features.
    En production, remplacer par les vraies nouvelles données reçues via l'API.
    """
    rng = np.random.default_rng(42)
    current = reference.sample(frac=0.3, random_state=42).copy()

    drifted_cols = rng.choice(NUMERIC_FEATURES, size=int(len(NUMERIC_FEATURES) * drift_fraction), replace=False)
    for col in drifted_cols:
        if col in current.columns:
            current[col] = current[col] * rng.uniform(1.2, 1.5)

    return current


def run_evidently_report(reference: pd.DataFrame, current: pd.DataFrame) -> Path:
    """Génère un rapport Evidently HTML complet (data drift + data quality)."""
    try:
        from evidently.report import Report
        from evidently.metric_preset import DataDriftPreset, DataQualityPreset, TargetDriftPreset
    except ImportError:
        raise ImportError("Installer evidently : pip install evidently")

    report = Report(metrics=[
        DataDriftPreset(),
        DataQualityPreset(),
        TargetDriftPreset() if TARGET in reference.columns else DataQualityPreset(),
    ])

    report.run(reference_data=reference, current_data=current)

    output_path = REPORT_DIR / "monitoring_drift_report.html"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report.save_html(str(output_path))
    return output_path


def run_basic_drift_report(reference: pd.DataFrame, current: pd.DataFrame) -> dict:
    """
    Détection de drift basique (sans Evidently) — comparaison des distributions.
    Utilisé comme fallback ou pour des alertes légères.
    """
    from scipy import stats

    drift_results = {}
    for col in NUMERIC_FEATURES:
        if col not in reference.columns or col not in current.columns:
            continue
        ref_vals = reference[col].dropna()
        cur_vals = current[col].dropna()
        stat, p_value = stats.ks_2samp(ref_vals, cur_vals)
        drift_results[col] = {
            "ks_statistic": round(float(stat), 4),
            "p_value": round(float(p_value), 4),
            "drift_detected": p_value < 0.05,
            "ref_mean": round(float(ref_vals.mean()), 2),
            "cur_mean": round(float(cur_vals.mean()), 2),
        }

    drifted = [k for k, v in drift_results.items() if v["drift_detected"]]
    return {
        "total_features_checked": len(drift_results),
        "features_with_drift": len(drifted),
        "drifted_features": drifted,
        "details": drift_results,
    }


def main():
    from loguru import logger

    logger.info("Chargement des données de référence...")
    reference = load_reference_data()
    logger.info(f"Référence : {reference.shape}")

    logger.info("Simulation des données courantes (avec drift artificiel)...")
    current = simulate_current_data(reference)
    logger.info(f"Courant : {current.shape}")

    # ── Rapport Evidently ────────────────────────────────────────────────────
    try:
        report_path = run_evidently_report(reference, current)
        logger.success(f"Rapport Evidently généré : {report_path}")
    except ImportError:
        logger.warning("Evidently non disponible — utilisation du rapport basique")
        drift_summary = run_basic_drift_report(reference, current)
        logger.info(f"Features avec drift : {drift_summary['features_with_drift']}/{drift_summary['total_features_checked']}")
        for feat in drift_summary["drifted_features"]:
            d = drift_summary["details"][feat]
            logger.warning(f"  DRIFT {feat}: mean {d['ref_mean']} → {d['cur_mean']} (p={d['p_value']})")

    # ── Rapport basique toujours affiché ─────────────────────────────────────
    drift_summary = run_basic_drift_report(reference, current)
    logger.info("=== Résumé drift (KS-test) ===")
    logger.info(f"Features analysées : {drift_summary['total_features_checked']}")
    logger.info(f"Features avec drift détecté : {drift_summary['features_with_drift']}")
    if drift_summary["drifted_features"]:
        logger.warning(f"Features driftées : {drift_summary['drifted_features']}")
    else:
        logger.success("Aucun drift significatif détecté.")


if __name__ == "__main__":
    main()
