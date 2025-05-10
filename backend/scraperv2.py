import json
import requests
from bs4 import BeautifulSoup
import re
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─────── CONFIG ───────
INPUT_FILE   = "course_data.json"          # Path to your input file
OUTPUT_FILE  = "course_prereqs.json"       # Path where results will be saved
STATE_FILE   = "scrape_state.json"         # Stores resume index
PREREQ_URL   = "https://ban.mona.uwi.edu:9071/StudentRegistrationSsb/ssb/courseSearchResults/getPrerequisites"
COOKIE       = "JSESSIONID=1E1D8FECA59672FBDCDD7C606A328C5F; SRVNAME=sas5|aB5Qq|aB5MY"
HEADERS = {
    "User-Agent":   "uwi-prereq-bot/1.0",
    "Content-Type": "application/x-www-form-urlencoded",
    "Cookie":       COOKIE
}
WORKERS      = 5     # Number of concurrent threads
TEST_COUNT   = None  # e.g., 5 or None to process all
MAX_RETRIES  = 3
RETRY_DELAY  = 5     # seconds base delay


def fetch_prereqs(subject, course_number, term="202510"):
    payload = {"term": term, "subjectCode": subject, "courseNumber": course_number, "first": "first"}
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(PREREQ_URL, headers=HEADERS, data=payload, timeout=10)
        except requests.exceptions.RequestException as e:
            last_error = str(e)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
                continue
            break
        if resp.status_code == 500:
            return [], "test score required"
        try:
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            last_error = str(e)
            break
        soup = BeautifulSoup(resp.text, "html.parser")
        if soup.find(string=lambda t: t and "No prerequisite information available" in t):
            return [], None
        table = soup.find("table", class_="basePreqTable")
        prereqs = []
        if table:
            for tr in table.select("tbody tr"):
                cols = [td.get_text(strip=True) for td in tr.find_all("td")]
                prereqs.append({
                    "and_or": cols[0] or None,
                    "subject": cols[4],
                    "number": cols[5],
                    "level": cols[6],
                    "grade": cols[7]
                })
        return prereqs, None
    return [], last_error or "Unknown error"


def fetch_course(idx, course):
    sub = course.get("subjectCode")
    num = course.get("courseNumber")
    prereqs, error = fetch_prereqs(sub, num)
    record = dict(course)
    record["prerequisites"] = prereqs
    if error:
        record["prereqError"] = error
    return idx, record


def main():
    with open(INPUT_FILE) as f:
        courses = json.load(f)
    total = len(courses) if TEST_COUNT is None else min(TEST_COUNT, len(courses))

    # resume state
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as sf:
            state = json.load(sf)
        start = state.get("next_index", 0)
        outfile = open(OUTPUT_FILE, "a", encoding="utf-8")
    else:
        start = 0
        outfile = open(OUTPUT_FILE, "w", encoding="utf-8")
        outfile.write('[\n')
    end = total
    first = (start == 0)

    # prepare tasks
    to_process = courses[start:end]
    results_buf = {}
    next_to_write = start

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(fetch_course, i+start, to_process[i]): i+start for i in range(len(to_process))}
        for future in as_completed(futures):
            idx, record = future.result()
            results_buf[idx] = record
            print(f"Completed {record.get('subjectCode')} {record.get('courseNumber')}")
            # write any ready records in order
            while next_to_write in results_buf:
                rec = results_buf.pop(next_to_write)
                block = json.dumps(rec, indent=2, ensure_ascii=False)
                if not first:
                    outfile.write(',\n')
                outfile.write(block)
                outfile.flush()
                first = False
                next_to_write += 1
                # update state
                with open(STATE_FILE, "w", encoding="utf-8") as sf:
                    json.dump({"next_index": next_to_write}, sf)

    # finish file
    outfile.write('\n]\n')
    outfile.close()
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
    print(f"Done — processed up to {next_to_write} of {total} courses.")

if __name__ == "__main__":
    main()
