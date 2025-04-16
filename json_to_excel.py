import os
import json
import pandas as pd


# extracts course information from json files and saves it to an excel file
# it only works with text files in the current directory
def extract_course_info(course: dict) -> dict:
    meetings = course.get("meetingsFaculty", [])
    meeting_info = meetings[0].get("meetingTime", {}) if meetings else {}

    return {
        "id": course.get("id"),
        "courseName": course.get("courseTitle"),
        "courseCode": course.get("subjectCourse"),
        "courseReferenceNumber": course.get("courseReferenceNumber"),
        "term": course.get("term"),
        "termDescription": course.get("termDesc"),
        "subjectDescription": course.get("subjectDescription"),
        "creditHours": course.get("creditHours"),
        "scheduleTypeDescription": course.get("scheduleTypeDescription"),
        "sequenceNumber": course.get("sequenceNumber"),
        "maximumEnrollment": course.get("maximumEnrollment"),
        "instructor": (
            course.get("faculty", [{}])[0].get("displayName")
            if course.get("faculty")
            else None
        ),
    }


# Collect all course data from .txt files
all_courses = []
for filename in os.listdir("."):
    if filename.endswith(".txt"):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                content = json.load(f)
                courses = content.get("data", [])
                all_courses.extend([extract_course_info(course) for course in courses])
        except Exception as e:
            print(f"⚠️ Error reading {filename}: {e}")

# Convert to DataFrame and save to Excel
df = pd.DataFrame(all_courses)
df.to_excel("combined_courses.xlsx", index=False)
print("✅ Combined Excel file 'combined_courses.xlsx' has been created.")
