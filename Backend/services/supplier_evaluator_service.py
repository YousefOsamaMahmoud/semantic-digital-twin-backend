# ============================================================
# services/supplier_evaluator_service.py — Layer 2: Service
#
# This module implements the batch supplier reliability
# evaluator, parsing uploaded datasets (Excel/CSV), calculating
# performance scores (decaying delays, costs, risks, ESG, etc.),
# mapping them to GraphDB supplier individuals, and persisting
# the scores.
# ============================================================

import io
import logging
import numpy as np
import pandas as pd
from knowledge_base.repository import get_active_suppliers, update_supplier_reliability_score

logger = logging.getLogger(__name__)


def evaluate_and_update_suppliers(file_bytes: bytes, filename: str) -> dict:
    """
    Parses a procurement spreadsheet (Excel or CSV), calculates supplier
    performance scores using exponential delay penalties, recency decay,
    and multi-criteria weights, maps the suppliers to GraphDB, and updates
    their reliability scores via SPARQL.
    """
    # 1. Load DataFrame
    try:
        if filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(file_bytes))
        else:
            try:
                df = pd.read_csv(io.BytesIO(file_bytes))
            except UnicodeDecodeError:
                df = pd.read_csv(io.BytesIO(file_bytes), encoding="latin-1")
    except Exception as e:
        logger.error("Failed to parse file %s: %s", filename, e)
        raise ValueError(f"Failed to parse dataset file: {e}")

    logger.info("Loaded dataset with %d rows and %d columns", len(df), len(df.columns))

    # Helper function to find a column with fallback names (case-insensitive)
    def find_col(possible_names, default_name=None):
        for col in df.columns:
            if str(col).strip().lower() in [n.lower() for n in possible_names]:
                return col
        return default_name

    # Identify and rename target columns
    col_mappings = {
        "Supplier ID": find_col(["Supplier ID", "Supplier_ID", "SupplierID"]),
        "Supplier Name": find_col(["Supplier Name", "Supplier_Name", "SupplierName", "Supplier"]),
        "Days Late": find_col(["Days Late", "DaysLate", "Days_Late", "Delay"]),
        "Lead Time Days": find_col(["Lead Time Days", "LeadTimeDays", "Lead_Time_Days", "LeadTime"]),
        "On Time Delivery": find_col(["On Time Delivery", "OnTimeDelivery", "Target_OnTimeDelivery", "On_Time_Delivery"]),
        "Unit Price": find_col(["Unit Price", "UnitPrice", "Unit_Price", "Price"]),
        "Discount Pct": find_col(["Discount Pct", "DiscountPct", "Discount_Pct", "Discount"]),
        "Supplier Risk": find_col(["Supplier Risk", "SupplierRisk", "Supplier_Risk", "Risk"]),
        "Preferred Supplier": find_col(["Preferred Supplier", "PreferredSupplier", "Preferred_Supplier", "Preferred"]),
        "Single Source Flag": find_col(["Single Source Flag", "SingleSourceFlag", "SingleSource", "Single_Source"]),
        "Supplier Tier": find_col(["Supplier Tier", "SupplierTier", "Supplier_Tier", "Tier"]),
        "Supplier ESG Score": find_col(["Supplier ESG Score", "SupplierESGScore", "Supplier_ESG_Score", "ESGScore", "ESG"])
    }

    # Rename existing columns to standard names
    for std_name, found_name in col_mappings.items():
        if found_name and found_name != std_name:
            df[std_name] = df[found_name]

    # Create missing columns with safe defaults
    if "On Time Delivery" not in df.columns:
        df["On Time Delivery"] = 1
    else:
        df["On Time Delivery"] = df["On Time Delivery"].apply(
            lambda val: 1 if str(val).strip().lower() in ["1", "true", "yes", "on time", "1.0"] else 0
        )

    if "Days Late" not in df.columns:
        df["Days Late"] = np.where(df["On Time Delivery"] == 1, 0, 5)
    else:
        df["Days Late"] = pd.to_numeric(df["Days Late"], errors="coerce").fillna(0)

    if "Lead Time Days" not in df.columns:
        df["Lead Time Days"] = 30
    else:
        df["Lead Time Days"] = pd.to_numeric(df["Lead Time Days"], errors="coerce").fillna(30)

    if "Unit Price" not in df.columns:
        df["Unit Price"] = 10.0
    else:
        df["Unit Price"] = pd.to_numeric(df["Unit Price"], errors="coerce").fillna(10.0)

    if "Discount Pct" not in df.columns:
        df["Discount Pct"] = 0.0
    else:
        df["Discount Pct"] = pd.to_numeric(df["Discount Pct"], errors="coerce").fillna(0.0)

    if "Supplier Risk" not in df.columns:
        df["Supplier Risk"] = "Medium"
    else:
        df["Supplier Risk"] = df["Supplier Risk"].fillna("Medium").astype(str)

    if "Preferred Supplier" not in df.columns:
        df["Preferred Supplier"] = "No"
    else:
        df["Preferred Supplier"] = df["Preferred Supplier"].fillna("No").astype(str)

    if "Single Source Flag" not in df.columns:
        df["Single Source Flag"] = "No"
    else:
        df["Single Source Flag"] = df["Single Source Flag"].fillna("No").astype(str)

    if "Supplier Tier" not in df.columns:
        df["Supplier Tier"] = "Tier 2"
    else:
        df["Supplier Tier"] = df["Supplier Tier"].fillna("Tier 2").astype(str)

    if "Supplier ESG Score" not in df.columns:
        df["Supplier ESG Score"] = 60.0
    else:
        df["Supplier ESG Score"] = pd.to_numeric(df["Supplier ESG Score"], errors="coerce").fillna(60.0)

    # Query GraphDB active suppliers for mapping
    db_suppliers = get_active_suppliers()
    
    # Check if supplier identity columns exist in the parsed file
    has_supplier_id = "Supplier ID" in df.columns and df["Supplier ID"].notna().any()
    has_supplier_name = "Supplier Name" in df.columns and df["Supplier Name"].notna().any()

    # If supplier identification columns are completely missing, fall back to round-robin
    if not has_supplier_id and not has_supplier_name:
        logger.info("Supplier identification columns missing. Falling back to round-robin assignment.")
        if not db_suppliers:
            raise ValueError("No active suppliers found in GraphDB to map dataset rows to.")
        
        # Assign supplier URIs round-robin
        supplier_uris = [s["supplier"] for s in db_suppliers]
        num_rows = len(df)
        df["Mapped_Supplier_URI"] = [supplier_uris[i % len(supplier_uris)] for i in range(num_rows)]
        df["Supplier ID"] = df["Mapped_Supplier_URI"].apply(lambda uri: uri.split("#")[-1])
        df["Supplier Name"] = df["Mapped_Supplier_URI"].apply(lambda uri: uri.split("#")[-1].replace("_", " "))
    else:
        if not db_suppliers:
            raise ValueError("No active suppliers found in GraphDB to map dataset rows to.")

        # Helper mapping function for a given row
        def map_row_to_supplier_uri(row):
            s_name = str(row.get("Supplier Name", "")).strip() if pd.notna(row.get("Supplier Name")) else ""
            s_id = str(row.get("Supplier ID", "")).strip() if pd.notna(row.get("Supplier ID")) else ""

            # 1. Try exact name match
            if s_name:
                for db_s in db_suppliers:
                    db_name = db_s.get("name") or db_s.get("label") or ""
                    if db_name.strip().lower() == s_name.lower():
                        return db_s["supplier"]
            
            # 2. Try exact ID match
            if s_id:
                clean_id = s_id.replace("-", "_").lower()
                for db_s in db_suppliers:
                    db_uri = db_s["supplier"]
                    db_suffix = db_uri.split("#")[-1].lower()
                    if db_suffix == clean_id or db_suffix == f"supplier_{clean_id}":
                        return db_s["supplier"]
            
            # 3. Try partial name match (substring)
            if s_name:
                for db_s in db_suppliers:
                    db_name = db_s.get("name") or db_s.get("label") or ""
                    if s_name.lower() in db_name.lower() or db_name.lower() in s_name.lower():
                        return db_s["supplier"]

            # 4. Fallback based on typical supplier structures
            if s_name:
                if "global" in s_name.lower():
                    for db_s in db_suppliers:
                        if "incumbent" in db_s["supplier"].lower():
                            return db_s["supplier"]
                if "eco" in s_name.lower() or "alternative" in s_name.lower():
                    for db_s in db_suppliers:
                        if "alternative" in db_s["supplier"].lower():
                            return db_s["supplier"]
                if "local" in s_name.lower() or "backup" in s_name.lower() or "city" in s_name.lower():
                    for db_s in db_suppliers:
                        if "local_backup" in db_s["supplier"].lower():
                            return db_s["supplier"]

            # 5. Last fallback: construct one using ID
            if s_id:
                sanitised_id = s_id.replace("-", "_")
                for db_s in db_suppliers:
                    if sanitised_id.lower() in db_s["supplier"].lower():
                        return db_s["supplier"]
                return f"http://example.org/ontology#Supplier_{sanitised_id}"

            return db_suppliers[0]["supplier"]

        df["Mapped_Supplier_URI"] = df.apply(map_row_to_supplier_uri, axis=1)

    # =========================
    # CALCULATIONS
    # =========================
    # 1. Recency Weighting
    df["Recency_Weight"] = np.linspace(1.0, 0.5, len(df))

    # 2. Performance Scores
    df["Delivery Score"] = 100 * np.exp(-df["Days Late"] / 5)
    df["Lead Time Score"] = 100 * np.exp(-df["Lead Time Days"] / 40)
    df["On Time Score"] = np.where(df["On Time Delivery"] == 1, 100, 50)

    # 3. Cost Score
    mean_price = df["Unit Price"].mean()
    if mean_price == 0:
        mean_price = 1.0
    df["Price Score"] = 100 * np.exp(-df["Unit Price"] / mean_price)

    max_discount = df["Discount Pct"].max()
    df["Discount Score"] = 100 * (df["Discount Pct"] / (max_discount + 1.0))

    df["Cost Score"] = (
        0.7 * df["Price Score"] +
        0.3 * df["Discount Score"]
    )

    # 4. Risk Score
    risk_map = {"low": 100, "medium": 60, "high": 20}
    df["Risk Score"] = df["Supplier Risk"].apply(lambda r: risk_map.get(str(r).strip().lower(), 60))

    # 5. Strategic Score
    pref_score = np.where(df["Preferred Supplier"].astype(str).str.lower().isin(["yes", "1", "true"]), 40, 0)
    single_score = np.where(df["Single Source Flag"].astype(str).str.lower().isin(["no", "0", "false"]), 20, 0)
    
    tier_map = {"tier 1": 40, "tier 2": 25, "tier 3": 10}
    tier_score = df["Supplier Tier"].apply(lambda t: tier_map.get(str(t).strip().lower(), 0))
    
    df["Strategic Score"] = pref_score + single_score + tier_score

    # 6. ESG Score
    df["ESG Score"] = df["Supplier ESG Score"]

    # 7. Final Transaction Score
    df["Transaction Score"] = (
        0.35 * df["Delivery Score"] +
        0.15 * df["Lead Time Score"] +
        0.20 * df["Cost Score"] +
        0.15 * df["Risk Score"] +
        0.10 * df["Strategic Score"] +
        0.05 * df["ESG Score"]
    )

    # Apply recency weight
    df["Transaction Score"] = df["Transaction Score"] * df["Recency_Weight"]

    # 8. Aggregation per supplier URI
    supplier_agg = df.groupby("Mapped_Supplier_URI").agg(
        Raw_Score=("Transaction Score", "mean"),
        Total_Orders=("Mapped_Supplier_URI", "count"),
        Avg_ESG=("ESG Score", "mean"),
        Avg_Days_Late=("Days Late", "mean"),
        Avg_Lead_Time=("Lead Time Days", "mean")
    ).reset_index()

    # 9. Use raw score directly (remove min-max normalization)
    supplier_agg["Normalized_Score"] = supplier_agg["Raw_Score"]


    # 10. Supplier Tiering (A/B/C Classification)
    def calculate_tier(score):
        if score >= 80:
            return "A (Preferred)"
        elif score >= 60:
            return "B (Approved)"
        else:
            return "C (Risk)"

    supplier_agg["Tier"] = supplier_agg["Normalized_Score"].apply(calculate_tier)

    # Match results and trigger GraphDB update
    report_updates = []
    
    for _, row in supplier_agg.iterrows():
        supplier_uri = row["Mapped_Supplier_URI"]
        supplier_id = supplier_uri.split("#")[-1]

        # Find supplier name from GraphDB or DataFrame
        db_match = [s for s in db_suppliers if s["supplier"] == supplier_uri]
        supplier_name = ""
        old_score = None
        if db_match:
            supplier_name = db_match[0].get("name") or db_match[0].get("label") or ""
            old_score_val = db_match[0].get("oldScore")
            if old_score_val is not None:
                try:
                    old_score = float(old_score_val)
                except ValueError:
                    old_score = old_score_val
        
        if not supplier_name:
            df_match = df[df["Mapped_Supplier_URI"] == supplier_uri]
            if not df_match.empty:
                supplier_name = df_match.iloc[0]["Supplier Name"]
            else:
                supplier_name = supplier_id.replace("_", " ")

        # Scaled score on 0-1 scale for GraphDB hasReliabilityScore
        new_reliability_score = round(float(row["Normalized_Score"]) / 100.0, 4)

        # Trigger database update
        update_supplier_reliability_score(supplier_uri, new_reliability_score)

        report_updates.append({
            "supplier_uri": supplier_uri,
            "supplier_id": supplier_id,
            "supplier_name": supplier_name,
            "old_score": old_score,
            "new_score": new_reliability_score,
            "tier": row["Tier"],
            "total_orders": int(row["Total_Orders"]),
            "avg_esg": round(float(row["Avg_ESG"]), 2),
            "avg_days_late": round(float(row["Avg_Days_Late"]), 2),
            "avg_lead_time": round(float(row["Avg_Lead_Time"]), 2)
        })

    # 11. Assign default estimate score (0.75) for active suppliers in GraphDB with no score and no transactions in uploaded file
    uploaded_uris = set(supplier_agg["Mapped_Supplier_URI"].tolist()) if not supplier_agg.empty else set()
    for db_s in db_suppliers:
        uri = db_s["supplier"]
        if uri not in uploaded_uris:
            old_score_val = db_s.get("oldScore")
            if old_score_val is None:
                default_score = 0.75
                supplier_id = uri.split("#")[-1]
                supplier_name = db_s.get("name") or db_s.get("label") or supplier_id.replace("_", " ")
                
                # Update database
                update_supplier_reliability_score(uri, default_score)
                
                report_updates.append({
                    "supplier_uri": uri,
                    "supplier_id": supplier_id,
                    "supplier_name": supplier_name,
                    "old_score": None,
                    "new_score": default_score,
                    "tier": "Estimated (New)",
                    "total_orders": 0,
                    "avg_esg": 60.0,
                    "avg_days_late": 0.0,
                    "avg_lead_time": 30.0
                })

    return {
        "status": "success",
        "evaluated_suppliers_count": len(report_updates),
        "updates": report_updates
    }

