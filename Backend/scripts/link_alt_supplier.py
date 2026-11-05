from knowledge_base.connection import graphdb

query = """
PREFIX : <http://example.org/ontology#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

INSERT DATA {
    GRAPH <http://example.org/contracts/> {
        :TestAltSupplier :supplies :TestMaterial .
    }
}
"""

try:
    graphdb.execute_sparql_update(query)
    print("Linked Alternative Supplier to Material!")
except Exception as e:
    print(e)
