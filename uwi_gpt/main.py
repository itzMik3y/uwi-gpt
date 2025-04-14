#!/usr/bin/env python
"""
main.py - Main entry point for the Combined University API

This application combines the Moodle API and the RAG-based QA system
into a single API service.
"""

import uvicorn
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import routers from the modules
from moodle_api.router import router as moodle_router
from rag_api.router import router as rag_router
from contextlib import asynccontextmanager
# Import the startup function from the RAG module
from rag_api import initialize_rag_resources

# Configure logging centrally
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)




# --- Startup Event ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic: Code here runs before the application starts receiving requests
    logger.info("API starting up (using lifespan)...")
    try:
        initialize_rag_resources()  # Call the RAG resource initializer
        logger.info("API startup complete. RAG resources initialized.")
    except Exception as e:
        # Log any errors during initialization
        logger.error(f"Fatal error during RAG initialization: {e}", exc_info=True)
        # Depending on the severity, you might raise the exception
        # to prevent the app from starting if initialization fails.
        # raise # Uncomment to stop app on initialization failure

    yield # The application runs while yielded

    # Shutdown logic: Code here runs after the application stops receiving requests
    logger.info("API shutting down...")

app = FastAPI(
    title="Combined University API",
    description="Provides access to Moodle data and a RAG-based QA system.",
    version="1.0.0",
    lifespan=lifespan  # Add the lifespan handler here
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],  # Add your frontend URLs
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)
logger.info("CORS middleware added to allow cross-origin requests")

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