import os
import re
import json
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import uvicorn

app = FastAPI(title="Moodle API")

class MoodleCredentials(BaseModel):
    username: str
    password: str
    time_sort_from: Optional[int] = 1744002000
    time_sort_to: Optional[int] = 1744606800
    limit_num: Optional[int] = 6

@app.post("/moodle-data")
async def get_moodle_data(credentials: MoodleCredentials):
    # URLs
    LOGIN_URL = "https://vle.mona.uwi.edu/login/index.php"
    COURSES_URL = "https://vle.mona.uwi.edu/my/courses.php"
    PROFILE_URL = "https://vle.mona.uwi.edu/user/profile.php"
    # Service URL templates
    COURSES_SERVICE_URL_TEMPLATE = "https://vle.mona.uwi.edu/lib/ajax/service.php?sesskey={}&info=core_course_get_enrolled_courses_by_timeline_classification"
    CALENDAR_SERVICE_URL_TEMPLATE = "https://vle.mona.uwi.edu/lib/ajax/service.php?sesskey={}&info=core_calendar_get_action_events_by_timesort"

    # Create a session to persist cookies
    session = requests.Session()

    try:
        # 1) GET the login page to fetch the logintoken
        login_page_response = session.get(LOGIN_URL)
        soup = BeautifulSoup(login_page_response.text, "html.parser")

        # Find the hidden input with name="logintoken"
        token_input = soup.find("input", {"name": "logintoken"})
        if not token_input or not token_input.get("value"):
            raise HTTPException(status_code=500, detail="Could not find the logintoken on the login page")

        logintoken = token_input["value"]

        # 2) Build payload with credentials and logintoken
        login_payload = {
            'username': credentials.username,
            'password': credentials.password,
            'logintoken': logintoken
        }

        # 3) POST the credentials to log in
        login_response = session.post(LOGIN_URL, data=login_payload)
        
        if login_response.status_code != 200:
            raise HTTPException(status_code=401, detail="Login failed")

        # Get the Moodle session cookie
        moodle_session = session.cookies.get("MoodleSession")
        if not moodle_session:
            raise HTTPException(status_code=401, detail="Moodle session cookie not found")

        # 4) Request the courses page (used to extract the sesskey)
        courses_response = session.get(COURSES_URL)
        courses_html = courses_response.text

        # 5) Extract sesskey from the HTML using regex
        sesskey_match = re.search(r'"sesskey"\s*:\s*"([^"]+)"', courses_html)
        if not sesskey_match:
            raise HTTPException(status_code=500, detail="Session key not found")
        
        sesskey = sesskey_match.group(1)

        # (Optional) Retrieve profile page to extract user name and email
        profile_response = session.get(PROFILE_URL)
        profile_soup = BeautifulSoup(profile_response.text, "html.parser")
        name_element = profile_soup.select_one(".page-header-headings h1")
        user_name = name_element.get_text(strip=True) if name_element else "Unknown"

        dt_email = profile_soup.find("dt", string="Email address")
        if dt_email:
            dd_email = dt_email.find_next_sibling("dd")
            if dd_email:
                email_link = dd_email.find("a")
                user_email = email_link.get_text(strip=True) if email_link else "No email link found"
            else:
                user_email = "No email <dd> found"
        else:
            user_email = "Could not locate 'Email address' field"

        # Common headers for service requests
        common_headers = {
            "Content-Type": "application/json",
            "Cookie": f"MoodleSession={moodle_session}"
        }

        # Build the course service URL using the sesskey
        courses_service_url = COURSES_SERVICE_URL_TEMPLATE.format(sesskey)

        # Prepare the JSON payload for the course information request
        courses_payload = [
            {
                "index": 0,
                "methodname": "core_course_get_enrolled_courses_by_timeline_classification",
                "args": {
                    "offset": 0,
                    "limit": 0,
                    "classification": "all",
                    "sort": "fullname",
                    "customfieldname": "",
                    "customfieldvalue": ""
                }
            }
        ]

        # Make the POST request to get course information
        courses_service_response = requests.post(courses_service_url, headers=common_headers, json=courses_payload)
        if courses_service_response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to fetch course information")

        try:
            courses_service_data = courses_service_response.json()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error parsing courses service JSON: {str(e)}")

        # Build the calendar service URL using the sesskey
        calendar_service_url = CALENDAR_SERVICE_URL_TEMPLATE.format(sesskey)

        # Prepare the JSON payload for the calendar events request
        calendar_payload = [
            {
                "index": 0,
                "methodname": "core_calendar_get_action_events_by_timesort",
                "args": {
                    "limitnum": credentials.limit_num,
                    "timesortfrom": credentials.time_sort_from,
                    "timesortto": credentials.time_sort_to,
                    "limittononsuspendedevents": True
                }
            }
        ]

        # Make the POST request to get calendar events
        calendar_service_response = requests.post(calendar_service_url, headers=common_headers, json=calendar_payload)
        if calendar_service_response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to fetch calendar events")

        try:
            calendar_service_data = calendar_service_response.json()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error parsing calendar service JSON: {str(e)}")

        # Process courses data to remove courseimage field if needed
        if courses_service_data and 'data' in courses_service_data[0] and 'courses' in courses_service_data[0]['data']:
            for course in courses_service_data[0]['data']['courses']:
                if 'courseimage' in course:
                    del course['courseimage']
        
        # Process calendar events data to remove courseimage field if needed
        if calendar_service_data and 'data' in calendar_service_data[0] and 'events' in calendar_service_data[0]['data']:
            for event in calendar_service_data[0]['data']['events']:
                if 'course' in event and 'courseimage' in event['course']:
                    del event['course']['courseimage']
                    
        # Return all data in one response
        return {
            "user_info": {
                "name": user_name,
                "email": user_email
            },
            "courses": courses_service_data,
            "calendar_events": calendar_service_data
        }

    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Request error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

if __name__ == "__main__":
    uvicorn.run("vle_api:app", host="0.0.0.0", port=8000, reload=True)