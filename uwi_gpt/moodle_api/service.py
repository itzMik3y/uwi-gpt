# moodle_api/service.py
from datetime import datetime
import os
import re
import json
import logging
import asyncio
from typing import Optional, List, Dict

import requests
from bs4 import BeautifulSoup, Tag
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

# No need for sessionmaker here if called within request scope
# from sqlalchemy.orm import sessionmaker
import traceback

from auth.models import CourseSchedule

# Relative import for credentials models
from .models import MoodleCredentials, SASCredentials
from sqlalchemy.future import select

# Imports for the data saving function & helpers
from user_db.services import (
    get_course_by_id,
    create_course,
    get_term_by_user_and_code,
    create_term,
    enroll_user_in_course,
    create_or_update_course_grade,
    save_course_schedule,
)
from user_db.schemas import (
    CourseCreate,
    TermCreate,
    EnrollmentCreate,
    CourseGradeCreate,
)
from user_db.models import (
    Course,
    Term,
    User,
)  # User might be needed for type hints if helpers use it


# --- Logger ---
logger = logging.getLogger(__name__)

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
    print(
        f"Received credentials - Username: {credentials.username}, Password: {credentials.password}"
    )
    session = (
        requests.Session()
    )  # Use a session object for all requests to handle cookies
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
            "username": credentials.username,
            "password": credentials.password,
            "logintoken": logintoken,
        }

        # 3) POST to log in (Using the session object)
        print("Attempting login...")
        login_response = session.post(LOGIN_URL, data=login_payload, timeout=15)
        login_response.raise_for_status()

        if (
            "Invalid login, please try again" in login_response.text
            or LOGIN_URL in login_response.url
        ):
            print("Login failed: Invalid credentials indicated.")
            raise HTTPException(
                status_code=401, detail="Login failed: Invalid credentials"
            )

        moodle_session_cookie = session.cookies.get("MoodleSession")
        if not moodle_session_cookie:
            if (
                "Dashboard" not in login_response.text
                and "My courses" not in login_response.text
            ):
                print(
                    "Login failed: Moodle session cookie not found and dashboard content missing."
                )
                raise HTTPException(
                    status_code=401,
                    detail="Moodle session cookie not found after login attempt",
                )
            else:
                print(
                    "Warning: Moodle session cookie missing, but dashboard content detected. Proceeding."
                )
        print("Login successful.")

        # 4) Request courses page for sesskey (Using the session object)
        print("Fetching courses page for session key...")
        courses_response = session.get(COURSES_URL, timeout=15)
        courses_response.raise_for_status()
        courses_html = courses_response.text
        sesskey_match = re.search(r'"sesskey"\s*:\s*"([^"]+)"', courses_html)
        if not sesskey_match:
            print("Error: Session key (sesskey) not found on courses page.")
            raise HTTPException(
                status_code=500, detail="Session key (sesskey) not found"
            )
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
                    user_email = (
                        email_link.get_text(strip=True)
                        if email_link
                        else "No email link found"
                    )
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
                "args": {
                    "offset": 0,
                    "limit": 0,
                    "classification": "all",
                    "sort": "fullname",
                    "customfieldname": "",
                    "customfieldvalue": "",
                },
            }
        ]
        print(
            f"Sending courses request to {courses_service_url} with payload: {json.dumps(courses_payload)}"
        )
        courses_service_response = session.post(
            courses_service_url,
            headers=common_headers,
            json=courses_payload,
            timeout=20,
        )
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
                "args": {
                    "limitnum": limit_num,
                    "timesortfrom": start_time,
                    "timesortto": end_time,
                    "limittononsuspendedevents": True,
                },
            }
        ]
        print(
            f"Sending calendar request to {calendar_service_url} with payload: {json.dumps(calendar_payload)}"
        )
        calendar_service_response = session.post(
            calendar_service_url,
            headers=common_headers,
            json=calendar_payload,
            timeout=20,
        )
        calendar_service_response.raise_for_status()
        calendar_service_data = calendar_service_response.json()
        print("Calendar data received.")

        # --- MODIFICATION START: Remove courseimage ---
        # 10) Process data (Remove course images before returning)
        print("Processing received data (removing course images)...")

        # Process Courses Data
        try:
            # Check the expected structure based on Moodle response
            if (
                isinstance(courses_service_data, list)
                and courses_service_data
                and isinstance(courses_service_data[0], dict)
                and "data" in courses_service_data[0]
                and isinstance(courses_service_data[0]["data"], dict)
                and "courses" in courses_service_data[0]["data"]
                and isinstance(courses_service_data[0]["data"]["courses"], list)
            ):

                for course in courses_service_data[0]["data"]["courses"]:
                    if isinstance(course, dict):  # Make sure it's a dictionary
                        course.pop(
                            "courseimage", None
                        )  # Safely remove 'courseimage' if it exists
            else:
                print(
                    "Warning: Unexpected structure in courses_service_data, skipping image removal for courses."
                )
        except Exception as proc_err:
            print(
                f"Warning: Error processing courses data to remove images: {proc_err}"
            )

        # Process Calendar Events Data (Images are nested within event['course'])
        try:
            # Check the expected structure based on Moodle response
            if (
                isinstance(calendar_service_data, list)
                and calendar_service_data
                and isinstance(calendar_service_data[0], dict)
                and "data" in calendar_service_data[0]
                and isinstance(calendar_service_data[0]["data"], dict)
                and "events" in calendar_service_data[0]["data"]
                and isinstance(calendar_service_data[0]["data"]["events"], list)
            ):

                for event in calendar_service_data[0]["data"]["events"]:
                    # Check if the event has a course dict and that dict is actually a dict
                    if (
                        isinstance(event, dict)
                        and "course" in event
                        and isinstance(event.get("course"), dict)
                    ):
                        event["course"].pop(
                            "courseimage", None
                        )  # Safely remove from nested course dict
            else:
                print(
                    "Warning: Unexpected structure in calendar_service_data, skipping image removal for calendar events."
                )
        except Exception as proc_err:
            print(
                f"Warning: Error processing calendar data to remove images: {proc_err}"
            )
        # --- MODIFICATION END ---

        # Extract session cookie for potential reuse
        moodle_session_cookie = session.cookies.get("MoodleSession", "")
        print(
            f"Session cookie extracted: {moodle_session_cookie[:5]}..."
            if moodle_session_cookie
            else "No session cookie found"
        )

        # 11) Return combined data (now without course images) and include auth tokens
        print("Returning combined data with auth tokens (images excluded).")
        # Extract the actual 'data' part from the list structure Moodle returns
        courses_result_data = (
            courses_service_data[0].get("data", {})
            if isinstance(courses_service_data, list) and courses_service_data
            else courses_service_data
        )
        calendar_result_data = (
            calendar_service_data[0].get("data", {})
            if isinstance(calendar_service_data, list) and calendar_service_data
            else calendar_service_data
        )

        return {
            "user_info": {
                "name": user_name,
                "email": user_email,
                "student_id": credentials.username,
            },
            "courses": courses_result_data,  # Return the inner 'data' object/dict
            "calendar_events": calendar_result_data,  # Return the inner 'data' object/dict
            "auth_tokens": {
                "login_token": logintoken,
                "sesskey": sesskey,
                "moodle_session": moodle_session_cookie,
            },
        }

    # Keep robust exception handling for the service
    except requests.exceptions.Timeout as e:
        print(f"Error: Request to Moodle timed out - {e}")
        raise HTTPException(status_code=504, detail="Request to Moodle timed out")
    except requests.exceptions.RequestException as e:
        print(f"Error: Moodle request error - {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Error communicating with Moodle: {type(e).__name__}",
        )
    except HTTPException as e:
        print(f"HTTP Exception encountered: Status {e.status_code}, Detail: {e.detail}")
        raise e
    except Exception as e:
        print(f"Error: Unexpected Moodle service error - {e}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred while fetching Moodle data: {type(e).__name__}",
        )
    finally:
        if "session" in locals() and session:
            session.close()
            print("HTTP session closed.")


