import os
import json
import pickle
import datetime
import requests
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier
from sklearn.utils import resample
from sklearn.metrics import classification_report, roc_auc_score
from SPARQLWrapper import SPARQLWrapper, JSON

# --- CONFIGURATION ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
GRAPHDB_ENDPOINT = "http://localhost:7200/repositories/SemanticDigitalTwin"
BACKEND_URL = "http://127.0.0.1:8001/api/sandbox/simulate-iot"
DATASET_PATH = os.path.join(SCRIPT_DIR, "Dataset_Procurement_SelectedFeatures.csv")
TELEMETRY_STREAM_PATH = os.path.join(os.path.dirname(os.path.dirname(SCRIPT_DIR)), "Data_Science", "data_Lake", "iot_streams", "telemetry_stream_001.json")

# Model serialization paths
MODEL_PATH = os.path.join(SCRIPT_DIR, "delay_prediction_model.pkl")
SCALER_PATH = os.path.join(SCRIPT_DIR, "scaler.pkl")
FEATURES_PATH = os.path.join(SCRIPT_DIR, "model_features.json")

# Static lookup fallback in case GraphDB is offline or unseeded
FALLBACK_DELIVERY_CONTEXT = {
    "DEL_015": {
        "PO Type": "Standard",
        "Supplier Region": "Asia",
        "Supplier Tier": 1,
        "Supplier Risk": "Low",
        "Payment Terms": "Net 30",
        "Category": "Raw Materials",
        "Sub Category": "Steel Sheet (kg)",
        "Unit of Measure": "KG",
        "Unit Price": 6.55,
        "Quantity": 41,
        "Discount Pct": 0,
        "Tax Pct": 5,
        "Line Net": 268.55,
        "Currency": "GBP",
        "Savings Pct": 7.7,
        "Lead Time Days": 50,
        "Department": "IT",
        "Contract Type": "Framework",
        "Maverick Spend": "No",
        "Single Source Flag": "No",
        "Preferred Supplier": "Yes",
        "Local International": "International",
        "Supplier ESG Score": 41.6,
        "PO_Month_Num": 5,
        "PO_DayOfWeek": 3
    },
    "DEL_005": {
        "PO Type": "Emergency",
        "Supplier Region": "Asia",
        "Supplier Tier": 1,
        "Supplier Risk": "Low",
        "Payment Terms": "Net 30",
        "Category": "Maintenance",
        "Sub Category": "Calibration Svc",
        "Unit of Measure": "EA",
        "Unit Price": 979.07,
        "Quantity": 192,
        "Discount Pct": 0,
        "Tax Pct": 0,
        "Line Net": 187981.44,
        "Currency": "AUD",
        "Savings Pct": 18.0,
        "Lead Time Days": 52,
        "Department": "Operations",
        "Contract Type": "Master Supply",
        "Maverick Spend": "No",
        "Single Source Flag": "No",
        "Preferred Supplier": "Yes",
        "Local International": "International",
        "Supplier ESG Score": 77.2,
        "PO_Month_Num": 5,
        "PO_DayOfWeek": 5
    }
}


# =====================================================================
# 1. AUTOMATED MODEL TRAINING AND ASSET EXPORT
# =====================================================================

