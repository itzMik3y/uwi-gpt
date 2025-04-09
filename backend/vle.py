import os
import re
import json
import requests
from bs4 import BeautifulSoup

# URLs
LOGIN_URL = "https://vle.mona.uwi.edu/login/index.php"
COURSES_URL = "https://vle.mona.uwi.edu/my/courses.php"
PROFILE_URL = "https://vle.mona.uwi.edu/user/profile.php"  # For profile info if needed
# Service URL templates – one for courses, one for calendar events
COURSES_SERVICE_URL_TEMPLATE = "https://vle.mona.uwi.edu/lib/ajax/service.php?sesskey={}&info=core_course_get_enrolled_courses_by_timeline_classification"
CALENDAR_SERVICE_URL_TEMPLATE = "https://vle.mona.uwi.edu/lib/ajax/service.php?sesskey={}&info=core_calendar_get_action_events_by_timesort"

# Create a session to persist cookies
session = requests.Session()

# --- LOGIN AND SESSION SETUP ---

# 1) GET the login page to fetch the logintoken
login_page_response = session.get(LOGIN_URL)
soup = BeautifulSoup(login_page_response.text, "html.parser")

# Find the hidden input with name="logintoken"
token_input = soup.find("input", {"name": "logintoken"})
if not token_input or not token_input.get("value"):
    print("Could not find the logintoken on the login page!")
    exit(1)

logintoken = token_input["value"]
print("Found logintoken:", logintoken)

# 2) Build payload with credentials and logintoken
login_payload = {
    'username': '620150765',
    'password': 'd%Zj%2cq',
    'logintoken': logintoken
}

# 3) POST the credentials to log in
login_response = session.post(LOGIN_URL, data=login_payload)
print("Login status code:", login_response.status_code)

# Print the Moodle session cookie (named "MoodleSession")
moodle_session = session.cookies.get("MoodleSession")
if moodle_session:
    print("Moodle session cookie:", moodle_session)
else:
    print("Moodle session cookie not found!")

# 4) Request the courses page (used to extract the sesskey)
courses_response = session.get(COURSES_URL)
courses_html = courses_response.text

# 5) Extract sesskey from the HTML using regex
sesskey_match = re.search(r'"sesskey"\s*:\s*"([^"]+)"', courses_html)
if sesskey_match:
    sesskey = sesskey_match.group(1)
    print("Extracted sesskey:", sesskey)
else:
    print("sesskey not found!")
    exit(1)

# (Optional) Retrieve profile page to extract user name and email
profile_response = session.get(PROFILE_URL)
profile_soup = BeautifulSoup(profile_response.text, "html.parser")
name_element = profile_soup.select_one(".page-header-headings h1")
user_name = name_element.get_text(strip=True) if name_element else "Unknown"
print("Name:", user_name)
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
print("Email:", user_email)

# --- COMMON HEADERS FOR SERVICE REQUESTS ---
common_headers = {
    "Content-Type": "application/json",
    "Cookie": f"MoodleSession={moodle_session}"
}

# --- COURSE INFORMATION REQUEST ---

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
print("Courses service response status code:", courses_service_response.status_code)

try:
    courses_service_data = courses_service_response.json()
    print("Course information JSON response:")
    # Uncomment the line below to print the JSON in a formatted manner:
    # print(json.dumps(courses_service_data, indent=2))
except Exception as e:
    print("Error parsing courses service JSON:", e)
    exit(1)

# Save the course information JSON to a file
script_directory = os.path.dirname(os.path.abspath(__file__))
courses_json_path = os.path.join(script_directory, "courses.json")
with open(courses_json_path, "w", encoding="utf-8") as f:
    json.dump(courses_service_data, f, indent=2)
print("Course information saved to", courses_json_path)

# --- CALENDAR EVENTS REQUEST ---

# Build the calendar service URL using the sesskey
calendar_service_url = CALENDAR_SERVICE_URL_TEMPLATE.format(sesskey)

# Prepare the JSON payload for the calendar events request
calendar_payload = [
    {
        "index": 0,
        "methodname": "core_calendar_get_action_events_by_timesort",
        "args": {
            "limitnum": 6,
            "timesortfrom": 1744002000,
            "timesortto": 1744606800,
            "limittononsuspendedevents": True
        }
    }
]

# Make the POST request to get calendar events
calendar_service_response = requests.post(calendar_service_url, headers=common_headers, json=calendar_payload)
print("Calendar service response status code:", calendar_service_response.status_code)

try:
    calendar_service_data = calendar_service_response.json()
    print("Calendar events JSON response:")
    # Uncomment the line below to print the JSON in a formatted manner:
    # print(json.dumps(calendar_service_data, indent=2))
except Exception as e:
    print("Error parsing calendar service JSON:", e)
    exit(1)

# Save the calendar events JSON to a file
calendar_json_path = os.path.join(script_directory, "calendar_events.json")
with open(calendar_json_path, "w", encoding="utf-8") as f:
    json.dump(calendar_service_data, f, indent=2)
print("Calendar events saved to", calendar_json_path)