def fetch_uwi_sas_details(credentials: SASCredentials):
    session = requests.Session()

    headers = {"User-Agent": "Mozilla/5.0"}

    # Step 1: Start at Moodle login page to trigger redirects
    moodle_login_url = "https://ban.mona.uwi.edu:9077/ssb8x/twbkwbis.P_WWWLogin"
    initial_response = session.get(
        moodle_login_url, headers=headers, allow_redirects=True
    )

    if initial_response.history:
        print("Redirect history:")
        for resp in initial_response.history:
            print(f"{resp.status_code} -> {resp.url}")
        print(f"Final URL: {initial_response.url}")

    # Step 2: Let redirects take us to the UWI Identity login page
    soup = BeautifulSoup(initial_response.text, "html.parser")
    session_data_key_input = soup.find("input", {"name": "sessionDataKey"})

    if not session_data_key_input:
        return {
            "success": False,
            "message": "Failed to extract sessionDataKey. UWI SSO might have changed.",
        }

    session_data_key = session_data_key_input.get("value")

    # Step 3: Prepare login form data
    login_url = "https://ban.mona.uwi.edu:9443/commonauth"
    form_data = {
        "usernameUserInput": credentials.username,
        "username": f"{credentials.username}@carbon.super",
        "password": credentials.password,
        "sessionDataKey": session_data_key,
        # "chkRemember": "on"
    }

    headers_form = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0",
    }

    # Step 4: Submit login POST request
    login_response = session.post(
        login_url, data=form_data, headers=headers_form, allow_redirects=True
    )

    if login_response.history:
        print("Redirect history:")
        for resp in login_response.history:
            print(f"{resp.status_code} -> {resp.url}")
        print(f"Final URL: {login_response.url}")

    # Confirm we're logged in
    if "General Menu" in login_response.text or "bmenu.P_MainMnu" in login_response.url:
        print("Login successful!")
    else:
        print("Login may have failed. Check response.")

    # ===== TRANSCRIPT DATA RETRIEVAL =====
    gpa_calc_page_url = "https://ban.mona.uwi.edu:9077/ssb8x/uwm_gpacalculator.gpa_ssb_student_unofficial"
    gpa_form_subm_page = session.get(gpa_calc_page_url, headers=headers)

    soup = BeautifulSoup(gpa_form_subm_page.text, "html.parser")

    pidm_input = soup.find("input", {"name": "p_pidm"})
    radio_input = soup.find("input", {"name": "p_degr_seq", "type": "radio"})

    if not pidm_input or not radio_input:
        print("❌ Could not find necessary form inputs. Check if session expired.")
        return {
            "success": False,
            "message": "Could not find necessary form inputs. Check if session expired.",
        }
    else:
        p_pidm = pidm_input.get("value")
        p_degr_seq = radio_input.get("value")  # e.g., "1:202210"

        # Step 7: Submit the GPA form
        submit_url = (
            "https://ban.mona.uwi.edu:9077/ssb8x/uwm_gpacalculator.process_gpa_uwi"
        )
        form_payload = {"p_pidm": p_pidm, "p_degr_seq": p_degr_seq}

        gpa_courses_page = session.post(
            submit_url, data=form_payload, headers=headers_form
        )

        reset_payload = {
            "p_pidm": p_pidm,
            "p_degr_seq": p_degr_seq,
            "v_user": p_pidm,  # same as s_pidm
            "trm_in": "202210",  # default term or the one you want to reset
            "crs_in": "",
            "grd_in": "***",
            "btnSubmit": "RESET",
        }

        gpa_action_url = (
            "https://ban.mona.uwi.edu:9077/ssb8x/uwm_gpacalculator.process_gpa"
        )

        reset_gpa_courses_page = session.post(
            gpa_action_url, data=reset_payload, headers=headers_form
        )

        if "GPA" in reset_gpa_courses_page.text:
            print("✅ Form reset successfully!")
        else:
            print("⚠️ Form reset may have failed.")

        calculate_payload = {
            "s_pidm": p_pidm,
            "p_degr_seq": p_degr_seq,
            "v_user": p_pidm,
            "trm_in": "202210",  # You can change to latest term if needed
            "crs_in": "",
            "grd_in": "***",
            "btnSubmit": "CALCULATE GPA",
        }

        target_page = session.post(
            gpa_action_url, data=calculate_payload, headers=headers_form
        )

        print("this is the target page url: ", target_page.url)

        def _safe_float(value_str):
            """Safely convert a string to float, returning None on failure."""
            try:
                # Remove any non-numeric characters except '.' and '-'
                cleaned_str = re.sub(r"[^0-9.-]", "", value_str)
                if cleaned_str:
                    return float(cleaned_str)
            except (ValueError, TypeError):
                pass
            return None

        def _parse_course_cells(cells):
            """Helper function to parse cells of a course row."""
            if not cells or len(cells) < 5:
                return None

            course_data = {}
            try:
                # Course Code (in the first cell's link)
                course_link = cells[0].find("a")
                if not course_link:
                    return None  # Not a standard course row start
                course_data["course_code"] = course_link.text.strip()
                # Validate course code format (allowing optional '+')
                if not re.match(r"^[A-Z]{3,4}\d{4}\+?$", course_data["course_code"]):
                    return None  # Doesn't look like a course code cell

                # Other details
                course_data["course_title"] = (
                    cells[1].text.strip() if len(cells) > 1 else ""
                )
                course_data["credit_hours"] = (
                    _safe_float(cells[2].text.strip()) if len(cells) > 2 else 0.0
                )
                course_data["grade_earned"] = (
                    cells[3].text.strip() if len(cells) > 3 else ""
                )
                course_data["whatif_grade"] = (
                    cells[4].text.strip() if len(cells) > 4 else ""
                )

                return course_data
            except (AttributeError, IndexError, ValueError) as e:
                print(f"Error parsing course cells: {e} - Row Cells: {cells}")
                return None

        def parse_transcript_data(html_content):
            """
            Parse academic transcript data from HTML content, handling complex row spans.

            Args:
                html_content: The HTML content of the transcript page

            Returns:
                A dictionary containing structured transcript data
            """
            soup = BeautifulSoup(html_content, "html.parser")

            # Extract student info
            student_id = None
            student_name = "Unknown"
            title_p = soup.find("p", {"class": "centeraligntext"})
            if title_p:
                # More robust search for name and ID
                match = re.search(
                    r"for<br/>\s*(.*?)\s*\((\d+)\)",
                    title_p.prettify(),
                    re.IGNORECASE | re.DOTALL,
                )
                if match:
                    student_name = match.group(1).strip()
                    student_id = match.group(2)
                else:  # Fallback to original regex if needed
                    match = re.search(r"([A-Za-z\s]+)\s*\((\d+)\)", title_p.text)
                    if match:
                        student_name = match.group(1).strip()
                        student_id = match.group(2)

            # Initialize the result structure
            result = {
                "student_name": student_name,
                "student_id": student_id,
                "terms": [],
                "overall": {
                    "cumulative_gpa": None,
                    "degree_gpa": None,
                    "total_credits_earned": None,
                },
            }

            # Find the main data table
            data_table = soup.find("table", {"class": "dataentrytable", "width": "890"})
            if not data_table:
                print("Could not find the main data table")
                return result

            # Get all direct child rows of the table body (or table itself if no tbody)
            table_body = (
                data_table.find("tbody") if data_table.find("tbody") else data_table
            )
            rows = table_body.find_all("tr", recursive=False)

            current_term_data = None

            # Iterate through rows skipping the header
            for i in range(1, len(rows)):
                row = rows[i]
                cells = row.find_all("td", recursive=False)  # Get direct child cells

                if not cells:
                    continue

                # Check if this row starts a new term
                # A term row starts with a cell having colspan=2 and contains the term code
                term_header_cell = cells[0]
                is_term_start_row = (
                    term_header_cell.get("colspan") == "2"
                    and term_header_cell.find("p", {"class": "centeraligntext"})
                    and term_header_cell.find("b")
                )

                if is_term_start_row:
                    # --- New Term Found ---
                    # Save previous term if exists
                    if current_term_data:
                        result["terms"].append(current_term_data)

                    term_code_b = term_header_cell.find("b")
                    term_code = term_code_b.text.strip() if term_code_b else None

                    # Validate term code and initialize
                    if term_code and re.match(r"^\d{6}$", term_code):
                        current_term_data = {
                            "term_code": term_code,
                            "courses": [],
                            "semester_gpa": None,
                            "cumulative_gpa": None,
                            "degree_gpa": None,
                            "credits_earned_to_date": None,
                        }

                        # --- Extract GPA/Credits and First Course from THIS row ---
                        row_cells_with_data = [
                            cell for cell in cells if isinstance(cell, Tag)
                        ]

                        # Identify GPA/Credit cells (usually have rowspan and specific classes/positions)
                        # We target them from the end, assuming structure consistency
                        gpa_credit_cells = [
                            c for c in row_cells_with_data if c.has_attr("rowspan")
                        ]

                        try:
                            # Credits Earned (dewhite, 4th from end with rowspan)
                            credits_td = (
                                gpa_credit_cells[-4]
                                if len(gpa_credit_cells) >= 4
                                else None
                            )
                            if (
                                credits_td
                                and credits_td.get("class") == ["dewhite"]
                                and "Yr:" in credits_td.text
                            ):
                                credits_text = credits_td.text.strip()
                                total_credits = 0
                                for year_match in re.finditer(
                                    r"Yr:\s*\d+\s*\((\d+)\)", credits_text
                                ):
                                    total_credits += int(year_match.group(1))
                                current_term_data["credits_earned_to_date"] = (
                                    total_credits
                                )

                            # Semester GPA (dedefault, 3rd from end with rowspan)
                            sem_gpa_td = (
                                gpa_credit_cells[-3]
                                if len(gpa_credit_cells) >= 3
                                else None
                            )
                            if sem_gpa_td and sem_gpa_td.get("class") == ["dedefault"]:
                                b_tag = sem_gpa_td.find("b")
                                if b_tag:
                                    current_term_data["semester_gpa"] = _safe_float(
                                        b_tag.text
                                    )

                            # Cumulative GPA (dewhite, 2nd from end with rowspan)
                            cum_gpa_td = (
                                gpa_credit_cells[-2]
                                if len(gpa_credit_cells) >= 2
                                else None
                            )
                            if cum_gpa_td and cum_gpa_td.get("class") == ["dewhite"]:
                                b_tag = cum_gpa_td.find("b")
                                if b_tag:
                                    current_term_data["cumulative_gpa"] = _safe_float(
                                        b_tag.text
                                    )

                            # Degree GPA (dedefault, last cell with rowspan)
                            deg_gpa_td = (
                                gpa_credit_cells[-1]
                                if len(gpa_credit_cells) >= 1
                                else None
                            )
                            if deg_gpa_td and deg_gpa_td.get("class") == ["dedefault"]:
                                b_tag = deg_gpa_td.find("b")
                                # Handle potentially empty <b> tag for Degree GPA
                                if b_tag and b_tag.text.strip():
                                    current_term_data["degree_gpa"] = _safe_float(
                                        b_tag.text
                                    )
                                else:
                                    current_term_data["degree_gpa"] = (
                                        None  # Explicitly None if empty
                                    )

                        except IndexError as e:
                            print(
                                f"Warning: Could not find expected GPA/Credit cell in term {term_code}: {e}"
                            )
                        except ValueError as e:
                            print(
                                f"Warning: Could not parse number in GPA/Credit cell in term {term_code}: {e}"
                            )

                        # --- Parse the FIRST course from the remaining cells in THIS row ---
                        # Cells for the first course start after the initial colspan=2 cell
                        first_course_cells = row_cells_with_data[1:]
                        # Adjust indices for course data extraction as the first two cells are missing compared to subsequent rows
                        # CourseCode(a), Title, CreditHrs, GradeEarned, WhatIfGrade, Source, GPA Hrs, Qual Pts
                        # We need cells corresponding to indices 1 through 5 relative to the *start* of the course data
                        course_cells_for_parsing = []
                        # Course Code is in cell 1 (index 0 of first_course_cells)
                        course_cells_for_parsing.append(first_course_cells[0])
                        # Title is in cell 2 (index 1 of first_course_cells)
                        course_cells_for_parsing.append(first_course_cells[1])
                        # Credit Hours is in cell 3 (index 2 of first_course_cells)
                        course_cells_for_parsing.append(first_course_cells[2])
                        # Grade Earned is in cell 4 (index 3 of first_course_cells)
                        course_cells_for_parsing.append(first_course_cells[3])
                        # WhatIf Grade is in cell 5 (index 4 of first_course_cells)
                        course_cells_for_parsing.append(first_course_cells[4])

                        if (
                            len(first_course_cells) >= 5
                        ):  # Need at least 5 cells for basic course info
                            course_data = _parse_course_cells(course_cells_for_parsing)
                        if course_data:
                            current_term_data["courses"].append(course_data)
                    else:
                        # Invalid term code found where expected
                        if current_term_data:  # Save previous valid term
                            result["terms"].append(current_term_data)
                        current_term_data = None  # Reset current term

                elif current_term_data is not None and len(cells) > 1:
                    # --- This is potentially a subsequent course row for the current term ---
                    # These rows lack the first two cells due to the term header's rowspan
                    # The first cell available IS the course code cell
                    course_data = _parse_course_cells(
                        cells
                    )  # Pass the full list of cells found
                    if course_data:
                        current_term_data["courses"].append(course_data)

            # Add the last processed term if it exists
            if current_term_data:
                result["terms"].append(current_term_data)

            # Update the overall info from the most recent term found (first in the list)
            # Note: The HTML provided shows terms in reverse chronological order.
            if result["terms"]:
                most_recent_term = result["terms"][0]
                # Use the cumulative/degree GPA from the *most recent* term record as the overall
                result["overall"]["cumulative_gpa"] = most_recent_term.get(
                    "cumulative_gpa"
                )
                result["overall"]["degree_gpa"] = most_recent_term.get("degree_gpa")
                # Total credits earned should also come from the most recent term record
                result["overall"]["total_credits_earned"] = most_recent_term.get(
                    "credits_earned_to_date"
                )

            return result

        transcript_data = parse_transcript_data(target_page.text)

        # ===== MAJOR/MINOR INFO RETRIEVAL =====

        # Submit term for accessing student details
        term_submit_page = "https://ban.mona.uwi.edu:9077/ssb8x/bwskflib.P_SelDefTerm"
        term_submit_resp = session.get(term_submit_page, headers=headers)
        term_soup = BeautifulSoup(term_submit_resp.text, "html.parser")

        term_hidden_inputs = term_soup.find("input", {"name": "name_var"})
        if not term_hidden_inputs:
            print("Warning: Could not find term selection inputs")
            # Continue with partial data rather than failing completely
            student_info = {"Majors": [], "Minors": [], "Faculty": None}
        else:
            term_hidden_value = term_hidden_inputs.get("value")
            term_select = "202420"  # hardcoded for now (2024/2025 semester 2)

            term_payload = {
                "name_var": term_hidden_value,
                "term_in": term_select,
            }

            student_registration_page = (
                "https://ban.mona.uwi.edu:9077/ssb8x/bwcklibs.P_StoreTerm"
            )
            student_registration_resp = session.post(
                student_registration_page, data=term_payload, headers=headers_form
            )

            # Access the major/minor info page
            fac_maj_min_page = (
                "https://ban.mona.uwi.edu:9077/ssb8x/UWM_CHANGE_MAJOR.P_DisplayHello"
            )
            fac_maj_min_resp = session.get(fac_maj_min_page, headers=headers)

            def parse_student_info(html_content):
                soup = BeautifulSoup(html_content, "html.parser")
                info = {"Majors": [], "Minors": [], "Faculty": None}
                rows = soup.find_all("tr")

                for row in rows:
                    cells = row.find_all("td")
                    if len(cells) >= 4:
                        header1 = cells[0].get_text(strip=True)
                        data1 = (
                            cells[1].find("b").get_text(strip=True)
                            if cells[1].find("b")
                            else ""
                        )
                        header2 = cells[2].get_text(strip=True)
                        data2 = (
                            cells[3].find("b").get_text(strip=True)
                            if cells[3].find("b")
                            else ""
                        )

                        if data1 and "Term" not in data1:
                            if "Major" in header1:
                                info["Majors"].append(data1)
                            if "Minor" in header1:
                                info["Minors"].append(data1)
                            if "Faculty/College" in header1:
                                info["Faculty"] = data1

                        if data2 and "Term" not in data2:
                            if "Major" in header2:
                                info["Majors"].append(data2)
                            if "Minor" in header2:
                                info["Minors"].append(data2)
                            if "Faculty/College" in header2:
                                info["Faculty"] = data2

                return info

            student_info = parse_student_info(fac_maj_min_resp.text)
            print(
                f"Found student info: {len(student_info['Majors'])} majors, {len(student_info['Minors'])} minors"
            )

        # ===== CALENDAR - SAS - RETRIEVAL =====

        target_page = "https://ban.mona.uwi.edu:9077/ssb8x/bwskfshd.P_CrseSchdDetl"

        result_target_page = session.get(target_page, headers=headers)
        # print("text of target page, ", result_target_page.text)
        # print("Current URL: ", result_target_page.url)

        # 1. Status code + final URL
        print("→ Status code:", result_target_page.status_code)
        print("→ Final URL:  ", result_target_page.url)

        # 2. Redirect history
        if result_target_page.history:
            print("→ Redirect chain:")
            for resp in result_target_page.history:
                print("   ", resp.status_code, resp.url)
        else:
            print("→ No redirects")

        target_soup = BeautifulSoup(result_target_page.text, "html.parser")

        # Option A: Look for the “Total Credit Hours” text
        if "Total Credit Hours" in result_target_page.text:
            print("✅ Found ‘Total Credit Hours’ – looks like the right page")
        else:
            print("❌ ‘Total Credit Hours’ not found – wrong page or not logged in")

        # Option B: Look for the very first <caption class="captiontext">
        first_caption = target_soup.find("caption", class_="captiontext")
        if first_caption:
            print("✅ First caption:", first_caption.get_text(strip=True))
        else:
            print("❌ No <caption class='captiontext'> – schedule tables missing")

        def parse_course_schedules(soup: BeautifulSoup):
            print("Starting parse_course_schedules()")

            # 0. Gather all the tables
            all_tables = soup.find_all("table", class_="datadisplaytable")
            print(f"Total datadisplaytable tables found: {len(all_tables)}")
            for idx, tbl in enumerate(all_tables, 1):
                summary = tbl.get("summary", "<no summary>")
                caption_tag = tbl.find("caption")
                caption = (
                    caption_tag.get_text(strip=True) if caption_tag else "<no caption>"
                )
                print(f" Table #{idx}: summary={summary!r}, caption={caption!r}")

            # 1. Identify the “detail” tables (everything except the Meeting Times tables)
            detail_tables = [
                tbl
                for tbl in all_tables
                if tbl.find("caption")
                and tbl.find("caption").get_text(strip=True)
                != "Scheduled Meeting Times"
            ]
            print(f"Filtered detail tables: {len(detail_tables)}")

            courses = {}

            for i, detail in enumerate(detail_tables, 1):
                raw_caption = detail.find("caption").get_text(strip=True)
                print(f"\n--- Detail table #{i}: caption = {raw_caption!r} ---")

                # split "Data Science Principles - COMP 3162 - B01"
                parts = [p.strip() for p in raw_caption.split(" - ")]
                if len(parts) != 3:
                    print(f" WARNING: caption didn’t split into 3 parts: {parts}")
                    continue
                course_title, course_code, section = parts
                print(
                    f" Parsed → title={course_title!r}, code={course_code!r}, section={section!r}"
                )

                # grab Level & Campus
                def get_field(label):
                    th = detail.find(
                        "th", string=lambda txt: txt and label.lower() in txt.lower()
                    )
                    if not th:
                        print(f"  {label!r} not found")
                        return None
                    td = th.find_next_sibling(["td", "TD"])
                    text = td.get_text(strip=True)
                    print(f"  {label!r} → {text}")
                    return text

                level = get_field("Level:")
                campus = get_field("Campus:")

                # 2. Find the very next table as the schedule table
                next_idx = all_tables.index(detail) + 1
                if next_idx >= len(all_tables):
                    print("WARNING: No next table for Meeting Times")
                    continue
                sched_tbl = all_tables[next_idx]
                sched_caption = sched_tbl.find("caption").get_text(strip=True)
                if sched_caption != "Scheduled Meeting Times":
                    print(
                        f"WARNING: Expected 'Scheduled Meeting Times' but got {sched_caption!r}"
                    )
                    continue
                print("  Found corresponding schedule table")

                # 3. Map headers → indices
                headers = [
                    th.get_text(strip=True)
                    for th in sched_tbl.find("tr").find_all("th")
                ]
                print(f"  Schedule headers: {headers}")
                idx_map = {h: j for j, h in enumerate(headers)}

                # 4. Parse each row
                for ridx, row in enumerate(sched_tbl.find_all("tr")[1:], start=1):
                    cols = row.find_all("td")
                    raw_cols = [c.get_text(strip=True) for c in cols]
                    print(f"  Row #{ridx} raw: {raw_cols}")

                    def parse_time_range(time_str):
                        try:
                            start, end = [t.strip() for t in time_str.split("-")]
                            return start, end
                        except Exception:
                            return None, None

                    def parse_date_range(date_range_str):
                        try:
                            start_str, end_str = [
                                d.strip() for d in date_range_str.split("-")
                            ]
                            start_date = datetime.strptime(
                                start_str, "%b %d, %Y"
                            ).date()
                            end_date = datetime.strptime(end_str, "%b %d, %Y").date()
                            return start_date, end_date
                        except Exception:
                            return None, None

                    time_str = cols[idx_map["Time"]].get_text(strip=True)
                    date_range_str = cols[idx_map["Date Range"]].get_text(strip=True)

                    start_time, end_time = parse_time_range(time_str)
                    start_date, end_date = parse_date_range(date_range_str)

                    # build your entry
                    entry = {
                        "instructor": cols[idx_map["Instructors"]].get_text(strip=True),
                        "level": level,
                        # this is the column “Schedule Type” (Lab/Lecture/etc)
                        "session_type": cols[idx_map["Schedule Type"]].get_text(
                            strip=True
                        ),
                        "campus": campus,
                        "where": cols[idx_map["Where"]]
                        .get_text(strip=True)
                        .replace("Located:", "")
                        .strip(),
                        "date_range": date_range_str,
                        "start_date": start_date,
                        "end_date": end_date,
                        "time": time_str,
                        "start_time": start_time,
                        "end_time": end_time,
                    }
                    print(f"  Parsed entry: {entry}")

                    # 5. Group into our courses dict
                    courses.setdefault(
                        course_code, {"title": course_title, "sections": {}}
                    )
                    courses[course_code]["sections"].setdefault(section, [])
                    courses[course_code]["sections"][section].append(entry)

            print(f"\nFinished parsing: found {len(courses)} course(s)")
            return courses

        # Now, only if those checks pass, you can call your parse_course_schedules()
        if (
            result_target_page.status_code == 200
            and not result_target_page.history
            and first_caption
        ):
            course_schedules = parse_course_schedules(target_soup)
            print(f"Parsed {len(course_schedules)} schedule entries")
        else:
            logger.debug(
                f"Failed to parse course schedules. Skipping. Status code: {result_target_page.status_code}, History: {result_target_page.history}",
                exc_info=True,
            )
            course_schedules = []

        # Combine the data and return
        transcript_data["student_info"] = {
            "majors": student_info["Majors"],
            "minors": student_info["Minors"],
            "faculty": student_info["Faculty"],
            "calendar": course_schedules,
        }

        return {
            "success": True,
            "data": transcript_data,
        }