def train_and_export_model():
    """Trains the RandomForest model on historical data and serializes assets."""
    print(f"[*] Training assets missing. Starting automated model training on '{DATASET_PATH}'...")
    
    if not os.path.exists(DATASET_PATH):
        raise FileNotFoundError(f"Dataset file '{DATASET_PATH}' not found in the current directory.")
        
    df = pd.read_csv(DATASET_PATH)
    
    # 1. Feature Engineering
    df['Cost_per_Day'] = df['Unit Price'] / (df['Lead Time Days'] + 1)
    df['Qty_per_Day'] = df['Quantity'] / (df['Lead Time Days'] + 1)
    
    category_lead_time_mean = df.groupby('Category')['Lead Time Days'].transform('mean')
    df['Extreme_Lead_Time_Flag'] = (df['Lead Time Days'] > (1.5 * category_lead_time_mean)).astype(int)
    df['Tier_LeadTime_Interaction'] = df['Supplier Tier'] * df['Lead Time Days']
    
    line_net_75 = df['Line Net'].quantile(0.75)
    df['High_Value_Order'] = (df['Line Net'] > line_net_75).astype(int)
    
    # 2. Drop redundant columns
    df = df.drop(columns=['Supplier Status', 'Budget Unit Price'])
    
    # 3. One-Hot Encoding
    categorical_cols = df.select_dtypes(include=['object']).columns.tolist()
    df_encoded = pd.get_dummies(df, columns=categorical_cols, drop_first=True)
    
    # 4. Split Features & Target
    X = df_encoded.drop(columns=['Target_OnTimeDelivery'])
    y = df_encoded['Target_OnTimeDelivery']
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    # 5. Oversample training data to handle imbalance
    train_data = pd.concat([X_train, y_train], axis=1)
    majority = train_data[train_data['Target_OnTimeDelivery'] == 1]
    minority = train_data[train_data['Target_OnTimeDelivery'] == 0]
    
    minority_upsampled = resample(minority, replace=True, n_samples=len(majority), random_state=42)
    upsampled_train_data = pd.concat([majority, minority_upsampled])
    
    X_train_upsampled = upsampled_train_data.drop(columns=['Target_OnTimeDelivery'])
    y_train_upsampled = upsampled_train_data['Target_OnTimeDelivery']
    
    # 6. Scaling
    numerical_cols = [
        'Unit Price', 'Quantity', 'Discount Pct', 'Tax Pct',
        'Line Net', 'Savings Pct', 'Lead Time Days', 'Supplier ESG Score',
        'Supplier Tier', 'PO_Month_Num', 'PO_DayOfWeek',
        'Cost_per_Day', 'Qty_per_Day', 'Tier_LeadTime_Interaction'
    ]
    
    scaler = StandardScaler()
    # Fit scaler on upsampled training features
    scaler.fit(X_train_upsampled[numerical_cols])
    
    # Scale numerical features in-place on a copy of upsampled training data
    X_train_upsampled_scaled = X_train_upsampled.copy()
    X_train_upsampled_scaled[numerical_cols] = scaler.transform(X_train_upsampled[numerical_cols])
    
    # 7. Model Training (Risk-Averse weighting)
    rf_model_risk = RandomForestClassifier(n_estimators=300, random_state=42, class_weight={0: 3, 1: 1})
    rf_model_risk.fit(X_train_upsampled_scaled, y_train_upsampled)
    
    # Save assets
    with open(MODEL_PATH, 'wb') as f:
        pickle.dump(rf_model_risk, f)
        
    with open(SCALER_PATH, 'wb') as f:
        pickle.dump(scaler, f)
        
    # Save exact feature columns list to maintain consistency during live encoding
    with open(FEATURES_PATH, 'w') as f:
        json.dump(list(X.columns), f)
        
    print("[+] Model, Scaler, and Feature list successfully serialized.")


# =====================================================================
# 2. CONTEXT RETRIEVAL (GraphDB + Fallback)
# =====================================================================

