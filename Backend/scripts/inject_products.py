from knowledge_base.connection import graphdb

query = """
PREFIX : <http://example.org/ontology#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

INSERT DATA {
    GRAPH <http://example.org/contracts/> {
        # Link Drone Assembly Line to its Product
        :DroneProduct a :Product ;
                      rdfs:label "Surveillance Drone V2" .
        :TestProcess :producesProduct :DroneProduct .
        
        # Link Battery Pack Assembly to its Product
        :EVBattery a :Product ;
                   rdfs:label "Electric Vehicle Battery Pack" .
        :BatteryPackLine :producesProduct :EVBattery .
        
        # Link Chassis Molding Line to its Product
        :CarChassis a :Product ;
                    rdfs:label "Sports Car Chassis" .
        :ChassisMoldingLine :producesProduct :CarChassis .
        
        # Link CPU Fabrication Line to its Product
        :QuantumCPU a :Product ;
                    rdfs:label "Quantum Core Processor" .
        :CPUFabrication :producesProduct :QuantumCPU .
    }
}
"""

try:
    graphdb.execute_sparql_update(query)
    print("Successfully injected Product data into GraphDB!")
except Exception as e:
    print(f"Failed to inject Product data: {e}")
