# ============================================================
# database/connection.py — Layer 3: GraphDB Connection Broker
#
# This module manages the connection to a local Ontotext
# GraphDB instance via its SPARQL endpoint.
#
# ╔══════════════════════════════════════════════════════════╗
# ║  GOLDEN RULE #1 — STATELESS CONNECTION                  ║
# ║  Unlike Neo4j's persistent driver, SPARQLWrapper is      ║
# ║  stateless.  Each request is an independent HTTP call.   ║
# ║  There is NO socket pool to manage and NO session to     ║
# ║  close.  The class below simply centralises the endpoint ║
# ║  URL so every module uses the same configuration.        ║
# ╚══════════════════════════════════════════════════════════╝
#
# Usage:
#   from knowledge_base.connection import graphdb
#   results = graphdb.execute_sparql_select("SELECT …")
#   graphdb.execute_sparql_update("INSERT DATA { … }")
# ============================================================

import os
import json
from dotenv import load_dotenv
from SPARQLWrapper import SPARQLWrapper, JSON, POST, DIGEST

# ---- Load .env file ----
load_dotenv()


class GraphDBConnection:
    """
    A thin, **stateless** wrapper around SPARQLWrapper.

    Responsibilities
    ----------------
    - Read the GraphDB endpoint URL from the .env file.
    - Build the correct SPARQL and SPARQL-Update endpoint URLs.
    - Provide `execute_sparql_select()` for SELECT / ASK queries.
    - Provide `execute_sparql_update()` for INSERT / DELETE queries.

    Why no close() method?
    ----------------------
    SPARQLWrapper uses plain HTTP requests under the hood.
    There is no persistent connection, no socket pool, and
    therefore nothing to close.  Each method call is a fresh
    HTTP round-trip to the GraphDB REST API.
    """

    def __init__(self):
        # ---- Configuration from .env ----
        # Example .env:
        #   GRAPHDB_URL=http://localhost:7200
        #   GRAPHDB_REPO=supply-chain
        graphdb_url = os.getenv("GRAPHDB_URL", "http://localhost:7200")
        graphdb_repo = os.getenv("GRAPHDB_REPO", "supply-chain")

        # Optional authentication (GraphDB Free often runs without auth)
        self._user = os.getenv("GRAPHDB_USER", "")
        self._password = os.getenv("GRAPHDB_PASSWORD", "")

        # ---- Endpoint URLs ----
        # GraphDB exposes two endpoints per repository:
        #   /repositories/{repo}          → for SELECT / ASK queries
        #   /repositories/{repo}/statements → for INSERT / DELETE updates
        self._query_endpoint = f"{graphdb_url}/repositories/{graphdb_repo}"
        self._update_endpoint = f"{graphdb_url}/repositories/{graphdb_repo}/statements"

    # ----------------------------------------------------------
    # _get_sparql_wrapper() — build a fresh wrapper per request
    # ----------------------------------------------------------
    def _get_sparql_wrapper(self, endpoint: str, is_update: bool = False) -> SPARQLWrapper:
        """
        Create a new SPARQLWrapper instance for a single request.

        This is intentionally created fresh every time
        (Golden Rule #1: Stateless Connection).
        """
        sparql = SPARQLWrapper(endpoint)

        if is_update:
            sparql.setMethod(POST)

        # Set auth only if credentials are provided
        if self._user and self._password:
            sparql.setCredentials(self._user, self._password)
            sparql.setHTTPAuth(DIGEST)

        return sparql

    # ----------------------------------------------------------
    # execute_sparql_select() — run a SELECT / ASK query
    # ----------------------------------------------------------
    def execute_sparql_select(self, query: str) -> list[dict]:
        """
        Execute a SPARQL SELECT query and return the result
        bindings as a list of dictionaries.

        Parameters
        ----------
        query : str
            A SPARQL SELECT or ASK query string.

        Returns
        -------
        list[dict]
            Each dict maps variable names to their values.
            Example: [{"supplier": "Acme", "material": "Steel"}]
        """
        sparql = self._get_sparql_wrapper(self._query_endpoint)
        sparql.setQuery(query)
        sparql.setReturnFormat(JSON)

        response = sparql.query().convert()

        # Parse the standard SPARQL JSON response format
        results = []
        for binding in response["results"]["bindings"]:
            row = {}
            for var_name, var_data in binding.items():
                row[var_name] = var_data["value"]
            results.append(row)

        return results

    # ----------------------------------------------------------
    # execute_sparql_update() — run an INSERT / DELETE update
    # ----------------------------------------------------------
    def execute_sparql_update(self, update_query: str) -> bool:
        """
        Execute a SPARQL UPDATE (INSERT DATA / DELETE DATA, etc.).

        Parameters
        ----------
        update_query : str
            A SPARQL UPDATE statement.

        Returns
        -------
        bool
            True if the update was accepted (HTTP 2xx).

        Raises
        ------
        Exception
            If GraphDB returns an error status code.
        """
        sparql = self._get_sparql_wrapper(self._update_endpoint, is_update=True)
        sparql.setQuery(update_query)

        # SPARQLWrapper sends the update; GraphDB returns 204 on success
        response = sparql.query()
        return True


# ==============================================================
# Module-level singleton
# ==============================================================
# Even though the connection is stateless, we use a singleton
# so that every module shares the SAME endpoint configuration.
# No sockets are held open — this is just a config object.
graphdb = GraphDBConnection()
