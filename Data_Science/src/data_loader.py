# ==========================================
# SEMANTIC DIGITAL TWIN: Master Data Loader
# ==========================================
# This script reads the static master data from the Data Lake 
# and permanently injects it into GraphDB using your exact Ontology.

import os
import json
from SPARQLWrapper import SPARQLWrapper, POST

# --- CONFIGURATION ---
# The endpoint MUST end in /statements for INSERT operations
GRAPHDB_UPDATE_ENDPOINT = "http://localhost:7200/repositories/SemanticDigitalTwin/statements"

# Point to your Data Lake file
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Goes UP one folder from 'src', IN to 'data_Lake', IN to 'raw_logs'
MASTER_DATA_FILE = os.path.join(SCRIPT_DIR, "..", "data_Lake", "raw_logs", "master_operational_data.json")


def load_json_data():
    """Reads the master operational data from the data lake."""
    print(f"[*] Reading Master Data from: {MASTER_DATA_FILE}")
    try:
        with open(MASTER_DATA_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print("[-] Data Lake file not found! Please check the path.")
        return None

def build_supplier_triples(suppliers):
    """Translates Supplier JSON into SPARQL Triples."""
    triples = ""
    for sup in suppliers:
        s_id = sup['id']
        name = sup['name']
        tier = sup['reliability_tier']
        score = sup['reliability_score']
        # Convert Python boolean to SPARQL xsd:boolean string
        is_sustainable = "true" if sup.get('sustainability_certified') else "false"
        
        triples += f"""
        trail1:{s_id} a trail1:Supplier ;
            trail1:hasName "{name}"^^xsd:string ;
            trail1:hasReliabilityTier "{tier}"^^xsd:string ;
            trail1:hasReliabilityScore "{score}"^^xsd:float ;
            trail1:isSustainabilityCertified "{is_sustainable}"^^xsd:boolean .
        """
        # Add Object Properties connecting Suppliers to Materials
        for mat in sup.get('supplies_materials', []):
            triples += f"trail1:{s_id} trail1:supplies trail1:{mat} .\n"
            
    return triples

def build_inventory_triples(inventory):
    """Translates Inventory JSON into SPARQL Triples."""
    triples = ""
    for item in inventory:
        m_id = item['material_id']
        stock = item['current_stock']
        safety = item['safety_stock_level']
        cost = item['unit_cost']
        process = item.get('affects_process')
        
        triples += f"""
        trail1:{m_id} a trail1:RawMaterial ;
            trail1:hasInventoryStock "{stock}"^^xsd:integer ;
            trail1:hasSafetyStockLevel "{safety}"^^xsd:integer ;
            trail1:hasUnitCost "{cost}"^^xsd:float .
        """
        # If the material affects a process, link them and define the process
        if process:
            # Convert Python boolean to SPARQL xsd:boolean string
            is_critical = "true" if item.get('is_critical_path') else "false"
            crit_level = item.get('criticality_level', 'Medium')
            
            triples += f"""
            trail1:{m_id} trail1:affectsProcess trail1:{process} .
            trail1:{process} a trail1:ProductionProcess ;
                trail1:isCriticalPath "{is_critical}"^^xsd:boolean ;
                trail1:hasCriticalityLevel "{crit_level}"^^xsd:string .
            """
    return triples


def build_delivery_triples(deliveries):
    """Translates Active ERP Deliveries into SPARQL Triples."""
    triples = ""
    for d in deliveries:
        d_id = d['delivery_id']
        m_id = d['material_id']
        
        # We tell GraphDB exactly what this truck is transporting!
        triples += f"""
        trail1:{d_id} a trail1:DeliveryEvent ;
            trail1:hasDeliveryStatus "Scheduled"^^xsd:string ;
            trail1:transports trail1:{m_id} .
        """
    return triples


def inject_to_graphdb(triples):
    """Executes the SPARQL INSERT DATA command."""
    print("\n[*] Injecting mapped ontology data into GraphDB...")
    
    sparql_update = f"""
    PREFIX trail1: <http://www.semanticweb.org/youssef/ontologies/2026/1/trail1#>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

    INSERT DATA {{
        {triples}
    }}
    """
    
    sparql = SPARQLWrapper(GRAPHDB_UPDATE_ENDPOINT)
    sparql.setQuery(sparql_update)
    sparql.setMethod(POST)
    
    try:
        sparql.query()
        print("[+] SUCCESS! Master Data securely injected into Knowledge Graph.")
    except Exception as e:
        print("[-] GraphDB Error:", e)

if __name__ == "__main__":
    print("==================================================")
    print("  SEMANTIC TWIN: DATA LAKE TO GRAPHDB LOADER")
    print("==================================================\n")
    
    data = load_json_data()
    
    if data:
        print("[*] Translating JSON schema into RDF Triples...")
        all_triples = ""
        
        if "Suppliers" in data:
            all_triples += build_supplier_triples(data["Suppliers"])
        
        if "Inventory" in data:
            all_triples += build_inventory_triples(data["Inventory"])
            
        if "Active_Deliveries" in data:
            all_triples += build_delivery_triples(data["Active_Deliveries"])
            
        if all_triples:
            inject_to_graphdb(all_triples)
            
        else:
            print("[-] No valid data found to inject.")