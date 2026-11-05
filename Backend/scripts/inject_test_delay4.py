from knowledge_base.connection import graphdb

query = """
PREFIX : <http://example.org/ontology#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

INSERT DATA {
    GRAPH <http://example.org/contracts/> {
        # --- Material #4: Semiconductor Wafers ---
        :SemiconductorWafers a :RawMaterial ;
                             rdfs:label "Semiconductor Wafers" .

        # Primary Supplier who is delayed
        :SiliconFoundrySupplier a :Supplier ;
                                rdfs:label "Global Silicon Foundry" ;
                                :supplies :SemiconductorWafers ;
                                :leadTimeDays 14 ;
                                :penaltyRatePerDay 800 ;
                                :hasReliabilityScore "0.22"^^xsd:float .

        # Production process impacted
        :CPUFabrication a :ProductionProcess ;
                        rdfs:label "CPU Fabrication Line" .

        :SemiconductorWafers :affectsProcess :CPUFabrication .

        # Mark the process as disrupted (At Risk)
        :CPUFabrication a :ProductionDisruption .

        # Delayed delivery event (240 hrs = 10 days late)
        :WaferDelivery a :DeliveryEvent ;
                       :transports :SemiconductorWafers ;
                       :hasDeliveryStatus "Delayed" ;
                       :hasDelayDuration 240 .

        # Alternative Supplier 1 (Best)
        :PrecisionWafersAlt a :AlternativeSupplier ;
                            rdfs:label "Precision Wafers Inc." ;
                            :supplies :SemiconductorWafers ;
                            :country "US" ;
                            :leadTimeDays 12 ;
                            :hasReliabilityScore "0.95"^^xsd:float .

        # Alternative Supplier 2 (Average)
        :EuroChipAlt a :AlternativeSupplier ;
                     rdfs:label "EuroChip Materials" ;
                     :supplies :SemiconductorWafers ;
                     :country "DE" ;
                     :leadTimeDays 15 ;
                     :hasReliabilityScore "0.81"^^xsd:float .
                     
        # Alternative Supplier 3 (Poor)
        :CheapWafersAlt a :AlternativeSupplier ;
                        rdfs:label "Budget Silicon Ltd." ;
                        :supplies :SemiconductorWafers ;
                        :country "CN" ;
                        :leadTimeDays 21 ;
                        :hasReliabilityScore "0.45"^^xsd:float .
    }
}
"""

try:
    graphdb.execute_sparql_update(query)
    print("Successfully injected Semiconductor Wafers with 3 alternatives!")
except Exception as e:
    print(f"Failed: {e}")