async def get_or_create_course(db: AsyncSession, course_data: CourseCreate) -> Course:
    """Check if a course exists by ID, if not create it. Relies on caller for commit."""
    existing_course = await get_course_by_id(db, course_data.id)
    if existing_course:
        return existing_course
    try:
        # Assuming create_course adds and session commit happens later
        return await create_course(db, course_data)
    except Exception as e:
        # Log race condition without rollback, try fetch again
        logger.warning(
            f"Race condition/Error creating course {course_data.id}. Re-fetching.",
            exc_info=True,
        )
        await db.flush()  # Flush to ensure any previous adds are processed before fetch
        existing_course = await get_course_by_id(db, course_data.id)
        if existing_course:
            return existing_course
        logger.error(
            f"Failed to get or create course {course_data.id} after re-fetch.",
            exc_info=True,
        )
        raise  # Re-raise original error


async def update_or_create_term(db: AsyncSession, term_data: TermCreate) -> Term:
    """Update existing term or create a new one. Relies on caller for commit."""
    existing_term = await get_term_by_user_and_code(
        db, term_data.user_id, term_data.term_code
    )
    if existing_term:
        updated = False
        if (
            term_data.semester_gpa is not None
            and existing_term.semester_gpa != term_data.semester_gpa
        ):
            existing_term.semester_gpa = term_data.semester_gpa
            updated = True
        if (
            term_data.cumulative_gpa is not None
            and existing_term.cumulative_gpa != term_data.cumulative_gpa
        ):
            existing_term.cumulative_gpa = term_data.cumulative_gpa
            updated = True
        if (
            term_data.degree_gpa is not None
            and existing_term.degree_gpa != term_data.degree_gpa
        ):
            existing_term.degree_gpa = term_data.degree_gpa
            updated = True
        if (
            term_data.credits_earned_to_date is not None
            and existing_term.credits_earned_to_date != term_data.credits_earned_to_date
        ):
            existing_term.credits_earned_to_date = term_data.credits_earned_to_date
            updated = True
        if updated:
            await db.flush()  # Flush changes to session
            await db.refresh(existing_term)  # Refresh state if needed
        return existing_term
    else:
        # Assuming create_term adds and session commit happens later
        new_term = Term(**term_data.dict())
        db.add(new_term)
        await db.flush()  # Flush to make sure it's added before potential use
        await db.refresh(new_term)
        return new_term
        # return await create_term(db, term_data) # Use above if create_term commits


