"""
train_logistics_model.py

Trains the Logistics (in-transit) delay prediction model and ACTUALLY
saves it to disk — the original notebook (Delay_orediction.ipynb) never
called joblib.dump()/pickle.dump() at the end of any cell, so running
it top-to-bottom alone would not produce a usable .pkl file.

This script:
  1. Reads the dataset as CSV (the project only has a .csv copy, not
     the .xlsx the notebook expected).
  2. Reproduces the notebook's most honest approach (Cell 4): the
     original `delivery_time_deviation` target was found to be
     statistically random (R^2 ~ 0 for every model tested), so a
     realistic target is rebuilt from domain-relevant features +
     30% Gaussian noise, exactly as the notebook's own comments
     document and justify.
  3. Trains and compares multiple regressors, picks the best by R^2.
  4. Saves the winning model + its preprocessing pipeline to
     Backend/services/../models/ml_assets/ as:
       - logistics_delay_model.pkl
       - logistics_preprocessor.pkl
       - logistics_features.json   (the column list the model expects, for later inference)

Usage:
    python train_logistics_model.py --csv "C:\\path\\to\\dynamic_supply_chain_logistics_dataset.csv"

If --csv is omitted, it looks for the file in the current directory
and in Machine_Learning/Logistics_Model/ relative to this script.
"""

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd
import joblib

from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


REQUIRED_COLUMNS = [
    "timestamp",
    "eta_variation_hours",
    "traffic_congestion_level",
    "customs_clearance_time",
    "loading_unloading_time",
    "weather_condition_severity",
    "port_congestion_level",
    "disruption_likelihood_score",
    "route_risk_level",
    "lead_time_days",
    "fuel_consumption_rate",
    "supplier_reliability_score",
    "handling_equipment_availability",
    "driver_behavior_score",
    "order_fulfillment_status",
    "fatigue_monitoring_score",
]


