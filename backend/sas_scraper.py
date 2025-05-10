#!/usr/bin/env python3
"""
Script to log into UWI SSO, print auth tokens (cookies and hidden inputs),
then call the Student Registration course search API and display the JSON response.
Explicitly attaches cookies and all browser headers to mimic the request pictured.
Credentials are set directly in this script.
"""
import requests
from bs4 import BeautifulSoup
import json
from requests.exceptions import RequestException, ConnectTimeout, HTTPError

# === USER CREDENTIALS ===
USERNAME = "620150765"    # replace with your UWI username (without domain)
PASSWORD = "d%Zj%2cq"    # replace with your UWI password
# ========================

# === API PARAMETERS ===
TERM = "202510"
SESSION_ID = "ok2k61746408595347"  # replace if needed or obtain dynamically
PAGE_OFFSET = 0
PAGE_MAX_SIZE = 10
SORT_COLUMN = "subjectDescription"
SORT_DIRECTION = "asc"
# ======================

# Configure default timeout (in seconds)
DEFAULT_TIMEOUT = 15
# Disable SSL verification if necessary (set to False to skip)
VERIFY_SSL = True

# Base Referer for API calls
REFERER_PLAN = "https://ban.mona.uwi.edu:9071/StudentRegistrationSsb/ssb/plan/plan"

# Browser-like base headers (static)
BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.0.0 Safari/537.36"
    ),
}


def fetch_tokens_and_call_api(username: str, password: str):
    session = requests.Session()

    # === 1. Initial GET to login page ===
    try:
        login_url = "https://ban.mona.uwi.edu:9077/ssb8x/twbkwbis.P_WWWLogin"
        resp = session.get(
            login_url,
            headers=BASE_HEADERS,
            allow_redirects=True,
            timeout=DEFAULT_TIMEOUT,
            verify=VERIFY_SSL
        )
        resp.raise_for_status()
    except (ConnectTimeout, RequestException) as e:
        print(f"Error connecting to login page: {e}")
        return

    # Print cookies set by login page
    print("=== Initial GET Cookies ===")
    for k, v in session.cookies.get_dict().items():
        print(f"{k} = {v}")

    # Extract hidden inputs for login
    soup = BeautifulSoup(resp.text, "html.parser")
    hidden_login = {inp.get('name'): inp.get('value') for inp in soup.find_all('input', type='hidden')}
    print("\n=== Hidden login inputs ===")
    for name, val in hidden_login.items():
        print(f"{name} = {val}")
    session_data_key = hidden_login.get('sessionDataKey')

    # === 2. POST credentials ===
    try:
        auth_url = "https://ban.mona.uwi.edu:9443/commonauth"
        payload = {
            'usernameUserInput': username,
            'username': f"{username}@carbon.super",
            'password': password,
            'sessionDataKey': session_data_key or ''
        }
        headers_post = {**BASE_HEADERS, 'Content-Type': 'application/x-www-form-urlencoded'}
        login_resp = session.post(
            auth_url,
            data=payload,
            headers=headers_post,
            allow_redirects=True,
            timeout=DEFAULT_TIMEOUT,
            verify=VERIFY_SSL
        )
        login_resp.raise_for_status()
    except (ConnectTimeout, RequestException) as e:
        print(f"Error during login POST: {e}")
        return

    # Print cookies after login
    print("\n=== After login POST Cookies ===")
    for k, v in session.cookies.get_dict().items():
        print(f"{k} = {v}")

    # === 3. Visit plan page to get extra cookies & sync token ===
    try:
        plan_resp = session.get(
            REFERER_PLAN,
            headers=BASE_HEADERS,
            timeout=DEFAULT_TIMEOUT,
            verify=VERIFY_SSL
        )
        plan_resp.raise_for_status()
    except Exception as e:
        print(f"Warning: Could not load plan page for sync token: {e}")
        plan_resp = None

    # Print additional cookies
    print("\n=== Cookies after visiting plan page ===")
    for k, v in session.cookies.get_dict().items():
        print(f"{k} = {v}")

    # Extract X-Synchronizer-Token if present
    sync_token = None
    if plan_resp:
        soup2 = BeautifulSoup(plan_resp.text, 'html.parser')
        sync_inp = soup2.find('input', {'name': 'x-synchronizer-token'})
        if sync_inp and sync_inp.get('value'):
            sync_token = sync_inp['value']
            print(f"Found X-Synchronizer-Token: {sync_token}")

    # Build final cookie header string
    cookie_header = "; ".join(f"{k}={v}" for k, v in session.cookies.get_dict().items())

    # === 4. Call courseSearchResults API ===
    api_url = (
        "https://ban.mona.uwi.edu:9071/StudentRegistrationSsb/ssb/courseSearchResults/courseSearchResults"
        f"?txt_term={TERM}&startDatepicker=&endDatepicker="
        f"&uniqueSessionId={SESSION_ID}"
        f"&pageOffset={PAGE_OFFSET}&pageMaxSize={PAGE_MAX_SIZE}"
        f"&sortColumn={SORT_COLUMN}&sortDirection={SORT_DIRECTION}"
    )
    api_headers = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Accept-Language': 'en-US,en;q=0.9',
        'Connection': 'keep-alive',
        'Host': 'ban.mona.uwi.edu:9071',
        'Referer': REFERER_PLAN,
        'Sec-Ch-Ua': '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'User-Agent': BASE_HEADERS['User-Agent'],
        'X-Requested-With': 'XMLHttpRequest',
        'Cookie': cookie_header
    }
    if sync_token:
        api_headers['X-Synchronizer-Token'] = sync_token

    print("\n=== Calling courseSearchResults API ===")
    print(f"Request URL: {api_url}")
    print('--- Request Headers ---')
    for k, v in api_headers.items():
        print(f"{k}: {v}")

    try:
        api_resp = session.get(
            api_url,
            headers=api_headers,
            timeout=DEFAULT_TIMEOUT,
            verify=VERIFY_SSL
        )
        api_resp.raise_for_status()
    except (ConnectTimeout, RequestException, HTTPError) as e:
        print(f"Error calling courseSearchResults API: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response text: {e.response.text}")
        return

    print(f"Status Code: {api_resp.status_code}\n")
    try:
        print(json.dumps(api_resp.json(), indent=2))
    except ValueError:
        print('Failed to parse JSON, raw response:')
        print(api_resp.text)


if __name__ == '__main__':
    fetch_tokens_and_call_api(USERNAME, PASSWORD)