async def save_initial_scraped_data(
    db: AsyncSession,  # Accept session directly when called by route
    user_id: int,
    moodle_payload: Optional[dict],
    sas_payload: Optional[dict],
):
    """
    Synchronously processes and saves scraped data within the provided DB session.
    Raises ValueError on failure. Assumes caller handles commit/rollback.
    """
    logger.info(f"SYNC SAVE: Saving initial scraped data for user {user_id}")
    # Wrap operations for Moodle and SAS separately to pinpoint errors
    try:
        # --- Process Moodle ---
        if moodle_payload and isinstance(moodle_payload.get("courses"), dict):
            current_term_data = TermCreate(term_code="CURRENT", user_id=user_id)
            current_term = await update_or_create_term(
                db, current_term_data
            )  # Pass session

            moodle_courses = moodle_payload.get("courses", {}).get("courses", [])
            logger.info(
                f"SYNC SAVE: Processing {len(moodle_courses)} Moodle courses for user {user_id}"
            )
            for c in moodle_courses:
                course_id = c.get("id")
                if course_id is None:
                    logger.warning(
                        f"Skipping Moodle course, missing ID: {c.get('fullname')}"
                    )
                    continue
                try:
                    course_id = int(course_id)
                except (ValueError, TypeError):
                    logger.warning(
                        f"Skipping Moodle course, invalid ID type: {c.get('fullname')}"
                    )
                    continue

                course_create_data = CourseCreate(
                    id=course_id,
                    fullname=c.get("fullname", "?"),
                    shortname=c.get("shortname", ""),
                    idnumber=c.get("idnumber", ""),
                    summary=c.get("summary", ""),
                    summaryformat=int(c.get("summaryformat", 1)),
                    startdate=int(c.get("startdate", 0)),
                    enddate=int(c.get("enddate", 0)),
                    visible=bool(c.get("visible", False)),
                    showactivitydates=bool(c.get("showactivitydates", False)),
                    showcompletionconditions=bool(
                        c.get("showcompletionconditions", False)
                    ),
                    fullnamedisplay=c.get("fullnamedisplay", c.get("fullname", "?")),
                    viewurl=c.get("viewurl", ""),
                    coursecategory=c.get("coursecategory", ""),
                )
                course = await get_or_create_course(
                    db, course_create_data
                )  # Pass session

                enrollment_data = EnrollmentCreate(
                    user_id=user_id,
                    course_id=course.id,
                    term_id=current_term.id,
                    course_code=course.shortname,
                    course_title=course.fullname,
                    # TODO: Determine actual credit hours if possible, defaulting to 3.0
                    credit_hours=float(
                        c.get("credit_hours", 3.0)
                    ),  # Example: Try getting from payload or default
                )
                await enroll_user_in_course(db, enrollment_data)  # Pass session
        else:
            logger.warning(
                f"SYNC SAVE: No valid Moodle course data to process for user {user_id}"
            )

    except Exception as e:
        logger.error(
            f"SYNC SAVE: Failed during Moodle data processing for user {user_id}: {e}",
            exc_info=True,
        )
        raise ValueError(
            f"Failed to save Moodle data"
        ) from e  # Raise specific error to trigger rollback in router

    try:
        # --- Process SAS ---
        if (
            sas_payload
            and sas_payload.get("success")
            and isinstance(sas_payload.get("data"), dict)
        ):
            sas_data = sas_payload["data"]

            # --- Update user with major/minor/faculty info ---
            if "student_info" in sas_data:
                student_info = sas_data["student_info"]

                # Get user record
                user_result = await db.execute(select(User).where(User.id == user_id))
                user = user_result.scalar_one_or_none()

                if user:
                    # Process majors (convert list to comma-separated string)
                    if (
                        "majors" in student_info
                        and isinstance(student_info["majors"], list)
                        and student_info["majors"]
                    ):
                        user.majors = ",".join(student_info["majors"])

                    # Process minors (convert list to comma-separated string)
                    if (
                        "minors" in student_info
                        and isinstance(student_info["minors"], list)
                        and student_info["minors"]
                    ):
                        user.minors = ",".join(student_info["minors"])

                    # Set faculty
                    if "faculty" in student_info and student_info["faculty"]:
                        user.faculty = student_info["faculty"]

                    logger.info(
                        f"SYNC SAVE: Updated user {user_id} with academic program information"
                    )

                    await db.flush()  # Flush changes to database session

                    # store calendar events

                    if "calendar" in student_info and student_info["calendar"]:
                        calendar_payload = student_info["calendar"]
                        await save_course_schedule(db, user_id, calendar_payload)

                else:
                    logger.warning(
                        f"SYNC SAVE: User {user_id} not found for academic info update"
                    )

            terms_data = sas_data.get("terms", [])
            logger.info(
                f"SYNC SAVE: Processing {len(terms_data)} SAS terms/grades for user {user_id}"
            )

            for term in terms_data:
                term_code = term.get("term_code")
                if not term_code:
                    logger.warning("Skipping SAS term, missing term_code.")
                    continue

                term_create_data = TermCreate(
                    term_code=term_code,
                    user_id=user_id,
                    semester_gpa=term.get("semester_gpa"),
                    cumulative_gpa=term.get("cumulative_gpa"),
                    degree_gpa=term.get("degree_gpa"),
                    credits_earned_to_date=term.get("credits_earned_to_date"),
                )
                term_rec = await update_or_create_term(
                    db, term_create_data
                )  # Pass session

                sas_courses = term.get("courses", [])
                for g in sas_courses:
                    course_code = g.get("course_code")
                    if not course_code:
                        logger.warning(
                            f"Skipping SAS grade term {term_code}, missing course_code."
                        )
                        continue

                    sas_course_id = -abs(hash(course_code)) % (2**31)
                    course_create_data = CourseCreate(
                        id=sas_course_id,
                        fullname=g.get("course_title", course_code),
                        shortname=course_code,
                        idnumber=course_code,
                        summary="Imported from SAS",
                        summaryformat=1,
                        startdate=0,
                        enddate=0,
                        visible=True,
                        showactivitydates=False,
                        showcompletionconditions=False,
                        fullnamedisplay=g.get("course_title", course_code),
                        viewurl="",
                        coursecategory="SAS Imported",
                    )
                    course = await get_or_create_course(
                        db, course_create_data
                    )  # Pass session

                    grade_data = CourseGradeCreate(
                        user_id=user_id,
                        course_id=course.id,
                        term_id=term_rec.id,
                        course_code=course_code,
                        course_title=g.get("course_title", course_code),
                        credit_hours=float(g.get("credit_hours", 0.0)),
                        grade_earned=g.get("grade_earned"),
                        whatif_grade=g.get("whatif_grade"),
                        is_historical=True,
                        earned_date=None,
                    )
                    await create_or_update_course_grade(db, grade_data)  # Pass session
        else:
            logger.warning(
                f"SYNC SAVE: No successful SAS data found to process for user {user_id}"
            )

    except Exception as e:
        logger.error(
            f"SYNC SAVE: Failed during SAS data processing for user {user_id}: {e}",
            exc_info=True,
        )
        raise ValueError(
            f"Failed to save SAS data"
        ) from e  # Raise specific error to trigger rollback in router

    logger.info(
        f"SYNC SAVE: Finished processing initial scraped data for user {user_id}"
    )