def query_graphdb_context(delivery_id: str) -> dict:
    """Queries GraphDB for supplier, material, and SLA metrics related to a delivery."""
    query = f"""
    PREFIX : <http://example.org/ontology#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    
    SELECT ?poType ?supplierRegion ?supplierTier ?paymentTerms ?materialLabel
           ?unitOfMeasure ?hasUnitCost ?quantity ?discountPct ?taxPct ?lineNet ?hasCurrency 
           ?savingsPct ?leadTimeDays ?department ?contractType ?maverickSpend ?singleSourceFlag 
           ?preferredSupplier ?localInternational ?esgScore
    WHERE {{
        :{delivery_id} a :DeliveryEvent ;
                    :transports ?material .
        ?material rdfs:label ?materialLabel .
        ?supplier :supplies ?material ;
                  rdfs:label ?supplierName .
                  
        # Map values from GraphDB triples
        OPTIONAL {{ ?supplier :hasReliabilityTier ?supplierTier }}
        OPTIONAL {{ ?supplier :hasReliabilityScore ?esgScore }}
        
        # Load properties from GraphDB
        OPTIONAL {{ :{delivery_id} :poType ?poType }}
        OPTIONAL {{ :{delivery_id} :supplierRegion ?supplierRegion }}
        OPTIONAL {{ :{delivery_id} :paymentTerms ?paymentTerms }}
        OPTIONAL {{ :{delivery_id} :unitOfMeasure ?unitOfMeasure }}
        OPTIONAL {{ :{delivery_id} :hasUnitCost ?hasUnitCost }}
        OPTIONAL {{
            :{delivery_id} :fulfills ?po .
            ?po :hasOrderedQuantity ?quantity .
        }}
        OPTIONAL {{ :{delivery_id} :discountPct ?discountPct }}
        OPTIONAL {{ :{delivery_id} :taxPct ?taxPct }}
        OPTIONAL {{ :{delivery_id} :lineNet ?lineNet }}
        OPTIONAL {{ :{delivery_id} :hasCurrency ?hasCurrency }}
        OPTIONAL {{ :{delivery_id} :savingsPct ?savingsPct }}
        OPTIONAL {{ :{delivery_id} :leadTimeDays ?leadTimeDays }}
        OPTIONAL {{ :{delivery_id} :department ?department }}
        OPTIONAL {{ :{delivery_id} :contractType ?contractType }}
        OPTIONAL {{ :{delivery_id} :maverickSpend ?maverickSpend }}
        OPTIONAL {{ :{delivery_id} :singleSourceFlag ?singleSourceFlag }}
        OPTIONAL {{ :{delivery_id} :preferredSupplier ?preferredSupplier }}
        OPTIONAL {{ :{delivery_id} :localInternational ?localInternational }}
    }}
    LIMIT 1
    """
    sparql = SPARQLWrapper(GRAPHDB_ENDPOINT)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()["results"]["bindings"]
    if results:
        row = results[0]
        # Convert SPARQL variables into Python dictionary
        context = {}
        for key, val in row.items():
            # Cast numeric fields appropriately
            if key in ['quantity', 'leadTimeDays']:
                context[key] = int(float(val['value']))
            elif key in ['hasUnitCost', 'discountPct', 'taxPct', 'lineNet', 'savingsPct', 'esgScore']:
                context[key] = float(val['value'])
            else:
                context[key] = str(val['value'])
        
        # Standardize raw supplier reliability tier string/integer to model features
        raw_tier = context.get("supplierTier", "High")
        if str(raw_tier).strip() in ['1', 'High']:
            tier_int = 1
            risk_str = "Low"
        elif str(raw_tier).strip() in ['2', 'Medium']:
            tier_int = 2
            risk_str = "Medium"
        else:
            tier_int = 3
            risk_str = "High"
        
        # Map raw material names to closest supported model feature subcategories
        raw_sub = context.get("materialLabel", "Steel Sheet (kg)")
        if "steel" in raw_sub.lower():
            sub_cat = "Steel Sheet (kg)"
        elif "aluminium" in raw_sub.lower():
            sub_cat = "Aluminium Bar (kg)"
        elif "copper" in raw_sub.lower():
            sub_cat = "Copper Wire (m)"
        elif "plastic" in raw_sub.lower() or "resin" in raw_sub.lower():
            sub_cat = "Plastic Resin (kg)"
        else:
            sub_cat = "Steel Sheet (kg)"
        
        # Map SPARQL camelCase keys to match dataset headers
        mapped_context = {
            "PO Type": context.get("poType", "Standard"),
            "Supplier Region": context.get("supplierRegion", "Asia"),
            "Supplier Tier": tier_int,
            "Supplier Risk": risk_str,
            "Payment Terms": context.get("paymentTerms", "Net 30"),
            "Category": "Raw Materials",
            "Sub Category": sub_cat,
            "Unit of Measure": context.get("unitOfMeasure", "KG"),
            "Unit Price": context.get("hasUnitCost", 6.55),
            "Quantity": context.get("quantity", 41),
            "Discount Pct": context.get("discountPct", 0),
            "Tax Pct": context.get("taxPct", 5),
            "Line Net": context.get("lineNet", 268.55),
            "Currency": context.get("hasCurrency", "GBP"),
            "Savings Pct": context.get("savingsPct", 7.7),
            "Lead Time Days": context.get("leadTimeDays", 50),
            "Department": context.get("department", "IT"),
            "Contract Type": context.get("contractType", "Framework"),
            "Maverick Spend": context.get("maverickSpend", "No"),
            "Single Source Flag": context.get("singleSourceFlag", "No"),
            "Preferred Supplier": context.get("preferredSupplier", "Yes"),
            "Local International": context.get("localInternational", "International"),
            "Supplier ESG Score": context.get("esgScore", 41.6),
            "PO_Month_Num": 5,
            "PO_DayOfWeek": 3
        }
        return mapped_context
    return None


