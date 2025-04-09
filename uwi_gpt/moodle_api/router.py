# moodle_api/router.py
import logging
from fastapi import APIRouter, HTTPException, Depends
from .models import MoodleCredentials
from .service import fetch_moodle_details

# Optional: configure a logger specific to this module
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/moodle",  # All routes here will start with /moodle
    tags=["Moodle"]     # Group endpoints in Swagger UI
)

@router.post("/data", summary="Fetch Moodle Courses and Calendar Events")
async def get_moodle_data_endpoint(credentials: MoodleCredentials):
    """
    Logs into the UWI Mona VLE using provided credentials and retrieves:
    - User's name and email
    - Enrolled courses
    - Calendar events within the specified time range (defaults provided)
    """
    try:
        # Because fetch_moodle_details is synchronous but involves I/O,
        # FastAPI runs it in a threadpool when called from an async route.
        # No need to explicitly use run_in_threadpool here.
        data = fetch_moodle_details(credentials)
        logger.info(f"Successfully retrieved Moodle data for user {credentials.username[:3]}***")
        return data
    except HTTPException as e:
        logger.warning(f"HTTPException fetching Moodle data for {credentials.username[:3]}***: {e.detail} (Status: {e.status_code})")
        raise e # Re-raise exceptions from the service layer
    except Exception as e:
        logger.exception(f"Unexpected error in /moodle/data endpoint for {credentials.username[:3]}***") # Log stack trace
        raise HTTPException(status_code=500, detail="Internal server error retrieving Moodle data.")