def fetch_calendar_sas_info(credentials: SASCredentials):

    session = requests.Session()

    headers = {"User-Agent": "Mozilla/5.0"}

    # Step 1: Start at Moodle login page to trigger redirects
    moodle_login_url = "https://ban.mona.uwi.edu:9077/ssb8x/twbkwbis.P_WWWLogin"
    # initial_response = session.get(moodle_login_url, headers=headers, allow_redirects=True)
    initial_response = session.get(
        moodle_login_url, headers=headers, allow_redirects=True
    )

    if initial_response.history:
        print("Redirect history:")
        for resp in initial_response.history:
            print(f"{resp.status_code} -> {resp.url}")
        print(f"Final URL: {initial_response.url}")

    # Step 2: Let redirects take us to the UWI Identity login page
    soup = BeautifulSoup(initial_response.text, "html.parser")
    session_data_key_input = soup.find("input", {"name": "sessionDataKey"})

    if not session_data_key_input:
        return {
            "success": False,
            "message": "Failed to extract sessionDataKey. UWI SSO might have changed.",
        }

    session_data_key = session_data_key_input.get("value")

    # Step 3: Prepare login form data
    login_url = "https://ban.mona.uwi.edu:9443/commonauth"
    form_data = {
        "usernameUserInput": credentials.username,
        "username": f"{credentials.username}@carbon.super",
        "password": credentials.password,
        "sessionDataKey": session_data_key,
        # "chkRemember": "on"
    }

    headers_form = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0",
    }

    # Step 4: Submit login POST request
    login_response = session.post(
        login_url, data=form_data, headers=headers_form, allow_redirects=True
    )

    if login_response.history:
        print("Redirect history:")
        for resp in login_response.history:
            print(f"{resp.status_code} -> {resp.url}")
        print(f"Final URL: {login_response.url}")

    # Confirm we're logged in
    if "General Menu" in login_response.text or "bmenu.P_MainMnu" in login_response.url:
        print("Login successful!")
    else:
        print("Login may have failed. Check response.")

    term_submit_page = "https://ban.mona.uwi.edu:9077/ssb8x/bwskflib.P_SelDefTerm"

    term_submit_resp = session.get(term_submit_page, headers=headers)
    term_soup = BeautifulSoup(term_submit_resp.text, "html.parser")

    term_hidden_inputs = term_soup.find("input", {"name": "name_var"})
    term_hidden_value = term_hidden_inputs.get("value")

    term_select = "202420"  # hardcoded for now, but can be dynamic if needed, represents 2025/2026 semester 2

    term_payload = {
        "name_var": term_hidden_value,
        "term_in": term_select,
    }

    student_registration_page = "https://ban.mona.uwi.edu:9077/ssb8x/bwcklibs.P_StoreTerm"  # leads to this page after the post request from the term submisison page

    student_registration_resp = session.post(
        student_registration_page, data=term_payload, headers=headers_form
    )

    target_page = "https://ban.mona.uwi.edu:9077/ssb8x/bwskfshd.P_CrseSchdDetl"

    result_target_page = session.get(target_page, headers=headers)
    # print("text of target page, ", result_target_page.text)
    # print("Current URL: ", result_target_page.url)

    # 1. Status code + final URL
    print("→ Status code:", result_target_page.status_code)
    print("→ Final URL:  ", result_target_page.url)

    # 2. Redirect history
    if result_target_page.history:
        print("→ Redirect chain:")
        for resp in result_target_page.history:
            print("   ", resp.status_code, resp.url)
    else:
        print("→ No redirects")

    target_soup = BeautifulSoup(result_target_page.text, "html.parser")

    # Option A: Look for the “Total Credit Hours” text
    if "Total Credit Hours" in result_target_page.text:
        print("✅ Found ‘Total Credit Hours’ – looks like the right page")
    else:
        print("❌ ‘Total Credit Hours’ not found – wrong page or not logged in")

    # Option B: Look for the very first <caption class="captiontext">
    first_caption = target_soup.find("caption", class_="captiontext")
    if first_caption:
        print("✅ First caption:", first_caption.get_text(strip=True))
    else:
        print("❌ No <caption class='captiontext'> – schedule tables missing")

    def parse_course_schedules(soup: BeautifulSoup):
        print("Starting parse_course_schedules()")

        # 0. Gather all the tables
        all_tables = soup.find_all("table", class_="datadisplaytable")
        print(f"Total datadisplaytable tables found: {len(all_tables)}")
        for idx, tbl in enumerate(all_tables, 1):
            summary = tbl.get("summary", "<no summary>")
            caption_tag = tbl.find("caption")
            caption = (
                caption_tag.get_text(strip=True) if caption_tag else "<no caption>"
            )
            print(f" Table #{idx}: summary={summary!r}, caption={caption!r}")

        # 1. Identify the “detail” tables (everything except the Meeting Times tables)
        detail_tables = [
            tbl
            for tbl in all_tables
            if tbl.find("caption")
            and tbl.find("caption").get_text(strip=True) != "Scheduled Meeting Times"
        ]
        print(f"Filtered detail tables: {len(detail_tables)}")

        courses = {}

        for i, detail in enumerate(detail_tables, 1):
            raw_caption = detail.find("caption").get_text(strip=True)
            print(f"\n--- Detail table #{i}: caption = {raw_caption!r} ---")

            # split "Data Science Principles - COMP 3162 - B01"
            parts = [p.strip() for p in raw_caption.split(" - ")]
            if len(parts) != 3:
                print(f" WARNING: caption didn’t split into 3 parts: {parts}")
                continue
            course_title, course_code, section = parts
            print(
                f" Parsed → title={course_title!r}, code={course_code!r}, section={section!r}"
            )

            # grab Level & Campus
            def get_field(label):
                th = detail.find(
                    "th", string=lambda txt: txt and label.lower() in txt.lower()
                )
                if not th:
                    print(f"  {label!r} not found")
                    return None
                td = th.find_next_sibling(["td", "TD"])
                text = td.get_text(strip=True)
                print(f"  {label!r} → {text}")
                return text

            level = get_field("Level:")
            campus = get_field("Campus:")

            # 2. Find the very next table as the schedule table
            next_idx = all_tables.index(detail) + 1
            if next_idx >= len(all_tables):
                print("WARNING: No next table for Meeting Times")
                continue
            sched_tbl = all_tables[next_idx]
            sched_caption = sched_tbl.find("caption").get_text(strip=True)
            if sched_caption != "Scheduled Meeting Times":
                print(
                    f"WARNING: Expected 'Scheduled Meeting Times' but got {sched_caption!r}"
                )
                continue
            print("  Found corresponding schedule table")

            # 3. Map headers → indices
            headers = [
                th.get_text(strip=True) for th in sched_tbl.find("tr").find_all("th")
            ]
            print(f"  Schedule headers: {headers}")
            idx_map = {h: j for j, h in enumerate(headers)}

            # 4. Parse each row
            for ridx, row in enumerate(sched_tbl.find_all("tr")[1:], start=1):
                cols = row.find_all("td")
                raw_cols = [c.get_text(strip=True) for c in cols]
                print(f"  Row #{ridx} raw: {raw_cols}")

                def parse_time_range(time_str):
                    try:
                        start, end = [t.strip() for t in time_str.split("-")]
                        return start, end
                    except Exception:
                        return None, None

                def parse_date_range(date_range_str):
                    try:
                        start_str, end_str = [
                            d.strip() for d in date_range_str.split("-")
                        ]
                        start_date = datetime.strptime(start_str, "%b %d, %Y").date()
                        end_date = datetime.strptime(end_str, "%b %d, %Y").date()
                        return start_date, end_date
                    except Exception:
                        return None, None

                time_str = cols[idx_map["Time"]].get_text(strip=True)
                date_range_str = cols[idx_map["Date Range"]].get_text(strip=True)

                start_time, end_time = parse_time_range(time_str)
                start_date, end_date = parse_date_range(date_range_str)

                # build your entry
                entry = {
                    "instructor": cols[idx_map["Instructors"]].get_text(strip=True),
                    "level": level,
                    # this is the column “Schedule Type” (Lab/Lecture/etc)
                    "session_type": cols[idx_map["Schedule Type"]].get_text(strip=True),
                    "campus": campus,
                    "where": cols[idx_map["Where"]]
                    .get_text(strip=True)
                    .replace("Located:", "")
                    .strip(),
                    "date_range": date_range_str,
                    "start_date": start_date,
                    "end_date": end_date,
                    "time": time_str,
                    "start_time": start_time,
                    "end_time": end_time,
                }
                print(f"  Parsed entry: {entry}")

                # 5. Group into our courses dict
                courses.setdefault(course_code, {"title": course_title, "sections": {}})
                courses[course_code]["sections"].setdefault(section, [])
                courses[course_code]["sections"][section].append(entry)

        print(f"\nFinished parsing: found {len(courses)} course(s)")
        return courses

    # Now, only if those checks pass, you can call your parse_course_schedules()
    if (
        result_target_page.status_code == 200
        and not result_target_page.history
        and first_caption
    ):
        course_schedules = parse_course_schedules(target_soup)
        print(f"Parsed {len(course_schedules)} schedule entries")
    else:
        logger.debug(
            f"Failed to parse course schedules. Skipping. Status code: {result_target_page.status_code}, History: {result_target_page.history}",
            exc_info=True,
        )
        course_schedules = []
    return course_schedules


