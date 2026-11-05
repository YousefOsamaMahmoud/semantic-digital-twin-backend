# =====================================================================
# Machine_Learning/seed_procurement_evaluation.py
#
# Seeding script to load the 20% evaluation test partition of the new 
# procurement dataset into Ontotext GraphDB.
#
# This script:
#   1. Loads the new procurement dataset with supplier IDs & names.
#   2. Splits the dataset into 80% train / 20% test (random_state=42).
#   3. Identifies the unique suppliers in the 20% test set.
#   4. Generates and executes SPARQL INSERT statements to seed their 
#      static contract context (leadTimeDays, hasReliabilityScore, etc.) 
#      into GraphDB.
# =====================================================================

import os
import sys
import re
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

# Allow importing backend modules by adding the Backend folder to Python Path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
BACKEND_PATH = os.path.join(PROJECT_ROOT, "Backend")
sys.path.append(BACKEND_PATH)

from knowledge_base.connection import graphdb
from knowledge_base.repository import PREFIXES, CONTRACT_GRAPH

DATASET_PATH = os.path.join(SCRIPT_DIR, "Dataset_Procurement_SelectedFeatures.csv")

def clean_uri_fragment(text: str) -> str:
    """Replaces all non-alphanumeric characters with underscores for safe URI fragments."""
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", text)
    return safe

def escape_literal(text: str) -> str:
    """Escapes quotes and newlines for SPARQL string literals."""
    escaped = str(text).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return escaped

