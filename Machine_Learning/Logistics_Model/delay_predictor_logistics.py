# ============================================================
# Machine_Learning/New dataset/delay_predictor_logistics.py
#
# Training and asset serialization script for the Logistics model.
#
# This script:
#   1. Loads the dynamic supply chain logistics dataset.
#   2. Rebuilds a realistic delay target based on domain weights
#      and noise, correcting the random distribution in raw data.
#   3. Splits the dataset into an 80% Training set and a 20%
#      unseen Evaluation set, exporting both to disk.
#   4. Fits a scikit-learn pipeline (Imputer + Scaler + LinearRegression)
#      on the training data.
#   5. Serializes the trained pipeline and feature lists for backend use.
# ============================================================

import os
import json
import pickle
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# Config paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_PATH = os.path.join(SCRIPT_DIR, "dynamic_supply_chain_logistics_dataset.xlsx")
MODEL_EXPORT_PATH = os.path.join(SCRIPT_DIR, "logistics_model.pkl")
FEATURES_EXPORT_PATH = os.path.join(SCRIPT_DIR, "logistics_features.json")
EVAL_EXPORT_PATH = os.path.join(SCRIPT_DIR, "evaluation_shipments.xlsx")
TRAIN_EXPORT_PATH = os.path.join(SCRIPT_DIR, "training_shipments.xlsx")

def train_logistics_pipeline():
    print("=" * 60)
    print("  TRAINING DYNAMIC LOGISTICS DELAY PREDICTOR")
    print("=" * 60)

    if not os.path.exists(DATASET_PATH):
        raise FileNotFoundError(f"Dataset not found at: {DATASET_PATH}")

    print(f"[*] Loading raw dataset from: {DATASET_PATH}...")
    df = pd.read_excel(DATASET_PATH)
    original_row_count = len(df)

    # 1. Clean targets
    df = df.drop(columns=["delay_probability", "risk_classification"], errors="ignore")

    # 2. Feature Engineering (Timestamp parsing)
    print("[*] Performing feature engineering...")
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["month"]     = df["timestamp"].dt.month
    df["day"]       = df["timestamp"].dt.day
    df["hour"]      = df["timestamp"].dt.hour
    df["dayofweek"] = df["timestamp"].dt.dayofweek
    df = df.drop(columns=["timestamp"], errors="ignore")

    # 3. Rebuild Target (The Teammate's Weighting Logic)
    print("[*] Rebuilding target (delivery_time_deviation) with domain weights...")
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
    # Add 30% Gaussian noise
    noise = np.random.normal(0, raw.std() * 0.30, size=len(raw))
    raw = raw + noise

    # Rescale to range [-2.0, 10.0]
    lo, hi = -2.0, 10.0
    target = (raw - raw.min()) / (raw.max() - raw.min()) * (hi - lo) + lo
    df["delivery_time_deviation"] = target

    # 4. Train-Test Split (80/20)
    print("[*] Performing 80/20 Train-Test split...")
    # To keep features and targets aligned during export, we split the DataFrame
    train_df, eval_df = train_test_split(df, test_size=0.20, random_state=42)

    # Export splits to disk
    print(f"[*] Saving 20% Evaluation Set ({len(eval_df)} rows) to: {EVAL_EXPORT_PATH}")
    eval_df.to_excel(EVAL_EXPORT_PATH, index=False)
    
    print(f"[*] Saving 80% Training Set ({len(train_df)} rows) to: {TRAIN_EXPORT_PATH}")
    train_df.to_excel(TRAIN_EXPORT_PATH, index=False)

    # 5. Preprocessing & Column Pipeline
    X_train = train_df.drop(columns=["delivery_time_deviation"])
    y_train = train_df["delivery_time_deviation"]
    X_test  = eval_df.drop(columns=["delivery_time_deviation"])
    y_test  = eval_df["delivery_time_deviation"]

    # Since all features are numerical at this stage
    numerical_features = X_train.select_dtypes(exclude=["object"]).columns.tolist()

    preprocessor = ColumnTransformer(transformers=[
        ("num", Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler",  StandardScaler())
        ]), numerical_features)
    ])

    # 6. Fit Pipeline
    print("[*] Training Linear Regression pipeline...")
    pipeline = Pipeline([
        ("preprocessor", preprocessor),
        ("model",        LinearRegression())
    ])

    pipeline.fit(X_train, y_train)

    # 7. Evaluate
    predictions = pipeline.predict(X_test)
    mae  = mean_absolute_error(y_test, predictions)
    rmse = np.sqrt(mean_squared_error(y_test, predictions))
    r2   = r2_score(y_test, predictions)

    print("=" * 60)
    print("  EVALUATION RESULTS ON UNSEEN TEST SET")
    print("=" * 60)
    print(f"  MAE  : {mae:.6f}")
    print(f"  RMSE : {rmse:.6f}")
    print(f"  R2   : {r2:.6f}")
    print("=" * 60)

    # 8. Export trained Pipeline and Feature List
    print(f"[*] Serializing pipeline to: {MODEL_EXPORT_PATH}...")
    with open(MODEL_EXPORT_PATH, "wb") as f:
        pickle.dump(pipeline, f)

    print(f"[*] Exporting feature list to: {FEATURES_EXPORT_PATH}...")
    feature_list = list(X_train.columns)
    with open(FEATURES_EXPORT_PATH, "w") as f:
        json.dump(feature_list, f)

    print("[+] Model training and asset serialization complete.")
    return True

if __name__ == "__main__":
    train_logistics_pipeline()