def record_telemetry_transaction_and_update_score(delivery_id: str, delay_hours: int):
    """
    Finds the transaction for the delivery in the CSV dataset and updates its delay properties.
    If the transaction does not exist, appends it as a new transaction.
    Then triggers a recalculation of all supplier reliability scores in GraphDB.
    """
    import pandas as pd
    import os
    import datetime
    
    dir_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    dataset_path = os.path.join(dir_path, "Machine_Learning", "Procurement_Model", "Dataset_Procurement_SelectedFeatures.csv")
    
    if not os.path.exists(dataset_path):
        logger.warning("Procurement dataset not found at %s. Skipping transaction record.", dataset_path)
        return
        
    df = pd.read_csv(dataset_path)
    days_late = round(delay_hours / 24.0, 2)
    on_time = 1 if delay_hours == 0 else 0
    
    # Check if 'Delivery ID' column exists, if not create it
    if "Delivery ID" not in df.columns:
        df["Delivery ID"] = None

    # Query GraphDB for the context first (always needed for the score update step)
    from knowledge_base.connection import graphdb
    from knowledge_base.repository import PREFIXES
    
    query = f"""{PREFIXES}
    SELECT ?supplierId ?supplierName ?poType ?supplierRegion ?supplierTier ?paymentTerms 
           ?material ?materialLabel ?unitOfMeasure ?hasUnitCost ?discountPct ?taxPct ?savingsPct 
           ?leadTimeDays ?department ?contractType ?maverickSpend ?singleSourceFlag 
           ?preferredSupplier ?localInternational ?esgScore ?hasCurrency ?lineNet ?slaLeadTimeHours
    WHERE {{
        GRAPH <http://example.org/contracts/> {{
            BIND(:{delivery_id} AS ?delivery)
            ?delivery a :DeliveryEvent ;
                      :transports ?material .
            
            OPTIONAL {{ ?delivery :poType ?poType . }}
            OPTIONAL {{ ?delivery :supplierRegion ?supplierRegion . }}
            OPTIONAL {{ ?delivery :paymentTerms ?paymentTerms . }}
            OPTIONAL {{ ?delivery :unitOfMeasure ?unitOfMeasure . }}
            OPTIONAL {{ ?delivery :hasUnitCost ?hasUnitCost . }}
            OPTIONAL {{ ?delivery :discountPct ?discountPct . }}
            OPTIONAL {{ ?delivery :taxPct ?taxPct . }}
            OPTIONAL {{ ?delivery :lineNet ?lineNet . }}
            OPTIONAL {{ ?delivery :hasCurrency ?hasCurrency . }}
            OPTIONAL {{ ?delivery :savingsPct ?savingsPct . }}
            OPTIONAL {{ ?delivery :department ?department . }}
            OPTIONAL {{ ?delivery :contractType ?contractType . }}
            OPTIONAL {{ ?delivery :maverickSpend ?maverickSpend . }}
        }}
        
        # Resolve supplier using direct relationships first
        OPTIONAL {{
            GRAPH <http://example.org/contracts/> {{
                ?delivery :isPerformedBy ?perfSupplier .
            }}
            FILTER NOT EXISTS {{ ?perfSupplier rdf:type :AlternativeSupplier . }}
        }}
        OPTIONAL {{
            GRAPH <http://example.org/contracts/> {{
                ?delivery :fulfills ?po .
                ?po :issuedTo ?poSupplier .
            }}
            FILTER NOT EXISTS {{ ?poSupplier rdf:type :AlternativeSupplier . }}
        }}
        OPTIONAL {{
            {{ ?suppliesSupplier :supplies ?material . }} UNION {{ ?material :isSuppliedBy ?suppliesSupplier . }}
            FILTER NOT EXISTS {{ ?suppliesSupplier rdf:type :AlternativeSupplier . }}
        }}
        BIND(COALESCE(?perfSupplier, ?poSupplier, ?suppliesSupplier) AS ?supplier)
        FILTER(BOUND(?supplier))
        OPTIONAL {{ ?supplier rdfs:label ?sLabel . }}
        OPTIONAL {{ ?supplier :hasName ?sName . }}
        BIND(COALESCE(?sLabel, ?sName) AS ?supplierName)
        BIND(REPLACE(STR(?supplier), "^.*#", "") AS ?supplierId)
        
        OPTIONAL {{ ?supplier :hasReliabilityTier ?supplierTier . }}
        OPTIONAL {{ ?supplier :hasReliabilityScore ?esgScore . }}
        OPTIONAL {{ 
            ?contract rdf:type :SLAContract ;
                      :hasSupplier ?supplier ;
                      :governsMaterial ?material ;
                      :leadTimeDays ?leadTimeDays .
        }}
        OPTIONAL {{
            {{ ?supplier :hasSLA ?sla . }} UNION {{ ?sla :governs ?supplier . }}
            OPTIONAL {{ ?sla :hasSLALeadTime ?slaLeadTimeHours . }}
            OPTIONAL {{ ?sla :singleSourceFlag ?singleSourceFlag . }}
            OPTIONAL {{ ?sla :preferredSupplier ?preferredSupplier . }}
            OPTIONAL {{ ?sla :localInternational ?localInternational . }}
        }}
        OPTIONAL {{ ?material rdfs:label ?materialLabel . }}
    }}
    LIMIT 1
    """
    
    row = None
    try:
        results = graphdb.execute_sparql_select(query)
        if results:
            row = results[0]
    except Exception as e:
        logger.error("Failed to query GraphDB delivery context for %s: %s", delivery_id, e)
        
    # See if there's a match
    match_mask = df["Delivery ID"] == delivery_id
    if match_mask.any():
        # Update existing row
        df.loc[match_mask, "Days Late"] = days_late
        df.loc[match_mask, "Target_OnTimeDelivery"] = on_time
        logger.info("[+] Updated existing transaction in CSV for %s (Delivery ID: %s, Delay: %dh).", 
                    df.loc[match_mask, "Supplier Name"].iloc[0], delivery_id, delay_hours)
    else:
        # Append as a new row using context
        if row:
            mat_uri = row.get("material", "")
            mat_id = mat_uri.split("#")[-1] if "#" in mat_uri else mat_uri.split("/")[-1]
            material_label = row.get("materialLabel") or mat_id.replace("_", " ")

            # Parse supplier tier safely
            tier_str = str(row.get("supplierTier", "1")).strip()
            try:
                tier_val = int(float(tier_str))
            except (ValueError, TypeError):
                tier_lower = tier_str.lower()
                if "low" in tier_lower:
                    tier_val = 1
                elif "med" in tier_lower:
                    tier_val = 2
                elif "high" in tier_lower:
                    tier_val = 3
                else:
                    tier_val = 1

            now = datetime.datetime.now()
            new_data = {
                "PO Type": row.get("poType", "Standard"),
                "Supplier Region": row.get("supplierRegion", "Europe"),
                "Supplier Tier": tier_val,
                "Supplier Risk": "Low" if tier_val == 1 else "Medium" if tier_val == 2 else "High",
                "Payment Terms": row.get("paymentTerms", "Net 30"),
                "Category": "Raw Materials",
                "Sub Category": material_label,
                "Unit of Measure": row.get("unitOfMeasure", "KG"),
                "Unit Price": float(row.get("hasUnitCost", 10.0)),
                "Quantity": 100,  # Default fallback quantity
                "Discount Pct": float(row.get("discountPct", 0.0)),
                "Tax Pct": float(row.get("taxPct", 5.0)),
                "Line Net": float(row.get("lineNet", 1000.0)),
                "Currency": row.get("hasCurrency", "GBP"),
                "Savings Pct": float(row.get("savingsPct", 5.0)),
                "Lead Time Days": int(float(row.get("leadTimeDays", 30))) if row.get("leadTimeDays") else 30,
                "Department": row.get("department", "Operations"),
                "Contract Type": row.get("contractType", "Framework"),
                "Maverick Spend": row.get("maverickSpend", "No"),
                "Single Source Flag": row.get("singleSourceFlag", "No"),
                "Preferred Supplier": row.get("preferredSupplier", "Yes"),
                "Local International": row.get("localInternational", "Local"),
                "Supplier ESG Score": float(row.get("esgScore", 0.75)) * 100.0,
                "PO_Month_Num": now.month,
                "PO_DayOfWeek": now.weekday(),
                "Target_OnTimeDelivery": on_time,
                "Days Late": days_late,
                "Supplier ID": row.get("supplierId", "SUP_UNKNOWN"),
                "Supplier Name": row.get("supplierName", "Unknown Supplier"),
                "Delivery ID": delivery_id
            }
            new_row_df = pd.DataFrame([new_data])
            df = pd.concat([df, new_row_df], ignore_index=True)
            logger.info("[+] Appended new delayed transaction to CSV for %s (Delivery ID: %s, Delay: %dh).", 
                        new_data["Supplier Name"], delivery_id, delay_hours)
        else:
            logger.warning("Could not find GraphDB delivery context for %s to append transaction.", delivery_id)
            return
            
    # Save back to CSV (wrap in try-except in case file is locked by Excel/external editor)
    try:
        df.to_csv(dataset_path, index=False)
    except Exception as csv_err:
        logger.warning("[!] Could not save transaction update to CSV (file may be locked or read-only): %s. Proceeding with GraphDB score updates.", csv_err)
    
    # Direct Real-Time Score Update (Option 3):
    # Instead of running a full batch recalculation over 5,000+ rows (which dilutes a single delay
    # to less than 0.03%), apply a direct and immediate penalty to the supplier's reliability score in GraphDB.
    try:
        if row:
            supplier_id = row.get("supplierId")
            if supplier_id:
                supplier_uri = f"http://example.org/ontology#{supplier_id}"
                current_score_val = row.get("esgScore")
                current_score = float(current_score_val) if current_score_val is not None else 0.75
                
                if delay_hours > 0:
                    # Standardized dynamic penalty based on SLA Compliance (Option A)
                    lead_days_val = row.get("leadTimeDays")
                    if lead_days_val is not None:
                        lead_days = int(float(lead_days_val))
                    else:
                        sla_hours = row.get("slaLeadTimeHours")
                        if sla_hours is not None:
                            lead_days = max(1, int(float(sla_hours) / 24.0))
                        else:
                            lead_days = 14  # Safe default if no lead time is configured
                            
                    actual_delay_days = delay_hours / 24.0
                    
                    # Calculate standard SLA compliance
                    if actual_delay_days <= 2:
                        compliance = max(90.0, (1.0 - (actual_delay_days / (lead_days * 2.0))) * 100.0)
                    else:
                        severity = (actual_delay_days - 2) / lead_days
                        compliance = max(0.0, (1.0 - severity) * 90.0)
                    
                    # Tying compliance deficit to score penalty (capped at 25% max penalty)
                    penalty = round((1.0 - (compliance / 100.0)) * 0.25, 4)
                    
                    new_reliability_score = max(0.0, round(current_score - penalty, 4))
                    logger.info("[+] Real-time delay detected (%dh delay vs %d-day lead time). SLA Compliance: %.2f%%. Penalizing supplier %s by %.4f: %s -> %s", 
                                delay_hours, lead_days, compliance, supplier_uri, penalty, current_score, new_reliability_score)
                else:
                    # Slight improvement for on-time delivery completion
                    new_reliability_score = min(1.0, round(current_score + 0.01, 4))
                    logger.info("[+] Real-time delivery on-time. Supplier %s: %s -> %s", 
                                supplier_uri, current_score, new_reliability_score)
                    
                update_supplier_reliability_score(supplier_uri, new_reliability_score)
        else:
            logger.warning("No context row resolved. Skipping direct score update.")
    except Exception as e:
        logger.error("Failed to update supplier score directly in GraphDB: %s", e)

    # Invalidate the dashboard's impacted-products cache so the next page load
    # reflects the updated reliability score and delayed delivery status immediately.
    try:
        from services.dashboard_service import invalidate_impacted_cache
        invalidate_impacted_cache()
        logger.info("[+] Dashboard impacted-products cache invalidated after telemetry score update.")
    except Exception as e:
        logger.warning("[!] Could not invalidate dashboard cache: %s", e)


