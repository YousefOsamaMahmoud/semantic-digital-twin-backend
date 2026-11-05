 # =====================================================================
# services/order_risk_service.py — Layer 2: Order Risk Assessment
#
# Predicts delay risks for proposed Purchase Orders before they are placed.
# Loads the pre-trained Procurement Classifier and queries GraphDB 
# for SLA rules to perform full 109-feature engineering.
# =====================================================================

import os
import pickle
import json
import logging
import numpy as np
import pandas as pd

from knowledge_base.connection import graphdb
from knowledge_base.repository import PREFIXES, _sanitize_uri_fragment
from models.schemas import OrderRiskPredictionRequest, OrderRiskPredictionResponse

logger = logging.getLogger(__name__)

# --- Global Asset Cache ---
_MODEL = None
_SCALER = None
_FEATURES = None

def _load_ml_assets():
    """Lazy-loads and caches model, scaler, and feature lists."""
    global _MODEL, _SCALER, _FEATURES
    logger.info("Inside _load_ml_assets: _MODEL=%s, _SCALER=%s, _FEATURES=%s",
                _MODEL is not None, _SCALER is not None, _FEATURES is not None)
    if _MODEL is None or _SCALER is None or _FEATURES is None:
        dir_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        assets_dir = os.path.join(dir_path, "models", "ml_assets")
        
        model_path = os.path.join(assets_dir, "delay_prediction_model.pkl")
        scaler_path = os.path.join(assets_dir, "scaler.pkl")
        features_path = os.path.join(assets_dir, "model_features.json")
        
        logger.info("Loading ML assets from: %s", assets_dir)
        try:
            with open(model_path, "rb") as f:
                model = pickle.load(f)
            logger.info("Loaded model successfully")
            with open(scaler_path, "rb") as f:
                scaler = pickle.load(f)
            logger.info("Loaded scaler successfully")
            with open(features_path, "r") as f:
                features = json.load(f)
            logger.info("Loaded features successfully, count=%d", len(features) if features else 0)
            
            _MODEL = model
            _SCALER = scaler
            _FEATURES = features
            logger.info("Assigned global variables successfully: _FEATURES is None: %s", _FEATURES is None)
        except Exception as e:
            logger.error("Failed to load ML assets: %s", e)
            raise e

def _get_sparql_ref(uri_or_id: str) -> str:
    """Format a string ID to be a safe SPARQL URI reference."""
    if uri_or_id.startswith("http://") or uri_or_id.startswith("https://"):
        return f"<{uri_or_id}>"
    if uri_or_id.startswith(":"):
        return uri_or_id
    # Sanitize and prefix
    return f":{_sanitize_uri_fragment(uri_or_id)}"