def fetch_extra_sas_info(credentials: SASCredentials):

    session = requests.Session()

    headers = {"User-Agent": "Mozilla/5.0"}

    # Step 1: Start at Moodle login page to trigger redirects
    moodle_login_url = "https://ban.mona.uwi.edu:9077/ssb8x/twbkwbis.P_WWWLogin"
    # initial_response = session.get(moodle_login_url, headers=headers, allow_redirects=True)
    initial_response = session.get(
        moodle_login_url, headers=headers, allow_redirects=True
    )

    if initial_response.history:
        print("Redirect history:")
        for resp in initial_response.history:
            print(f"{resp.status_code} -> {resp.url}")
        print(f"Final URL: {initial_response.url}")

    # Step 2: Let redirects take us to the UWI Identity login page
    soup = BeautifulSoup(initial_response.text, "html.parser")
    session_data_key_input = soup.find("input", {"name": "sessionDataKey"})

    if not session_data_key_input:
        return {
            "success": False,
            "message": "Failed to extract sessionDataKey. UWI SSO might have changed.",
        }

    session_data_key = session_data_key_input.get("value")

    # Step 3: Prepare login form data
    login_url = "https://ban.mona.uwi.edu:9443/commonauth"
    form_data = {
        "usernameUserInput": credentials.username,
        "username": f"{credentials.username}@carbon.super",
        "password": credentials.password,
        "sessionDataKey": session_data_key,
        # "chkRemember": "on"
    }

    headers_form = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0",
    }

    # Step 4: Submit login POST request
    login_response = session.post(
        login_url, data=form_data, headers=headers_form, allow_redirects=True
    )

    if login_response.history:
        print("Redirect history:")
        for resp in login_response.history:
            print(f"{resp.status_code} -> {resp.url}")
        print(f"Final URL: {login_response.url}")

    # Confirm we're logged in
    if "General Menu" in login_response.text or "bmenu.P_MainMnu" in login_response.url:
        print("Login successful!")
    else:
        print("Login may have failed. Check response.")

    term_submit_page = "https://ban.mona.uwi.edu:9077/ssb8x/bwskflib.P_SelDefTerm"

    term_submit_resp = session.get(term_submit_page, headers=headers)
    term_soup = BeautifulSoup(term_submit_resp.text, "html.parser")

    term_hidden_inputs = term_soup.find("input", {"name": "name_var"})
    term_hidden_value = term_hidden_inputs.get("value")

    term_select = "202520"  # hardcoded for now, but can be dynamic if needed, represents 2025/2026 semester 2

    term_payload = {
        "name_var": term_hidden_value,
        "term_in": term_select,
    }

    student_registration_page = "https://ban.mona.uwi.edu:9077/ssb8x/bwcklibs.P_StoreTerm"  # leads to this page after the post request from the term submisison page

    student_registration_resp = session.post(
        student_registration_page, data=term_payload, headers=headers_form
    )

    fac_maj_min_page = "https://ban.mona.uwi.edu:9077/ssb8x/UWM_CHANGE_MAJOR.P_DisplayHello"  # target page for majors and minors and faculty
    fac_maj_min_resp = session.get(fac_maj_min_page, headers=headers)

    def parse_student_info(html_content):
        soup = BeautifulSoup(html_content, "html.parser")

        info = {"Majors": [], "Minors": [], "Faculty": None}

        rows = soup.find_all("tr")

        for row in rows:
            cells = row.find_all("td")
            if len(cells) >= 4:
                header1 = cells[0].get_text(strip=True)
                data1 = (
                    cells[1].find("b").get_text(strip=True)
                    if cells[1].find("b")
                    else ""
                )
                header2 = cells[2].get_text(strip=True)
                data2 = (
                    cells[3].find("b").get_text(strip=True)
                    if cells[3].find("b")
                    else ""
                )

                if data1 and "Term" not in data1:
                    if "Major" in header1:
                        info["Majors"].append(data1)
                    if "Minor" in header1:
                        info["Minors"].append(data1)
                    if "Faculty/College" in header1:
                        info["Faculty"] = data1

                if data2 and "Term" not in data2:
                    if "Major" in header2:
                        info["Majors"].append(data2)
                    if "Minor" in header2:
                        info["Minors"].append(data2)
                    if "Faculty/College" in header2:
                        info["Faculty"] = data2

        return info

    data = parse_student_info(fac_maj_min_resp.text)

    return {
        "success": True,
        "data": data,
    }