def get_delivery_context(delivery_id: str) -> dict:
    """Retrieves context from GraphDB, returning None on failure."""
    try:
        context = query_graphdb_context(delivery_id)
        if context:
            print(f"[+] Loaded context for {delivery_id} from live GraphDB.")
            return context
        else:
            print(f"[-] No context found for {delivery_id} in GraphDB.")
    except Exception as e:
        print(f"[!] GraphDB error while loading context for {delivery_id}: {e}")
        
    return None


# =====================================================================
# 3. REAL-TIME STREAM PREDICTION RUNNER
# =====================================================================

def execute_stream_prediction(event: dict, model, scaler, feature_cols, debug=False):
    """Processes a telemetry event, runs model prediction, and calls the API if delayed."""
    delivery_id = event["delivery_id"]
    status = event["status_code"]
    
    print(f"\n>> Ingested Telemetry for {delivery_id} | Status: {status} | Weather: {event['weather_condition']}")
    
    # Trigger prediction only if shipment is active and telemetry indicates an anomaly/stoppage
    is_active_shipment = status in ["Shipped", "In_Transit"]
    is_telemetry_anomaly = is_active_shipment and (
        event.get("weather_condition") in ["Storm", "Heavy Snow"] or
        event.get("current_speed_kmh", 80.0) == 0.0 or
        event.get("disruption_probability", 0.0) > 0.50
    )
    
    if not is_telemetry_anomaly:
        print(f"    [+] Telemetry is nominal. No action needed.")
        return
        
    print(f"    [!] Telemetry anomaly detected (Weather: {event['weather_condition']}, Speed: {event.get('current_speed_kmh')} km/h, Telemetry Disruption Prob: {event.get('disruption_probability', 0.0)}). Running ML risk evaluation...")
        
    # Retrieve contextual properties for the delivery
    context = get_delivery_context(delivery_id)
    if not context:
        print(f"    [-] Error: Could not resolve context for {delivery_id}. Skipping.")
        return
        
    if debug:
        print(f"    [DEBUG] Raw GraphDB Context loaded for {delivery_id}:")
        for k, v in sorted(context.items()):
            print(f"      - {k}: {v}")

    # Perform feature engineering matching the training dataset
    context['Cost_per_Day'] = context['Unit Price'] / (context['Lead Time Days'] + 1)
    context['Qty_per_Day'] = context['Quantity'] / (context['Lead Time Days'] + 1)
    
    # Extreme Lead Time flag
    # Category average from training dataset for Raw Materials is ~33 days, Maintenance is ~37 days
    cat_avg = 33.0 if context['Category'] == "Raw Materials" else 37.0
    context['Extreme_Lead_Time_Flag'] = int(context['Lead Time Days'] > (1.5 * cat_avg))
    context['Tier_LeadTime_Interaction'] = context['Supplier Tier'] * context['Lead Time Days']
    context['High_Value_Order'] = int(context['Line Net'] > 60000.0)
    
    if debug:
        print("    [DEBUG] Feature Engineering derived values:")
        for feat in ['Cost_per_Day', 'Qty_per_Day', 'Extreme_Lead_Time_Flag', 'Tier_LeadTime_Interaction', 'High_Value_Order']:
            print(f"      - {feat}: {context[feat]}")

    # Reconstruct the one-hot encoded vector
    input_df = pd.DataFrame(0.0, index=[0], columns=feature_cols)
    
    # Fill numerical values
    numerical_cols = [
        'Unit Price', 'Quantity', 'Discount Pct', 'Tax Pct',
        'Line Net', 'Savings Pct', 'Lead Time Days', 'Supplier ESG Score',
        'Supplier Tier', 'PO_Month_Num', 'PO_DayOfWeek',
        'Cost_per_Day', 'Qty_per_Day', 'Tier_LeadTime_Interaction'
    ]
    
    # Scale numerical values
    scaled_nums = scaler.transform([[context[col] for col in numerical_cols]])[0]
    for col, val in zip(numerical_cols, scaled_nums):
        input_df.loc[0, col] = val
        
    if debug:
        print("    [DEBUG] Scaled Numerical Features (passed to RF Model):")
        for col, val in zip(numerical_cols, scaled_nums):
            print(f"      - {col}: {val:.4f} (Raw: {context[col]})")

    # Set categorical dummy columns to 1
    # Example: context["PO Type"] = "Standard" -> column "PO Type_Standard" = 1
    categorical_source_fields = [
        ('PO Type', 'PO Type'),
        ('Supplier Region', 'Supplier Region'),
        ('Supplier Risk', 'Supplier Risk'),
        ('Payment Terms', 'Payment Terms'),
        ('Category', 'Category'),
        ('Sub Category', 'Sub Category'),
        ('Unit of Measure', 'Unit of Measure'),
        ('Currency', 'Currency'),
        ('Department', 'Department'),
        ('Contract Type', 'Contract Type'),
        ('Maverick Spend', 'Maverick Spend'),
        ('Single Source Flag', 'Single Source Flag'),
        ('Preferred Supplier', 'Preferred Supplier'),
        ('Local International', 'Local International')
    ]
    
    for field_name, header in categorical_source_fields:
        val = str(context[field_name])
        col_name = f"{header}_{val}"
        if col_name in input_df.columns:
            input_df.loc[0, col_name] = 1
            
    if debug:
        active_cats = [col for col in feature_cols if col not in numerical_cols and input_df.loc[0, col] == 1.0]
        print("    [DEBUG] Active One-Hot Encoded Categorical Features (value=1.0):")
        for col in sorted(active_cats):
            print(f"      - {col}")

    # Run Inference
    on_time_prob = model.predict_proba(input_df)[0][1]
    print(f"    [i] ML Model On-Time Confidence: {on_time_prob*100:.2f}%")
    
    # Apply risk-averse thresholding
    if on_time_prob < 0.65:
        disruption_prob = round(1.0 - on_time_prob, 2)
        
        # Dynamically predict the delay hours based on ML output & GraphDB lead time
        # We estimate the delay duration as a percentage of the SLA lead time, scaled by the disruption probability
        lead_time_days = context.get('Lead Time Days', 3.0)
        estimated_delay = max(24, int(disruption_prob * lead_time_days * 24 * 0.20))
        
        # Dynamically classify the reason code based on active telemetry weather status
        weather = event.get("weather_condition", "Clear")
        if weather in ["Storm", "Heavy Snow", "Windy", "Light Rain"]:
            reason = "Transport/Weather"
        else:
            reason = "Carrier_Issue"
        
        print(f"    [!] RISK FLAGGED! Delay predicted (Disruption Prob: {disruption_prob}). Invoking API...")
        
        # Trigger backend simulation
        payload = {
            "delivery_id": delivery_id,
            "estimated_delay_hours": int(estimated_delay),
            "reason_code": reason,
            "disruption_probability": float(disruption_prob),
            "timestamp": event["discovery_timestamp"]
        }
        
        try:
            res = requests.post(BACKEND_URL, json=payload, timeout=60)
            if res.status_code == 200:
                print(f"    [+] API Success: Alarm generated securely.")
                alert_text = res.json().get("alert_text", "None")
                try:
                    print("    [+] Alert text:", alert_text)
                except UnicodeEncodeError:
                    clean_text = alert_text.encode('ascii', errors='replace').decode('ascii')
                    print("    [+] Alert text:", clean_text)
            else:
                print(f"    [!] API Warning: Backend returned status code {res.status_code}")
                print(res.text)
        except Exception as err:
            if isinstance(err, UnicodeEncodeError):
                # If UnicodeEncodeError happened outside the inner print block
                pass
            else:
                print(f"    [!] API Error: Could not connect to backend server: {err}")
    else:
         print("    [+] Delivery predicted to arrive on time. No alert triggered.")


