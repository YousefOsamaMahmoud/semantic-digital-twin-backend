# ============================================================
# main.py — Application Entry Point
#
# This file bootstraps the FastAPI app and registers all
# routers (one per feature group).  Run with:
#
#   uvicorn main:app --reload
# ============================================================

from fastapi import FastAPI
from api.sandbox import router as sandbox_router
from database.connection import db

# --------------- App Initialization ---------------
app = FastAPI(
    title="Semantic Digital Twin API",
    description="Backend engine for the Cavengers Graduation Project — "
                "raw-material supply detection and resolution.",
    version="0.1.0",
)

# --------------- Register Routers ---------------
# Each feature group gets its own router file in api/.
# We include them here so FastAPI knows about their endpoints.
app.include_router(sandbox_router)


# --------------- Lifecycle Events ---------------
@app.on_event("shutdown")
def shutdown_event():
    """
    Gracefully close the Neo4j driver when the server stops.
    This releases all connection-pool resources so we
    don't leak sockets.
    """
    db.close()


# --------------- Root Health-Check ---------------
@app.get("/")
def read_root():
    """Simple health-check endpoint to verify the server is alive."""
    return {"message": "Hello Cavengers! The Backend is alive!"}