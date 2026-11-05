from knowledge_base.connection import graphdb

query = """
PREFIX : <http://example.org/ontology#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

INSERT DATA {
    GRAPH <http://example.org/contracts/> {
        # Create a test material
        :TestMaterial a :RawMaterial ;
                      rdfs:label "Micro-Controllers (MCU)" ;
                      :isSuppliedBy :TestSupplier .
                      
        # Create a test supplier that provides the material
        :TestSupplier a :Supplier ;
                      rdfs:label "Stark Components Co." ;
                      :supplies :TestMaterial ;
                      :leadTimeDays 7 ;
                      :penaltyRatePerDay 250 ;
                      :hasReliabilityScore "0.35"^^xsd:float .
                      
        # Create a production process that relies on this material
        :TestProcess a :ProductionProcess ;
                     rdfs:label "Drone Assembly Line 1" .
                     
        :TestMaterial :affectsProcess :TestProcess .
        
        # Explicitly mark process as Disrupted (just in case OWL inference is disabled)
        :TestProcess a :ProductionDisruption .
        
        # Create the delayed delivery event
        :TestDelivery a :DeliveryEvent ;
                      :transports :TestMaterial ;
                      :hasDeliveryStatus "Delayed" ;
                      :hasDelayDuration 96 . # 96 hours = 4 days delay
                      
        # Add an alternative supplier so the fallback logic has something to find!
        :TestAltSupplier a :AlternativeSupplier ;
                         rdfs:label "Wayne Electronics Ltd." ;
                         :country "UK" ;
                         :leadTimeDays 3 ;
                         :hasReliabilityScore "0.92"^^xsd:float .
    }
}
"""

try:
    graphdb.execute_sparql_update(query)
    print("Successfully injected test delay data into GraphDB!")
except Exception as e:
    print(f"Failed to inject data: {e}")
