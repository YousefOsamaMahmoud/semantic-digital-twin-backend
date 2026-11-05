# ============================================================
# main.py — Application Entry Point
#
# This file bootstraps the FastAPI app and registers all
# routers (one per feature group).  Run with:
#
#   uvicorn main:app --reload --port 8001
# ============================================================

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.dashboard import router as dashboard_router
from api.sandbox import router as sandbox_router
from services.telemetry_simulator_service import start_simulator, stop_simulator

# --------------- App Initialization ---------------
app = FastAPI(
    title="Semantic Digital Twin API",
    description="Backend engine for the Cavengers Graduation Project — "
                "raw-material supply detection and resolution. "
                "Powered by GraphDB + OWL Reasoning.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------- Register Routers ---------------
app.include_router(sandbox_router)
app.include_router(dashboard_router)


# --------------- Lifecycle Events ---------------
@app.on_event("startup")
def startup_event():
    """
    Launches the background telemetry simulator, which continuously
    generates real-time IoT delivery events and feeds them through
    the risk engine pipeline (GraphDB injection -> risk analysis ->
    multi-manager alert generation -> persistence). Controlled via
    the TELEMETRY_INTERVAL_SECONDS env var (default 30s).
    """
    start_simulator()


# NOTE: SPARQLWrapper is stateless (Golden Rule #1).
# There is NO persistent connection to close on shutdown.
@app.on_event("shutdown")
def shutdown_event():
    """
    Stops the background telemetry simulator cleanly. GraphDB
    connections via SPARQLWrapper are stateless HTTP requests — no
    socket pool or driver to close.
    """
    stop_simulator()


# --------------- Root Health-Check ---------------
@app.get("/")
def read_root():
    """Simple health-check endpoint to verify the server is alive."""
    return {"message": "Hello Cavengers! The Backend is alive! (GraphDB Edition)"}