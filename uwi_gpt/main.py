#!/usr/bin/env python
"""
main.py - Main entry point for the Combined University API

This application combines the Moodle API and the RAG-based QA system
into a single API service.
"""

import uvicorn
import logging
from fastapi import FastAPI

# Import routers from the modules
from moodle_api.router import router as moodle_router
from rag_api.router import router as rag_router

# Import the startup function from the RAG module
from rag_api import initialize_rag_resources

# Configure logging centrally
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Create the main FastAPI app instance
app = FastAPI(
    title="Combined University API",
    description="Provides access to Moodle data and a RAG-based QA system.",
    version="1.0.0"
)

# --- Startup Event ---
@app.on_event("startup")
async def startup_event():
    logger.info("API starting up...")
    initialize_rag_resources()  # Call the RAG resource initializer
    logger.info("API startup complete. RAG resources initialized.")

# --- Include Routers ---
logger.info("Including API routers...")
app.include_router(moodle_router)
logger.info("Included Moodle router (prefix='/moodle')")
app.include_router(rag_router)
logger.info("Included RAG router (prefix='/rag')")

# --- Root Endpoint ---
@app.get("/", tags=["General"], summary="API Root/Health Check")
async def read_root():
    """Basic API information and health check."""
    return {
        "message": "Welcome to the Combined University API",
        "status": "OK",
        "docs_url": "/docs"
        }

# --- Run Instruction ---
if __name__ == "__main__":
    logger.info("Starting Uvicorn server...")
    # Point uvicorn to this file (main) and the app instance within it
    # reload=True is great for development, disable for production
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)