def verify_model_performance():
    """Evaluates the trained model against the historical test set and prints metrics."""
    print("\n" + "=" * 60)
    print("  MODEL ACCURACY & PERFORMANCE VERIFICATION")
    print("=" * 60)
    
    if not os.path.exists(DATASET_PATH):
        print(f"[-] Error: Historical dataset '{DATASET_PATH}' is missing. Cannot verify model.")
        return
        
    if not os.path.exists(MODEL_PATH) or not os.path.exists(SCALER_PATH) or not os.path.exists(FEATURES_PATH):
        print("[-] Error: Model assets are not trained/serialized yet. Training them now...")
        train_and_export_model()
        
    # Load model and scaler
    with open(MODEL_PATH, 'rb') as f:
        model = pickle.load(f)
    with open(SCALER_PATH, 'rb') as f:
        scaler = pickle.load(f)
    with open(FEATURES_PATH, 'r') as f:
        feature_cols = json.load(f)
        
    df = pd.read_csv(DATASET_PATH)
    
    # 1. Feature Engineering matching training
    df['Cost_per_Day'] = df['Unit Price'] / (df['Lead Time Days'] + 1)
    df['Qty_per_Day'] = df['Quantity'] / (df['Lead Time Days'] + 1)
    category_lead_time_mean = df.groupby('Category')['Lead Time Days'].transform('mean')
    df['Extreme_Lead_Time_Flag'] = (df['Lead Time Days'] > (1.5 * category_lead_time_mean)).astype(int)
    df['Tier_LeadTime_Interaction'] = df['Supplier Tier'] * df['Lead Time Days']
    line_net_75 = df['Line Net'].quantile(0.75)
    df['High_Value_Order'] = (df['Line Net'] > line_net_75).astype(int)
    
    df = df.drop(columns=['Supplier Status', 'Budget Unit Price'])
    
    # 2. One-Hot Encoding
    categorical_cols = df.select_dtypes(include=['object']).columns.tolist()
    df_encoded = pd.get_dummies(df, categorical_cols, drop_first=True)
    
    # Ensure columns match features list
    X = df_encoded.drop(columns=['Target_OnTimeDelivery'])
    y = df_encoded['Target_OnTimeDelivery']
    
    # Align columns to what model expects
    X = X.reindex(columns=feature_cols, fill_value=0)
    
    # Split using same random state to evaluate on same test set
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    # Scale test set
    numerical_cols = [
        'Unit Price', 'Quantity', 'Discount Pct', 'Tax Pct',
        'Line Net', 'Savings Pct', 'Lead Time Days', 'Supplier ESG Score',
        'Supplier Tier', 'PO_Month_Num', 'PO_DayOfWeek',
        'Cost_per_Day', 'Qty_per_Day', 'Tier_LeadTime_Interaction'
    ]
    X_test_scaled = X_test.copy()
    X_test_scaled[numerical_cols] = scaler.transform(X_test[numerical_cols])
    
    # Predictions
    y_pred = model.predict(X_test_scaled)
    y_prob = model.predict_proba(X_test_scaled)[:, 1]
    
    # Print Metrics
    print("\n[+] Classification Report (1 = On-Time, 0 = Delayed):")
    print(classification_report(y_test, y_pred, target_names=["Delayed", "On-Time"]))
    
    auc_score = roc_auc_score(y_test, y_prob)
    print(f"[+] ROC-AUC Score: {auc_score:.4f}")
    
    # Feature Importance
    importances = model.feature_importances_
    indices = np.argsort(importances)[::-1]
    print("\n[+] Top 10 Most Important Features:")
    for i in range(10):
        print(f"    {i+1}. {X.columns[indices[i]]}: {importances[indices[i]]:.4f}")
    print("=" * 60 + "\n")