def query_order_context(supplier_id: str, material_id: str) -> dict:
    """Queries GraphDB to fetch supplier characteristics & SLA rules."""
    sup_ref = _get_sparql_ref(supplier_id)
    mat_ref = _get_sparql_ref(material_id)

    query = f"""{PREFIXES}
    SELECT ?poType ?supplierRegion ?supplierTier ?paymentTerms ?materialLabel
           ?unitOfMeasure ?hasUnitCost ?discountPct ?taxPct ?savingsPct ?leadTimeDays 
           ?department ?contractType ?maverickSpend ?singleSourceFlag 
           ?preferredSupplier ?localInternational ?esgScore ?hasCurrency
    WHERE {{
        {sup_ref} a :Supplier .
        {mat_ref} a :RawMaterial .
        
        # Link supplier and material
        {{ {sup_ref} :supplies {mat_ref} }} UNION {{ {mat_ref} :isSuppliedBy {sup_ref} }}
        
        # Get label of material
        OPTIONAL {{ {mat_ref} rdfs:label ?materialLabel . }}
        
        # Get SLA properties from supplier
        OPTIONAL {{ {sup_ref} :hasReliabilityTier ?supplierTier }}
        OPTIONAL {{ {sup_ref} :hasReliabilityScore ?esgScore }}
        OPTIONAL {{ 
            ?contract rdf:type :SLAContract ;
                      :hasSupplier {sup_ref} ;
                      :governsMaterial ?material ;
                      :leadTimeDays ?leadTimeDays .
        }}
        OPTIONAL {{ {sup_ref} :penaltyClause ?penaltyRate }}
        
        # Fallback to existing delivery events to fetch region/type defaults if present
        OPTIONAL {{
            ?delivery :transports {mat_ref} .
            OPTIONAL {{ ?delivery :poType ?poType }}
            OPTIONAL {{ ?delivery :supplierRegion ?supplierRegion }}
            OPTIONAL {{ ?delivery :paymentTerms ?paymentTerms }}
            OPTIONAL {{ ?delivery :unitOfMeasure ?unitOfMeasure }}
            OPTIONAL {{ ?delivery :hasUnitCost ?hasUnitCost }}
            OPTIONAL {{ ?delivery :discountPct ?discountPct }}
            OPTIONAL {{ ?delivery :taxPct ?taxPct }}
            OPTIONAL {{ ?delivery :savingsPct ?savingsPct }}
            OPTIONAL {{ ?delivery :department ?department }}
            OPTIONAL {{ ?delivery :contractType ?contractType }}
            OPTIONAL {{ ?delivery :maverickSpend ?maverickSpend }}
            OPTIONAL {{ ?delivery :singleSourceFlag ?singleSourceFlag }}
            OPTIONAL {{ ?delivery :preferredSupplier ?preferredSupplier }}
            OPTIONAL {{ ?delivery :localInternational ?localInternational }}
            OPTIONAL {{ ?delivery :hasCurrency ?hasCurrency }}
        }}
    }}
    LIMIT 1
    """
    
    results = graphdb.execute_sparql_select(query)
    if not results:
        logger.warning("No context found for %s and %s in GraphDB. Using default contexts.", supplier_id, material_id)
        # Default fallback values matching a typical profile
        return {
            "poType": "Standard",
            "supplierRegion": "Europe",
            "supplierTier": 1,
            "paymentTerms": "Net 30",
            "materialLabel": "Steel Sheet (kg)",
            "unitOfMeasure": "KG",
            "discountPct": 0.0,
            "taxPct": 5.0,
            "savingsPct": 5.0,
            "leadTimeDays": 30,
            "department": "Operations",
            "contractType": "Framework",
            "maverickSpend": "No",
            "singleSourceFlag": "No",
            "preferredSupplier": "Yes",
            "localInternational": "Local",
            "esgScore": 75.0,
            "hasCurrency": "GBP"
        }
    
    row = results[0]
    # Build clean output dictionary with type-casting and defaults
    context = {
        "poType": row.get("poType", "Standard"),
        "supplierRegion": row.get("supplierRegion", "Europe"),
        "supplierTier": int(float(row.get("supplierTier", 1))) if row.get("supplierTier") else 1,
        "paymentTerms": row.get("paymentTerms", "Net 30"),
        "materialLabel": row.get("materialLabel", "Steel Sheet (kg)"),
        "unitOfMeasure": row.get("unitOfMeasure", "KG"),
        "discountPct": float(row.get("discountPct", 0.0)),
        "taxPct": float(row.get("taxPct", 5.0)),
        "savingsPct": float(row.get("savingsPct", 5.0)),
        "leadTimeDays": int(float(row.get("leadTimeDays", 30))) if row.get("leadTimeDays") else 30,
        "department": row.get("department", "Operations"),
        "contractType": row.get("contractType", "Framework"),
        "maverickSpend": row.get("maverickSpend", "No"),
        "singleSourceFlag": row.get("singleSourceFlag", "No"),
        "preferredSupplier": row.get("preferredSupplier", "Yes"),
        "localInternational": row.get("localInternational", "Local"),
        "esgScore": float(row.get("esgScore", 75.0)),
        "hasCurrency": row.get("hasCurrency", "GBP")
    }
    return context

