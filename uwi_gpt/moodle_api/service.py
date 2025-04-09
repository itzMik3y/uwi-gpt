# moodle_api/service.py
import os
import re
import json
import requests
from bs4 import BeautifulSoup
from fastapi import HTTPException
from .models import MoodleCredentials # Relative import
import traceback # Import traceback for detailed logging

# Define URLs
LOGIN_URL = "https://vle.mona.uwi.edu/login/index.php"
COURSES_URL = "https://vle.mona.uwi.edu/my/courses.php"
PROFILE_URL = "https://vle.mona.uwi.edu/user/profile.php"
COURSES_SERVICE_URL_TEMPLATE = "https://vle.mona.uwi.edu/lib/ajax/service.php?sesskey={}&info=core_course_get_enrolled_courses_by_timeline_classification"
CALENDAR_SERVICE_URL_TEMPLATE = "https://vle.mona.uwi.edu/lib/ajax/service.php?sesskey={}&info=core_calendar_get_action_events_by_timesort"

def fetch_moodle_details(credentials: MoodleCredentials):
    """
    Logs into Moodle, scrapes profile, courses and calendar events.
    Removes courseimage data before returning.
    Also returns login token and sesskey for potential reuse.
    Raises HTTPException on failure.
    """
    print(f"Received credentials - Username: {credentials.username}, Password: {credentials.password}")
    session = requests.Session() # Use a session object for all requests to handle cookies
    try:
        # --- Steps 1-7 remain the same (Login, Sesskey, Profile Info) ---
        # 1) GET the login page to fetch the logintoken
        print("Fetching login page...")
        login_page_response = session.get(LOGIN_URL, timeout=15)
        login_page_response.raise_for_status()
        soup = BeautifulSoup(login_page_response.text, "html.parser")
        token_input = soup.find("input", {"name": "logintoken"})
        if not token_input or not token_input.get("value"):
            raise HTTPException(status_code=500, detail="Could not find logintoken")
        logintoken = token_input["value"]
        print("Login token found.")

        # 2) Build login payload (Using credentials passed to the function)
        login_payload = {
            'username': credentials.username,
            'password': credentials.password,
            'logintoken': logintoken
        }

        # 3) POST to log in (Using the session object)
        print("Attempting login...")
        login_response = session.post(LOGIN_URL, data=login_payload, timeout=15)
        login_response.raise_for_status()

        if "Invalid login, please try again" in login_response.text or LOGIN_URL in login_response.url:
             print("Login failed: Invalid credentials indicated.")
             raise HTTPException(status_code=401, detail="Login failed: Invalid credentials")

        moodle_session_cookie = session.cookies.get("MoodleSession")
        if not moodle_session_cookie:
            if "Dashboard" not in login_response.text and "My courses" not in login_response.text:
                 print("Login failed: Moodle session cookie not found and dashboard content missing.")
                 raise HTTPException(status_code=401, detail="Moodle session cookie not found after login attempt")
            else:
                 print("Warning: Moodle session cookie missing, but dashboard content detected. Proceeding.")
        print("Login successful.")

        # 4) Request courses page for sesskey (Using the session object)
        print("Fetching courses page for session key...")
        courses_response = session.get(COURSES_URL, timeout=15)
        courses_response.raise_for_status()
        courses_html = courses_response.text
        sesskey_match = re.search(r'"sesskey"\s*:\s*"([^"]+)"', courses_html)
        if not sesskey_match:
            print("Error: Session key (sesskey) not found on courses page.")
            raise HTTPException(status_code=500, detail="Session key (sesskey) not found")
        sesskey = sesskey_match.group(1)
        print(f"Session key found: {sesskey[:5]}...")

        # 6) Get profile info (Using the session object and improved scraping)
        user_name = "Unknown"
        user_email = "Not retrieved"
        try:
            print("Fetching profile info...")
            profile_response = session.get(PROFILE_URL, timeout=15)
            profile_response.raise_for_status()
            profile_soup = BeautifulSoup(profile_response.text, "html.parser")
            name_element = profile_soup.select_one(".page-header-headings h1")
            user_name = name_element.get_text(strip=True) if name_element else "Unknown"
            print(f"Profile name retrieved: {user_name}")
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
            print(f"Profile email retrieved: {user_email}")
        except Exception as profile_err:
            print(f"Warning: Could not retrieve profile info: {profile_err}")

        # 7) Prepare common elements for service calls
        common_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
        }
        courses_service_url = COURSES_SERVICE_URL_TEMPLATE.format(sesskey)
        calendar_service_url = CALENDAR_SERVICE_URL_TEMPLATE.format(sesskey)

        # 8) Call courses service using VERIFIED payload args from reference script
        print("Preparing courses service payload...")
        courses_payload = [
            {
                "index": 0,
                "methodname": "core_course_get_enrolled_courses_by_timeline_classification",
                "args": { "offset": 0, "limit": 0, "classification": "all", "sort": "fullname", "customfieldname": "", "customfieldvalue": "" }
            }
        ]
        print(f"Sending courses request to {courses_service_url} with payload: {json.dumps(courses_payload)}")
        courses_service_response = session.post(courses_service_url, headers=common_headers, json=courses_payload, timeout=20)
        courses_service_response.raise_for_status()
        courses_service_data = courses_service_response.json()
        print("Courses data received.")

        # 9) Call calendar service using VERIFIED payload args from reference script
        print("Preparing calendar service payload...")
        start_time = credentials.time_sort_from
        end_time = credentials.time_sort_to
        limit_num = credentials.limit_num
        calendar_payload = [
            {
                "index": 0,
                "methodname": "core_calendar_get_action_events_by_timesort",
                "args": { "limitnum": limit_num, "timesortfrom": start_time, "timesortto": end_time, "limittononsuspendedevents": True }
            }
        ]
        print(f"Sending calendar request to {calendar_service_url} with payload: {json.dumps(calendar_payload)}")
        calendar_service_response = session.post(calendar_service_url, headers=common_headers, json=calendar_payload, timeout=20)
        calendar_service_response.raise_for_status()
        calendar_service_data = calendar_service_response.json()
        print("Calendar data received.")

        # --- MODIFICATION START: Remove courseimage ---
        # 10) Process data (Remove course images before returning)
        print("Processing received data (removing course images)...")

        # Process Courses Data
        try:
            # Check the expected structure based on Moodle response
            if (isinstance(courses_service_data, list) and courses_service_data and
                isinstance(courses_service_data[0], dict) and 'data' in courses_service_data[0] and
                isinstance(courses_service_data[0]['data'], dict) and 'courses' in courses_service_data[0]['data'] and
                isinstance(courses_service_data[0]['data']['courses'], list)):

                for course in courses_service_data[0]['data']['courses']:
                    if isinstance(course, dict): # Make sure it's a dictionary
                        course.pop('courseimage', None) # Safely remove 'courseimage' if it exists
            else:
                 print("Warning: Unexpected structure in courses_service_data, skipping image removal for courses.")
        except Exception as proc_err:
            print(f"Warning: Error processing courses data to remove images: {proc_err}")

        # Process Calendar Events Data (Images are nested within event['course'])
        try:
            # Check the expected structure based on Moodle response
            if (isinstance(calendar_service_data, list) and calendar_service_data and
                isinstance(calendar_service_data[0], dict) and 'data' in calendar_service_data[0] and
                isinstance(calendar_service_data[0]['data'], dict) and 'events' in calendar_service_data[0]['data'] and
                isinstance(calendar_service_data[0]['data']['events'], list)):

                for event in calendar_service_data[0]['data']['events']:
                     # Check if the event has a course dict and that dict is actually a dict
                    if isinstance(event, dict) and 'course' in event and isinstance(event.get('course'), dict):
                        event['course'].pop('courseimage', None) # Safely remove from nested course dict
            else:
                 print("Warning: Unexpected structure in calendar_service_data, skipping image removal for calendar events.")
        except Exception as proc_err:
            print(f"Warning: Error processing calendar data to remove images: {proc_err}")
        # --- MODIFICATION END ---

        # Extract session cookie for potential reuse
        moodle_session_cookie = session.cookies.get("MoodleSession", "")
        print(f"Session cookie extracted: {moodle_session_cookie[:5]}..." if moodle_session_cookie else "No session cookie found")

        # 11) Return combined data (now without course images) and include auth tokens
        print("Returning combined data with auth tokens (images excluded).")
        # Extract the actual 'data' part from the list structure Moodle returns
        courses_result_data = courses_service_data[0].get('data', {}) if isinstance(courses_service_data, list) and courses_service_data else courses_service_data
        calendar_result_data = calendar_service_data[0].get('data', {}) if isinstance(calendar_service_data, list) and calendar_service_data else calendar_service_data

        return {
            "user_info": {
                "name": user_name,
                "email": user_email,
                "student_id": credentials.username
            },
            "courses": courses_result_data, # Return the inner 'data' object/dict
            "calendar_events": calendar_result_data, # Return the inner 'data' object/dict
            "auth_tokens": {
                "login_token": logintoken,
                "sesskey": sesskey,
                "moodle_session": moodle_session_cookie
            }
        }

    # Keep robust exception handling for the service
    except requests.exceptions.Timeout as e:
        print(f"Error: Request to Moodle timed out - {e}")
        raise HTTPException(status_code=504, detail="Request to Moodle timed out")
    except requests.exceptions.RequestException as e:
        print(f"Error: Moodle request error - {e}")
        raise HTTPException(status_code=502, detail=f"Error communicating with Moodle: {type(e).__name__}")
    except HTTPException as e:
        print(f"HTTP Exception encountered: Status {e.status_code}, Detail: {e.detail}")
        raise e
    except Exception as e:
        print(f"Error: Unexpected Moodle service error - {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred while fetching Moodle data: {type(e).__name__}")
    finally:
        if 'session' in locals() and session:
            session.close()
            print("HTTP session closed.")