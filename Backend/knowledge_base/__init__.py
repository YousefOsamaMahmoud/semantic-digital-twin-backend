# ============================================================
# database/__init__.py — Package Initialisation
#
# Exposes the GraphDB connection singleton and
# repository functions for convenient imports.
# ============================================================

from knowledge_base.connection import graphdb
from knowledge_base.repository import (
    create_contract_graph,
    find_impacted_products_by_supplier_delay,
)
