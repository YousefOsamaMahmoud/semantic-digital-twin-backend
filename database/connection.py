# ============================================================
# database/connection.py — Layer 3: Neo4j Connection Broker
#
# This module manages the connection to the Neo4j graph
# database (supports both local Neo4j and AuraDB Cloud).
# It provides:
#   1. A reusable Neo4jConnection class
#   2. A module-level singleton (`db`) for easy imports
#
# Credentials are loaded from a .env file in the project root
# via python-dotenv. Other modules simply do:
#   from database.connection import db
#   db.execute_write(query, parameters)
# ============================================================

import os
from dotenv import load_dotenv
from neo4j import GraphDatabase

# ---- Load .env file ----
# This reads the .env file in the project root and injects
# its key-value pairs into os.environ so that os.getenv()
# can pick them up below. Must be called BEFORE os.getenv().
load_dotenv()


class Neo4jConnection:
    """
    A thin wrapper around the official Neo4j Python driver.

    Responsibilities
    ----------------
    - Read connection credentials from the .env file
      (loaded by python-dotenv at module import time).
    - Initialise the driver once and reuse it across requests.
    - Provide an `execute_write` helper that opens a session,
      runs a write transaction, and returns the result.
    - Provide a `close` method for clean shutdown.
    """

    def __init__(self):
        # ---- Connection credentials ----
        # These are read from your .env file. Example .env:
        #   NEO4J_URI=neo4j+s://xxxxxxxx.databases.neo4j.io
        #   NEO4J_USER=neo4j
        #   NEO4J_PASSWORD=your-auradb-password
        self._uri = os.getenv("NEO4J_URI")
        self._user = os.getenv("NEO4J_USER")
        self._password = os.getenv("NEO4J_PASSWORD")

        # ---- Driver initialisation ----
        # The driver object is thread-safe and should be created
        # once per application lifetime, NOT once per request.
        self._driver = GraphDatabase.driver(
            self._uri,
            auth=(self._user, self._password),
        )

    # ----------------------------------------------------------
    # close() — release resources
    # ----------------------------------------------------------
    def close(self):
        """
        Gracefully shut down the Neo4j driver.
        Call this when the FastAPI server stops (see main.py
        shutdown event).
        """
        if self._driver:
            self._driver.close()

    # ----------------------------------------------------------
    # execute_write() — run a Cypher write transaction
    # ----------------------------------------------------------
    def execute_write(self, query: str, parameters: dict = None):
        """
        Open a session, execute a WRITE transaction, and return
        the result records as a list.

        Parameters
        ----------
        query : str
            A Cypher statement (e.g. CREATE, MERGE, SET …).
        parameters : dict, optional
            Parameter map injected into the Cypher query.

        Returns
        -------
        list
            A list of Record objects returned by Neo4j.
        """
        # `with` ensures the session is always closed, even if
        # an exception is raised inside the block.
        with self._driver.session() as session:
            result = session.execute_write(
                lambda tx: tx.run(query, parameters or {}).data()
            )
            return result


# ==============================================================
# Module-level singleton
# ==============================================================
# By creating the instance here, every module that imports `db`
# shares the SAME driver — no duplicate connections.
db = Neo4jConnection()
