from knowledge_base.connection import graphdb

query = """
PREFIX : <http://example.org/ontology#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

INSERT DATA {
    GRAPH <http://example.org/contracts/> {
        # --- Material #2: Lithium Battery Cells ---
        :BatteryCells a :RawMaterial ;
                      rdfs:label "Lithium Battery Cells" .

        # Supplier who is delayed
        :VoltexSupplier a :Supplier ;
                        rdfs:label "Voltex Power Systems" ;
                        :supplies :BatteryCells ;
                        :leadTimeDays 5 ;
                        :penaltyRatePerDay 400 ;
                        :hasReliabilityScore "0.28"^^xsd:float .

        # Production process impacted
        :BatteryPackLine a :ProductionProcess ;
                          rdfs:label "Battery Pack Assembly" .

        :BatteryCells :affectsProcess :BatteryPackLine .

        # Mark the process as disrupted (At Risk)
        :BatteryPackLine a :ProductionDisruption .

        # Delayed delivery event  (72 hrs = 3 days late)
        :BatteryDelivery a :DeliveryEvent ;
                         :transports :BatteryCells ;
                         :hasDeliveryStatus "Delayed" ;
                         :hasDelayDuration 72 .

        # High-rated alternative supplier for BatteryCells
        :EnergyAltSupplier a :AlternativeSupplier ;
                            rdfs:label "NovaPower Energy Ltd." ;
                            :supplies :BatteryCells ;
                            :country "DE" ;
                            :leadTimeDays 4 ;
                            :hasReliabilityScore "0.88"^^xsd:float .
    }
}
"""

try:
    graphdb.execute_sparql_update(query)
    print("Successfully injected Lithium Battery Cells as a second at-risk material!")
except Exception as e:
    print(f"Failed: {e}")
