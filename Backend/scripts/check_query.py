PREFIXES = '''PREFIX : <http://example.org/ontology#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
'''

CONTRACT_GRAPH = 'http://example.org/contracts/'

supplier_uri = 'Sup'
material_uri = 'Mat'
contract_uri = f'Contract_{supplier_uri}_{material_uri}'
lead_days = 5
raw_penalty = 'x'
quantity = 100
unit_cost = 10.0
safe_supplier_name = 'Sup'
safe_material = 'Mat'

old_process_delete = ''
old_process_where = ''
process_triple = ''

timestamp = '2026'

sparql_update = f'''
    {PREFIXES}

    DELETE {{
        GRAPH <{CONTRACT_GRAPH}> {{
            {old_process_delete}
            :{supplier_uri} :hasReliabilityScore ?oldScore .
            :{material_uri} :hasUnitCost ?oldUnitCost .
            :{material_uri} :hasOrderedQuantity ?oldQty .
            :{contract_uri} rdf:type :SLAContract ;
                            :hasSupplier :{supplier_uri} ;
                            :governsMaterial :{material_uri} ;
                            :leadTimeDays ?oldContractLead ;
                            :penaltyClause ?oldContractPenalty ;
                            :hasOrderedQuantity ?oldContractQty ;
                            :hasUnitCost ?oldContractCost .
        }}
    }}
    INSERT {{
        GRAPH <{CONTRACT_GRAPH}> {{
            # ── Supplier individual ──
            :{supplier_uri}  rdf:type       :Supplier ;
                             rdfs:label     "{safe_supplier_name}" ;
                             :createdAt     "{timestamp}"^^xsd:dateTime .

            # ── RawMaterial individual ──
            :{material_uri}  rdf:type       :RawMaterial ;
                             rdfs:label     "{safe_material}" ;
                             :hasUnitCost   "{unit_cost}"^^xsd:float ;
                             :hasOrderedQuantity "{quantity}"^^xsd:integer .{process_triple}

            # ── Relationship: Supplier supplies RawMaterial ──
            :{supplier_uri}  :supplies      :{material_uri} .

            # ── Preserved or Default Reliability Score ──
            :{supplier_uri}  :hasReliabilityScore ?finalScore .

            # ── SLA Contract individual ──
            :{contract_uri}  rdf:type            :SLAContract ;
                             :hasSupplier        :{supplier_uri} ;
                             :governsMaterial    :{material_uri} ;
                             :leadTimeDays       {lead_days} ;
                             :penaltyClause      "{raw_penalty}" ;
                             :hasOrderedQuantity "{quantity}"^^xsd:integer ;
                             :hasUnitCost        "{unit_cost}"^^xsd:float .
        }}
    }}
    WHERE {{
        OPTIONAL {{
            GRAPH <{CONTRACT_GRAPH}> {{
                :{supplier_uri} :hasReliabilityScore ?oldScore .
            }}
        }}
        OPTIONAL {{
            GRAPH <{CONTRACT_GRAPH}> {{
                :{material_uri} :hasUnitCost ?oldUnitCost .
            }}
        }}
        OPTIONAL {{
            GRAPH <{CONTRACT_GRAPH}> {{
                :{material_uri} :hasOrderedQuantity ?oldQty .
            }}
        }}{old_process_where}
        OPTIONAL {{
            GRAPH <{CONTRACT_GRAPH}> {{
                :{contract_uri} rdf:type :SLAContract ;
                                :hasSupplier :{supplier_uri} ;
                                :governsMaterial :{material_uri} .
                OPTIONAL {{ :{contract_uri} :leadTimeDays ?oldContractLead . }}
                OPTIONAL {{ :{contract_uri} :penaltyClause ?oldContractPenalty . }}
                OPTIONAL {{ :{contract_uri} :hasOrderedQuantity ?oldContractQty . }}
                OPTIONAL {{ :{contract_uri} :hasUnitCost ?oldContractCost . }}
            }}
        }}
        BIND(COALESCE(?oldScore, "0.75"^^xsd:float) AS ?finalScore)
    }}
'''

for i, line in enumerate(sparql_update.splitlines()):
    print(f'{i+1:2}: {line}')