def seed_procurement_eval_data():
    print("=" * 60)
    print("  SEEDING GRAPHDB WITH 20% PROCUREMENT EVALUATION SET")
    print("=" * 60)

    if not os.path.exists(DATASET_PATH):
        raise FileNotFoundError(f"New dataset file missing at: {DATASET_PATH}")

    # Load dataset
    print(f"[*] Loading dataset from: {DATASET_PATH}...")
    df = pd.read_csv(DATASET_PATH)
    
    # Exclude dummy/evaluation suppliers to prevent them from ever being added again
    banned_suppliers = {
        "TechPro Components", "Cornerstone Services", "Quantum Electronics", 
        "Nordic Office Solutions", "Blue Horizon Packaging", "Iron Gate Steel", 
        "GlobalParts Ltd", "Atlantic Raw Materials", "Meridian Tech", 
        "Apex Industrial Supplies", "EuroBuild Materials", "SunRise Manufacturing", 
        "FastTrack Logistics", "Pacific Rim Supplies", "Delta Engineering"
    }
    df = df[~df["Supplier Name"].isin(banned_suppliers)]
    
    # 80/20 split to isolate the 20% test partition (random_state=42 matches training)
    print("[*] Performing 80/20 train-test split...")
    _, eval_df = train_test_split(df, test_size=0.2, random_state=42)
    print(f"[+] Isolated {len(eval_df)} rows in the evaluation set.")

    # Drop rows without Supplier ID or Supplier Name
    eval_df = eval_df.dropna(subset=["Supplier ID", "Supplier Name"])
    
    # Identify unique suppliers based on Supplier ID
    unique_suppliers = eval_df.drop_duplicates(subset=["Supplier ID"])
    print(f"[+] Found {len(unique_suppliers)} unique suppliers in the evaluation set to seed.")

    triples = []
    unique_suppliers_uris = []
    
    for idx, row in unique_suppliers.iterrows():
        sup_name = escape_literal(row["Supplier Name"])
        sup_id = str(row["Supplier ID"]).strip()
        if sup_id.startswith("Supplier_"):
            sup_uri = clean_uri_fragment(sup_id)
        else:
            sup_uri = f"Supplier_{clean_uri_fragment(sup_id)}"
            
        mat_name = str(row["Sub Category"]).strip()
        mat_uri = f"Material_{clean_uri_fragment(mat_name)}"
        
        lead_days = int(row["Lead Time Days"])
        rel_score = float(row["Supplier ESG Score"]) / 100.0
        tier = int(row["Supplier Tier"])
        region = escape_literal(row["Supplier Region"])
        risk = escape_literal(row["Supplier Risk"])
        terms = escape_literal(row["Payment Terms"])
        uom = escape_literal(row["Unit of Measure"])
        price = float(row["Unit Price"])
        discount = float(row["Discount Pct"])
        tax = float(row["Tax Pct"])
        net = float(row["Line Net"])
        savings = float(row["Savings Pct"])
        dept = escape_literal(row["Department"])
        contract_type = escape_literal(row["Contract Type"])
        maverick = escape_literal(row["Maverick Spend"])
        single_source = escape_literal(row["Single Source Flag"])
        preferred = escape_literal(row["Preferred Supplier"])
        local_intl = escape_literal(row["Local International"])
        currency = escape_literal(row["Currency"])
        po_type = escape_literal(row["PO Type"])

        unique_suppliers_uris.append(f":{sup_uri}")

        # Format penalty clause text
        penalty_clause = f"SLA Penalty terms: Delay penalty daily. Maverick spend limit enforcement. Savings target: {savings}%."

        # Construct RDF triples
        triples.append(f"""
            # Supplier properties
            :{sup_uri} rdf:type :Supplier ;
                      rdfs:label "{sup_name}" ;
                      :hasReliabilityScore "{rel_score}"^^xsd:float ;
                      :hasReliabilityTier {tier} .

            # Material properties
            :{mat_uri} rdf:type :RawMaterial ;
                      rdfs:label "{mat_name}" ;
                      :isSuppliedBy :{sup_uri} .
                      
            # Link relationship
            :{sup_uri} :supplies :{mat_uri} ;
                      :leadTimeDays {lead_days} ;
                      :penaltyClause "{penalty_clause}" .

            # Delivery profile representation (as default template for fallback predictions)
            :Del_Profile_{sup_uri} rdf:type :DeliveryEvent ;
                                  :transports :{mat_uri} ;
                                  :poType "{po_type}" ;
                                  :supplierRegion "{region}" ;
                                  :paymentTerms "{terms}" ;
                                  :unitOfMeasure "{uom}" ;
                                  :hasUnitCost {price} ;
                                  :discountPct {discount} ;
                                  :taxPct {tax} ;
                                  :lineNet {net} ;
                                  :hasCurrency "{currency}" ;
                                  :savingsPct {savings} ;
                                  :leadTimeDays {lead_days} ;
                                  :department "{dept}" ;
                                  :contractType "{contract_type}" ;
                                  :maverickSpend "{maverick}" ;
                                  :singleSourceFlag "{single_source}" ;
                                  :preferredSupplier "{preferred}" ;
                                  :localInternational "{local_intl}" .
        """)

    # Combine into a SPARQL update query
    # Targeted delete query using VALUES to only clear scores for suppliers being seeded, keeping other data intact
    if unique_suppliers_uris:
        delete_query = f"""{PREFIXES}
        DELETE {{
            GRAPH <{CONTRACT_GRAPH}> {{
                ?s :hasReliabilityScore ?o .
            }}
            ?s :hasReliabilityScore ?o .
        }}
        WHERE {{
            VALUES ?s {{ {" ".join(unique_suppliers_uris)} }}
            {{
                GRAPH <{CONTRACT_GRAPH}> {{
                    ?s :hasReliabilityScore ?o .
                }}
            }} UNION {{
                ?s :hasReliabilityScore ?o .
            }}
        }}
        """
    else:
        delete_query = ""

    sparql_update = f"""{PREFIXES}
    INSERT DATA {{
        GRAPH <{CONTRACT_GRAPH}> {{
            {" ".join(triples)}
        }}
    }}
    """

    print("[*] Connecting to GraphDB to insert evaluation supplier triples...")
    try:
        # Clear old scores first to avoid duplicates
        if delete_query:
            graphdb.execute_sparql_update(delete_query)
        graphdb.execute_sparql_update(sparql_update)
        print(f"[+] GraphDB successfully seeded with {len(unique_suppliers)} new suppliers and their logistics parameters.")
    except Exception as exc:
        print(f"[!] Error seeding GraphDB: {exc}")
        sys.exit(1)

    print("=" * 60)
    print("  SEEDING COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    seed_procurement_eval_data()
