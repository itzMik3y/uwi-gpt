#!/usr/bin/env python
"""
main.py - Main entry point for the Combined University API

This application combines the Moodle API, the RAG-based QA system,
the Academic credit‐check endpoints, and JWT authentication into a single API service.
"""

import uvicorn
import logging
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker


# -- Routers --
from auth.router import router as auth_router
from moodle_api.router import router as moodle_router
from rag_api.router import router as rag_router
from academic.router import router as academic_router  # <-- NEW

# -- RAG initializer --
from auth.router import router as auth_router  # Import the new auth router
from auth.middleware import TokenVerificationMiddleware  # Import the JWT middleware

# Import the startup function from the RAG module
from rag_api import initialize_rag_resources

# from user_db.database import get_db, engine, AsyncSessionLocal
from user_db.services import seed_superadmin

# -- Database (for lifespan) --
from user_db.database import AsyncSessionLocal

# Configure logging centrally
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# --- Application lifespan (startup/shutdown) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("API starting up (using lifespan)...")
    try:
        # Initialize DB pool
        app.state.db_pool = AsyncSessionLocal
        logger.info("Database connection pool initialized")

        # Initialize RAG resources
        initialize_rag_resources()  # Call the RAG resource initializer

        # creating/seeding super_admin user
        async with AsyncSessionLocal() as session:
            await seed_superadmin(session)

        logger.info("Super admin user checked/seeded")

        logger.info("API startup complete. RAG resources initialized.")

    except Exception as e:
        logger.error(f"Initialization error: {e}", exc_info=True)

    yield  # app  runs here
    logger.info("API shutting down...")


# Create the FastAPI app
app = FastAPI(
    title="Combined University API",
    description="Provides access to Moodle data, RAG-based QA, Academic credit‐check, and JWT auth.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # adjust as needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger.info("CORS middleware configured")

# JWT middleware
app.add_middleware(TokenVerificationMiddleware)
logger.info("JWT token verification middleware added")

# --- Include Routers ---
logger.info("Registering routers...")
app.include_router(auth_router)  # /auth
logger.info("  - Auth router (/auth)")
app.include_router(academic_router)  # /academic
logger.info("  - Academic router (/academic)")
app.include_router(moodle_router)  # /moodle
logger.info("  - Moodle router (/moodle)")
app.include_router(rag_router)  # /rag
logger.info("  - RAG router (/rag)")


# --- Health Check ---
@app.get("/", tags=["General"], summary="API Root/Health Check")
async def read_root():
    return {
        "message": "Welcome to the Combined University API",
        "status": "OK",
        "docs_url": "/docs",
    }


# --- Run server ---
if __name__ == "__main__":
    logger.info("Starting Uvicorn server...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
