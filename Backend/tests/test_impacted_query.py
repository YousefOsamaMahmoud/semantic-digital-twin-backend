from knowledge_base.connection import graphdb

query = """
PREFIX : <http://example.org/supply-chain/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?supplierLabel ?materialLabel ?productLabel ?riskStatus ?delayHours
WHERE {
    ?delivery  rdf:type     :DeliveryEvent ;
               :hasDeliveryStatus ?status ;
               :transports  ?material .
    FILTER(STR(?status) = "Delayed")
    
    OPTIONAL { ?delivery :hasDelayDuration ?delayHours . }
    
    OPTIONAL {
        { ?supplier :supplies ?material . }
        UNION
        { ?material :isSuppliedBy ?supplier . }
        OPTIONAL { ?supplier rdfs:label ?sLabel . }
        OPTIONAL { ?supplier :hasName ?sName . }
    }
    BIND(COALESCE(?sLabel, ?sName, REPLACE(STR(?supplier), "^.*#", "")) AS ?supplierLabel)

    OPTIONAL { ?material rdfs:label ?mLabel . }
    BIND(COALESCE(?mLabel, REPLACE(STR(?material), "^.*#", "")) AS ?materialLabel)

    ?material  :affectsProcess ?process .
    OPTIONAL { ?process rdfs:label ?pLabel . }
    BIND(COALESCE(?pLabel, REPLACE(STR(?process), "^.*#", "")) AS ?productLabel)

    ?process   rdf:type     :ProductionDisruption .
    BIND("true" AS ?riskStatus)
}
"""
try:
    results = graphdb.execute_sparql_select(query)
    print(f"FOUND {len(results)} IMPACTED PRODUCTS:")
    for r in results:
        print(r)
except Exception as e:
    print("Error:", e)