def predict_order_risk(request: OrderRiskPredictionRequest) -> OrderRiskPredictionResponse:
    """Evaluates the proposed order parameters and returns risk probability + explainability."""
    # Ensure assets are loaded
    _load_ml_assets()

    # 1. Fetch GraphDB context
    context = query_order_context(request.supplier_id, request.material_id)

    # 2. Extract and overwrite values with request params
    qty = request.quantity
    price = request.unit_price
    po_type = request.po_type
    dept = request.department
    
    # SLA parameters
    lead_time_days = context["leadTimeDays"]
    supplier_tier = context["supplierTier"]
    esg_score = context["esgScore"]
    
    # 3. Derive categorical subcategory & risk string
    raw_sub = context["materialLabel"]
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

    if supplier_tier == 1:
        risk_str = "Low"
    elif supplier_tier == 2:
        risk_str = "Medium"
    else:
        risk_str = "High"

    # 4. Feature Engineering
    line_net = qty * price * (1.0 - context["discountPct"] / 100.0) * (1.0 + context["taxPct"] / 100.0)
    cost_per_day = price / (lead_time_days + 1)
    qty_per_day = qty / (lead_time_days + 1)
    
    cat_avg = 33.0 if "sheet" in sub_cat.lower() or "bar" in sub_cat.lower() else 37.0
    extreme_lead_time_flag = int(lead_time_days > (1.5 * cat_avg))
    
    tier_leadtime_interaction = supplier_tier * lead_time_days
    high_value_order = int(line_net > 60000.0)

    # Date parsing
    ts = pd.to_datetime(request.po_date)
    month_num = ts.month
    day_of_week = ts.dayofweek

    # Assemble explainability features used (Behind the Scenes data)
    explainability_data = {
        "quantity": qty,
        "unit_price": price,
        "line_net": round(line_net, 2),
        "lead_time_days": lead_time_days,
        "supplier_tier": supplier_tier,
        "supplier_risk": risk_str,
        "supplier_esg_score": esg_score,
        "supplier_region": context["supplierRegion"],
        "payment_terms": context["paymentTerms"],
        "contract_type": context["contractType"],
        "cost_per_day": round(cost_per_day, 4),
        "qty_per_day": round(qty_per_day, 4),
        "extreme_lead_time_flag": extreme_lead_time_flag,
        "high_value_order": high_value_order,
        "tier_leadtime_interaction": tier_leadtime_interaction,
        "po_month": month_num,
        "po_dayofweek": day_of_week
    }

    # 5. Build full 109-feature dataframe
    features_dict = {feat: 0.0 for feat in _FEATURES}

    # Fill numerical fields
    features_dict["Unit Price"] = price
    features_dict["Quantity"] = qty
    features_dict["Discount Pct"] = context["discountPct"]
    features_dict["Tax Pct"] = context["taxPct"]
    features_dict["Line Net"] = line_net
    features_dict["Savings Pct"] = context["savingsPct"]
    features_dict["Lead Time Days"] = lead_time_days
    features_dict["Supplier ESG Score"] = esg_score
    features_dict["Supplier Tier"] = supplier_tier
    features_dict["PO_Month_Num"] = month_num
    features_dict["PO_DayOfWeek"] = day_of_week
    features_dict["Cost_per_Day"] = cost_per_day
    features_dict["Qty_per_Day"] = qty_per_day
    features_dict["Tier_LeadTime_Interaction"] = tier_leadtime_interaction

    # Fill numerical engineered flags
    if "Extreme_Lead_Time_Flag" in features_dict:
        features_dict["Extreme_Lead_Time_Flag"] = float(extreme_lead_time_flag)
    if "High_Value_Order" in features_dict:
        features_dict["High_Value_Order"] = float(high_value_order)

    # Scale the numerical fields in-place using scaler
    numerical_cols = [
        'Unit Price', 'Quantity', 'Discount Pct', 'Tax Pct',
        'Line Net', 'Savings Pct', 'Lead Time Days', 'Supplier ESG Score',
        'Supplier Tier', 'PO_Month_Num', 'PO_DayOfWeek',
        'Cost_per_Day', 'Qty_per_Day', 'Tier_LeadTime_Interaction'
    ]
    numerical_vals = [features_dict[col] for col in numerical_cols]
    scaled_vals = _SCALER.transform([numerical_vals])[0]
    for col, val in zip(numerical_cols, scaled_vals):
        features_dict[col] = val

    # Helper function to check and set dummy variables to 1.0
    def set_dummy(header, val):
        col_name = f"{header}_{val}"
        if col_name in features_dict:
            features_dict[col_name] = 1.0

    # Fill Categorical dummy fields
    set_dummy("PO Type", po_type)
    set_dummy("Supplier Region", context["supplierRegion"])
    set_dummy("Supplier Risk", risk_str)
    set_dummy("Payment Terms", context["paymentTerms"])
    set_dummy("Category", "Raw Materials")
    set_dummy("Sub Category", sub_cat)
    set_dummy("Unit of Measure", context["unitOfMeasure"])
    set_dummy("Currency", context["hasCurrency"])
    set_dummy("Department", dept)
    set_dummy("Contract Type", context["contractType"])
    set_dummy("Maverick Spend", context["maverickSpend"])
    set_dummy("Single Source Flag", context["singleSourceFlag"])
    set_dummy("Preferred Supplier", context["preferredSupplier"])
    set_dummy("Local International", context["localInternational"])

    # 6. Run Inference
    input_df = pd.DataFrame([features_dict], columns=_FEATURES)
    on_time_prob = float(_MODEL.predict_proba(input_df)[0][1])

    # Apply threshold to classify risk level and delay hours
    if on_time_prob < 0.65:
        risk_level = "High"
        # Delay estimated as 20% of contract lead time, min 24 hours
        estimated_delay = max(24, int((1.0 - on_time_prob) * lead_time_days * 24 * 0.20))
    else:
        risk_level = "Low"
        estimated_delay = 0

    logger.info("Order risk predicted successfully: On-Time Prob = %.2f%% | Risk Level = %s", on_time_prob * 100, risk_level)

    # ── Bridge: If HIGH risk, inject a Delayed DeliveryEvent into GraphDB ──────
    # This connects the ML prediction to the dashboard's at-risk panel and
    # fallback supplier workflow automatically.
    if risk_level == "High" and estimated_delay > 0:
        try:
            _inject_high_risk_delay(request.supplier_id, request.material_id, estimated_delay, on_time_prob)
        except Exception as exc:
            logger.warning("ML→GraphDB bridge injection failed (non-critical): %s", exc)

    return OrderRiskPredictionResponse(
        status="success",
        on_time_probability=on_time_prob,
        risk_level=risk_level,
        estimated_delay_hours=estimated_delay,
        features_used=explainability_data
    )