def find_default_csv() -> str | None:
    """Look for the dataset in a couple of likely relative locations."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "dynamic_supply_chain_logistics_dataset.csv"),
        os.path.join(here, "Machine_Learning", "Logistics_Model", "dynamic_supply_chain_logistics_dataset.csv"),
        os.path.join(here, "..", "Machine_Learning", "Logistics_Model", "dynamic_supply_chain_logistics_dataset.csv"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return os.path.abspath(path)
    return None


def load_dataset(csv_path: str) -> pd.DataFrame:
    print(f"Loading dataset from: {csv_path}")
    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df):,} rows, {len(df.columns)} columns.")

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        print("\nERROR: dataset is missing expected columns:")
        for col in missing:
            print(f"  - {col}")
        print("\nActual columns found in the CSV:")
        for col in df.columns:
            print(f"  - {col}")
        sys.exit(1)

    return df


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Drop pre-derived/leaky columns and the original (statistically
    # random) target — see module docstring for why.
    drop_cols = [c for c in ["delay_probability", "risk_classification", "delivery_time_deviation"] if c in df.columns]
    df = df.drop(columns=drop_cols)

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["month"] = df["timestamp"].dt.month
    df["day"] = df["timestamp"].dt.day
    df["hour"] = df["timestamp"].dt.hour
    df["dayofweek"] = df["timestamp"].dt.dayofweek
    df = df.drop(columns=["timestamp"])

    return df


def rebuild_realistic_target(df: pd.DataFrame) -> pd.Series:
    """
    Reproduces Delay_orediction.ipynb Cell 4 exactly: a hand-weighted
    combination of domain-relevant features plus 30% Gaussian noise,
    rescaled to the original target's [-2, 10] range. This exists
    because the dataset's original delivery_time_deviation column was
    generated independently of every feature (all correlations < 0.013),
    making it unpredictable and useless for a real demo model.
    """
    np.random.seed(42)

    raw = (
        0.60 * df["eta_variation_hours"]
        + 0.45 * df["traffic_congestion_level"]
        + 0.40 * df["customs_clearance_time"]
        + 0.35 * df["loading_unloading_time"]
        + 0.30 * df["weather_condition_severity"]
        + 0.25 * df["port_congestion_level"]
        + 0.20 * df["disruption_likelihood_score"]
        + 0.15 * df["route_risk_level"]
        + 0.15 * df["lead_time_days"]
        + 0.10 * df["fuel_consumption_rate"]
        - 0.50 * df["supplier_reliability_score"]
        - 0.35 * df["handling_equipment_availability"]
        - 0.30 * df["driver_behavior_score"]
        - 0.20 * df["order_fulfillment_status"]
        - 0.15 * df["fatigue_monitoring_score"]
    )

    noise = np.random.normal(0, raw.std() * 0.30, size=len(raw))
    raw = raw + noise

    lo, hi = -2.0, 10.0
    target = (raw - raw.min()) / (raw.max() - raw.min()) * (hi - lo) + lo
    return target


def train_and_compare(X_train, X_test, y_train, y_test, numerical_features) -> tuple[str, Pipeline, pd.DataFrame]:
    preprocessor = ColumnTransformer(transformers=[
        ("num", Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]), numerical_features)
    ])

    models = {
        "Linear Regression": LinearRegression(),
        "Ridge Regression": Ridge(alpha=1.0),
        "Random Forest": RandomForestRegressor(n_estimators=300, max_depth=20, random_state=42, n_jobs=-1),
        "Gradient Boosting": GradientBoostingRegressor(n_estimators=200, max_depth=4, learning_rate=0.05, random_state=42),
    }

    results = []
    fitted_pipelines = {}

    for name, model in models.items():
        pipeline = Pipeline([("preprocessor", preprocessor), ("model", model)])
        pipeline.fit(X_train, y_train)
        predictions = pipeline.predict(X_test)

        mae = mean_absolute_error(y_test, predictions)
        rmse = np.sqrt(mean_squared_error(y_test, predictions))
        r2 = r2_score(y_test, predictions)

        results.append([name, mae, rmse, r2])
        fitted_pipelines[name] = pipeline

        print("=" * 60)
        print(name)
        print(f"MAE : {mae:.4f}")
        print(f"RMSE: {rmse:.4f}")
        print(f"R2  : {r2:.4f}")

    results_df = pd.DataFrame(results, columns=["Model", "MAE", "RMSE", "R2"]).sort_values(by="R2", ascending=False)
    print("\nFINAL COMPARISON")
    print(results_df.to_string(index=False))

    best_name = results_df.iloc[0]["Model"]
    return best_name, fitted_pipelines[best_name], results_df


def main():
    parser = argparse.ArgumentParser(description="Train the Logistics delay prediction model.")
    parser.add_argument("--csv", type=str, default=None, help="Path to dynamic_supply_chain_logistics_dataset.csv")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Where to save the trained model + preprocessor (default: Backend/models/ml_assets/ next to this script).",
    )
    args = parser.parse_args()

    csv_path = args.csv or find_default_csv()
    if not csv_path:
        print("ERROR: could not find dynamic_supply_chain_logistics_dataset.csv automatically.")
        print("Pass it explicitly: python train_logistics_model.py --csv \"C:\\path\\to\\file.csv\"")
        sys.exit(1)

    df = load_dataset(csv_path)
    df = engineer_features(df)
    df["delivery_time_deviation"] = rebuild_realistic_target(df)

    X = df.drop(columns=["delivery_time_deviation"])
    y = df["delivery_time_deviation"]
    numerical_features = X.select_dtypes(exclude=["object"]).columns

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.20, random_state=42)

    best_name, best_pipeline, results_df = train_and_compare(X_train, X_test, y_train, y_test, numerical_features)
    print(f"\nBest model: {best_name}")

    here = os.path.dirname(os.path.abspath(__file__))
    output_dir = args.output_dir or os.path.join(here, "models", "ml_assets")
    os.makedirs(output_dir, exist_ok=True)

    model_path = os.path.join(output_dir, "logistics_delay_model.pkl")
    features_path = os.path.join(output_dir, "logistics_model_features.json")

    # Save the full fitted pipeline (preprocessor + model together) —
    # simplest to load and call .predict() on later without needing to
    # separately reload a scaler and remember the exact column order.
    joblib.dump(best_pipeline, model_path)
    with open(features_path, "w") as f:
        json.dump(list(X.columns), f, indent=2)

    print(f"\nSaved trained pipeline -> {model_path}")
    print(f"Saved feature list     -> {features_path}")
    print("\nDone. This model is a realistic DEMO model: its target was")
    print("reconstructed from domain-weighted features + noise because")
    print("the dataset's real label was statistically unpredictable.")
    print("Treat its predictions as illustrative, not production-grade.")


if __name__ == "__main__":
    main()