def record_placed_order_and_update_score(supplier_id: str, material_id: str, quantity: int, unit_price: float, po_date: str, po_type: str = "Standard", department: str = "Operations") -> str:
    """
    Records a newly placed order in the CSV dataset as an on-time transaction,
    and triggers a recalculation of all supplier reliability scores in GraphDB.
    """
    import pandas as pd
    import os
    import datetime
    from knowledge_base.connection import graphdb
    from knowledge_base.repository import PREFIXES
    
    dir_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    dataset_path = os.path.join(dir_path, "Machine_Learning", "Procurement_Model", "Dataset_Procurement_SelectedFeatures.csv")
    
    if not os.path.exists(dataset_path):
        logger.warning("Procurement dataset not found at %s. Skipping order placement record.", dataset_path)
        return ""
        
    clean_sup_id = supplier_id.split("#")[-1]
    clean_mat_id = material_id.split("#")[-1]
    
    # Query GraphDB for supplier/material details
    query = f"""{PREFIXES}
    SELECT ?supplierName ?supplierRegion ?supplierTier ?paymentTerms ?materialLabel
           ?unitOfMeasure ?discountPct ?taxPct ?savingsPct ?leadTimeDays ?contractType
           ?maverickSpend ?singleSourceFlag ?preferredSupplier ?localInternational ?esgScore ?hasCurrency
    WHERE {{
        BIND(:{clean_sup_id} AS ?supplier)
        BIND(:{clean_mat_id} AS ?material)
        
        ?supplier a :Supplier .
        ?material a :RawMaterial .
        
        OPTIONAL {{ ?supplier rdfs:label ?sLabel . }}
        OPTIONAL {{ ?supplier :hasName ?sName . }}
        BIND(COALESCE(?sLabel, ?sName) AS ?supplierName)
        
        OPTIONAL {{ ?supplier :hasReliabilityTier ?supplierTier . }}
        OPTIONAL {{ ?supplier :hasReliabilityScore ?esgScore . }}
        
        OPTIONAL {{
            ?supplier :supplies ?material .
            OPTIONAL {{ 
                ?contract rdf:type :SLAContract ;
                          :hasSupplier ?supplier ;
                          :governsMaterial ?material ;
                          :leadTimeDays ?leadTimeDays .
            }}
        }}
        
        # Look for template delivery details
        OPTIONAL {{
            ?del :transports ?material .
            OPTIONAL {{ ?del :supplierRegion ?supplierRegion . }}
            OPTIONAL {{ ?del :paymentTerms ?paymentTerms . }}
            OPTIONAL {{ ?del :unitOfMeasure ?unitOfMeasure . }}
            OPTIONAL {{ ?del :discountPct ?discountPct . }}
            OPTIONAL {{ ?del :taxPct ?taxPct . }}
            OPTIONAL {{ ?del :savingsPct ?savingsPct . }}
            OPTIONAL {{ ?del :contractType ?contractType . }}
            OPTIONAL {{ ?del :maverickSpend ?maverickSpend . }}
            OPTIONAL {{ ?del :singleSourceFlag ?singleSourceFlag . }}
            OPTIONAL {{ ?del :preferredSupplier ?preferredSupplier . }}
            OPTIONAL {{ ?del :localInternational ?localInternational . }}
            OPTIONAL {{ ?del :hasCurrency ?hasCurrency . }}
        }}
    }}
    LIMIT 1
    """
    
    try:
        results = graphdb.execute_sparql_select(query)
        row = results[0] if results else {}
    except Exception as e:
        logger.error("Failed to query order placement context from GraphDB: %s", e)
        row = {}
        
    ts = pd.to_datetime(po_date)
    discount = float(row.get("discountPct", 0.0))
    tax = float(row.get("taxPct", 5.0))
    line_net = quantity * unit_price * (1.0 - discount / 100.0) * (1.0 + tax / 100.0)
    
    delivery_id = f"DEL_PO_{int(datetime.datetime.now().timestamp())}"
    po_id = f"PO_DEL_{int(datetime.datetime.now().timestamp())}"
    
    # Save to GraphDB
    try:
        insert_query = f"""{PREFIXES}
        INSERT DATA {{
            GRAPH <http://example.org/contracts/> {{
                :{po_id} rdf:type :PurchaseOrder ;
                         :issuedTo :{clean_sup_id} ;
                         :hasOrderedQuantity {quantity} .
                :{delivery_id} rdf:type :DeliveryEvent ;
                              :isPerformedBy :{clean_sup_id} ;
                              :fulfills :{po_id} ;
                              :transports :{clean_mat_id} ;
                              :poType "{po_type}" ;
                              :supplierRegion "{row.get('supplierRegion', 'Europe')}" ;
                              :paymentTerms "{row.get('paymentTerms', 'Net 30')}" ;
                              :unitOfMeasure "{row.get('unitOfMeasure', 'KG')}" ;
                              :hasUnitCost {unit_price} ;
                              :discountPct {discount} ;
                              :taxPct {tax} ;
                              :lineNet {line_net} ;
                              :hasCurrency "{row.get('hasCurrency', 'GBP')}" ;
                              :savingsPct {row.get('savingsPct', 5.0)} ;
                              :leadTimeDays {int(float(row.get('leadTimeDays', 14)))} ;
                              :department "{department}" ;
                              :contractType "{row.get('contractType', 'Framework')}" ;
                              :maverickSpend "{row.get('maverickSpend', 'No')}" ;
                              :singleSourceFlag "{row.get('singleSourceFlag', 'No')}" ;
                              :preferredSupplier "{row.get('preferredSupplier', 'Yes')}" ;
                              :localInternational "{row.get('localInternational', 'Local')}" .
            }}
        }}
        """
        graphdb.execute_sparql_update(insert_query)
        logger.info("[+] Placed new order :%s (Delivery: :%s) in GraphDB.", po_id, delivery_id)
    except Exception as e:
        logger.error("Failed to write placed order to GraphDB: %s", e)
        
    # Do NOT append to CSV on order placement yet as the delivery is pending.
    # It will only be appended/recalculated when a delay or completion event is received.
        
    return delivery_id