# Force reload triggers (asset update verification)


def _inject_high_risk_delay(supplier_id: str, material_id: str, delay_hours: int, probability: float) -> None:
    """
    Injects a Delayed DeliveryEvent into GraphDB when the ML model predicts High risk.
    This bridges the order risk predictor to the dashboard's at-risk / fallback workflow.
    """
    import time as _time
    sup_uri = _sanitize_uri_fragment(supplier_id)
    mat_uri = _sanitize_uri_fragment(material_id)
    # Unique delivery URI based on supplier+material+timestamp to avoid duplicates
    delivery_uri = f"MLRisk_{sup_uri}_{mat_uri}_{int(_time.time())}"

    # First, look up the real material node URI (it might have spaces or special chars)
    mat_esc = material_id.replace('"', '\\"')
    lookup_q = f"""{PREFIXES}
    SELECT ?mat ?process WHERE {{
        ?mat rdf:type :RawMaterial .
        OPTIONAL {{ ?mat rdfs:label ?ml . }}
        FILTER(STR(?ml) = "{mat_esc}" || REPLACE(STR(?mat), "^.*#", "") = "{mat_uri}")
        OPTIONAL {{
            ?mat :affectsProcess ?process .
            ?process rdf:type :ProductionProcess .
        }}
    }} LIMIT 1
    """
    rows = graphdb.execute_sparql_select(lookup_q)
    if rows:
        mat_ref = f"<{rows[0]['mat']}>" if rows[0].get("mat") else f":{mat_uri}"
        proc_ref = f"<{rows[0]['process']}>" if rows[0].get("process") else None
    else:
        mat_ref = f":{mat_uri}"
        proc_ref = None

    # Build the INSERT: create a delivery event and mark it delayed
    proc_triple = f"\n            {proc_ref} rdf:type :ProductionDisruption ." if proc_ref else ""

    insert_q = f"""
    PREFIX : <http://example.org/ontology#>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
    INSERT DATA {{
        GRAPH <http://example.org/contracts/> {{
            :{delivery_uri} rdf:type :DeliveryEvent ;
                            :transports {mat_ref} ;
                            :hasDeliveryStatus "Delayed"^^xsd:string ;
                            :hasDelayDuration {delay_hours} ;
                            :hasRiskSource "ML_OrderRisk"^^xsd:string ;
                            :hasProbability "{probability:.4f}"^^xsd:float .{proc_triple}
        }}
    }}
    """
    graphdb.execute_sparql_update(insert_q)
    logger.info(
        "ML→GraphDB: Injected High-Risk delay event :%s for material %s (delay=%dh, prob=%.0f%%)",
        delivery_uri, material_id, delay_hours, probability * 100
    )