def run_stream_simulation(debug=False):
    """Reads telemetry stream JSON and loops through events to simulate shipping stream."""
    print("\n" + "=" * 60)
    print("  SIMULATING TELEMETRY STREAM INGESTION")
    print("=" * 60)
    
    if not os.path.exists(TELEMETRY_STREAM_PATH):
        raise FileNotFoundError(f"Telemetry stream file '{TELEMETRY_STREAM_PATH}' not found.")
        
    with open(TELEMETRY_STREAM_PATH, "r") as f:
        events = json.load(f)
        
    # Ensure model is trained
    if not os.path.exists(MODEL_PATH) or not os.path.exists(SCALER_PATH) or not os.path.exists(FEATURES_PATH):
        train_and_export_model()
        
    with open(MODEL_PATH, 'rb') as f:
        model = pickle.load(f)
    with open(SCALER_PATH, 'rb') as f:
        scaler = pickle.load(f)
    with open(FEATURES_PATH, 'r') as f:
        feature_cols = json.load(f)
        
    print(f"[*] Successfully loaded model, scaler, and {len(feature_cols)} features.")
    print(f"[*] Processing {len(events)} telemetry events...")
    
    for event in events:
        execute_stream_prediction(event, model, scaler, feature_cols, debug=debug)
        
    print("\n" + "=" * 60)
    print("  STREAM SIMULATION INGESTION COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    # Setup warnings filter for cleaner console outputs
    import warnings
    warnings.filterwarnings("ignore", category=UserWarning)
    
    import sys
    if "--verify" in sys.argv:
        verify_model_performance()
    else:
        # Run the stream simulation
        debug_mode = "--debug" in sys.argv
        run_stream_simulation(debug=debug_mode)
