import re
import json
from typing import Dict, Any, List

# -------------------------------------
# 1. Define Requirement Dictionaries with Faculty Structure
# -------------------------------------

faculty_schema = {
    "faculty": "FST",
    "total_credits_faculty": 93,
    "departments": [
        {
            "department": "COMPUTING", 
            "majors": [
                {"name": "Computer Science", "code": "COMP"},
                {"name": "Information Technology", "code": "INFO"},
                {"name": "Software Engineering", "code": "SWEN"}
            ]
        },
        {
            "department": "PHYSICS", 
            "majors": [
                {"name": "Electronics", "code": "ELET"}
            ]
        }
    ],
    "level_requirements": {
        "level_1": {
            "min_credits": 24,
            "min_faculty_credits": 18,
            "notes": "At least 18 of these must be FST courses"
        },
        "level_2_and_3": {
            "min_credits": 60
        }
    },
    # Foundation requirements now use a slot‐based approach.
    # Slot 1 (alternatives: FOUN1014 or FOUN1019) is mandatory and cannot be replaced.
    # Slots 2 and 3 (FOUN1101 and FOUN1301) can be substituted with a language course.
    "foundation_requirements": {
        "total_foundation_credits": 9,  # required total credits from foundations
        "required_slots": [
            { "alternatives": ["FOUN1014", "FOUN1019"], "mandatory": True },
            { "alternatives": ["FOUN1101"], "mandatory": False },
            { "alternatives": ["FOUN1301"], "mandatory": False }
        ],
        "language_substitution": {
            "allowed_courses": ["JAPA", "SPAN","FREN", "CHIN"],
            "max_substitutions": 1
        }
    },
    "special_notes": [
        "Students may substitute one (1) foundation course (except FOUN1014/FOUN1019) with an approved foreign language course.",
        "FOUN1014/FOUN1019 are mandatory and cannot be replaced by a language."
    ]
}

major_schema_comp = {
    "major": "Computer Science",
    "faculty": "FST",
    "requirements": {
        "levels": [
            {
                "level_name": "Level 1",
                "required_credits": 15,
                "required_courses": [
                    "COMP1220",
                    "COMP1126",
                    "COMP1127",
                    "COMP1161",
                    "COMP1210"
                ],
                "notes": "Complete at least 15 credits from these introductory courses."
            },
            {
                "level_name": "Level 2 and 3",
                "required_credits": 39,
                "required_courses": [
                    "COMP2140",
                    "COMP2171",
                    "COMP2190",
                    "COMP2201",
                    "COMP2211",
                    "COMP2340",
                    "COMP3101",
                    "COMP3161",
                    "COMP3220",
                    "COMP3901"
                ],
                "notes": "Complete at least 39 credits from the advanced CS courses listed."
            }
        ]
    }
}

major_schema_swen = {
    "major": "Software Engineering",
    "faculty": "FST",
    "requirements": {
        "levels": [
            {
                "level_name": "Level 1",
                "required_credits": 15,
                "required_courses": [
                    "COMP1126",
                    "COMP1127",
                    "COMP1161",
                    "COMP1210",
                    "COMP1220"
                ],
                "notes": "Complete at least 15 credits from these introductory courses."
            },
            {
                "level_name": "Level 2 and 3",
                "required_credits": 39,
                "required_courses": [
                    "COMP2140",
                    "COMP2171",
                    "COMP2190",
                    "COMP2201",
                    "COMP2211",
                    "COMP3911",
                    "SWEN3130",
                    "SWEN3145",
                    "SWEN3165",
                    "SWEN3185",
                    "SWEN3920"
                ],
                "notes": "Complete at least 39 credits from these advanced courses, including three (3) credits from Level 2 or 3 courses offered by the Department of Computing."
            }
        ]
    }
}
# -------------------------------------
# 2. Transcript Data (as JSON string)
# -------------------------------------

transcript_json = """
{
    "success": true,
    "data": {
        "student_name": "See WHATIF GPA Calculations below forJordan Campbell",
        "student_id": "620155675",
        "terms": [
            {
                "term_code": "202420",
                "courses": [
                    {
                        "course_code": "COMP3162+",
                        "course_title": "Data Science Principles",
                        "credit_hours": 3.0,
                        "grade_earned": "NA",
                        "whatif_grade": "NA"
                    },
                    {
                        "course_code": "COMP3901+",
                        "course_title": "Group Project",
                        "credit_hours": 3.0,
                        "grade_earned": "NA",
                        "whatif_grade": "NA"
                    },
                    {
                        "course_code": "INFO3165+",
                        "course_title": "Security Analysis and Digital Forensics",
                        "credit_hours": 3.0,
                        "grade_earned": "NA",
                        "whatif_grade": "NA"
                    },
                    {
                        "course_code": "INFO3180+",
                        "course_title": "Dynamic Web Development II",
                        "credit_hours": 3.0,
                        "grade_earned": "NA",
                        "whatif_grade": "NA"
                    },
                    {
                        "course_code": "MGMT2004+",
                        "course_title": "Computer Applications",
                        "credit_hours": 3.0,
                        "grade_earned": "NA",
                        "whatif_grade": "NA"
                    }
                ],
                "semester_gpa": 0.0,
                "cumulative_gpa": 3.6593,
                "degree_gpa": 3.6133,
                "credits_earned_to_date": 96
            },
            {
                "term_code": "202410",
                "courses": [
                    {
                        "course_code": "COMP3101+",
                        "course_title": "Operating Systems",
                        "credit_hours": 3.0,
                        "grade_earned": "A-",
                        "whatif_grade": "A-"
                    },
                    {
                        "course_code": "COMP3220+",
                        "course_title": "Principles of Artificial Intelligence",
                        "credit_hours": 3.0,
                        "grade_earned": "B",
                        "whatif_grade": "B"
                    },
                    {
                        "course_code": "INFO2180+",
                        "course_title": "Dynamic Web Development 1",
                        "credit_hours": 3.0,
                        "grade_earned": "A",
                        "whatif_grade": "A"
                    },
                    {
                        "course_code": "MGMT3031+",
                        "course_title": "Business Strategy and Policy",
                        "credit_hours": 3.0,
                        "grade_earned": "B+",
                        "whatif_grade": "B+"
                    },
                    {
                        "course_code": "SPAN0101",
                        "course_title": "Beginners' Spanish (l)",
                        "credit_hours": 3.0,
                        "grade_earned": "B+",
                        "whatif_grade": "B+"
                    },
                    {
                        "course_code": "SWEN3001+",
                        "course_title": "Android Application Development I",
                        "credit_hours": 3.0,
                        "grade_earned": "C",
                        "whatif_grade": "C"
                    }
                ],
                "semester_gpa": 3.2167,
                "cumulative_gpa": 3.6593,
                "degree_gpa": 3.6133,
                "credits_earned_to_date": 81
            },
            {
                "term_code": "202320",
                "courses": [
                    {
                        "course_code": "COMP2171+",
                        "course_title": "Object Oriented Design & Implementation",
                        "credit_hours": 3.0,
                        "grade_earned": "B+",
                        "whatif_grade": "B+"
                    },
                    {
                        "course_code": "COMP2211+",
                        "course_title": "Analysis of Algorithms",
                        "credit_hours": 3.0,
                        "grade_earned": "A+",
                        "whatif_grade": "A+"
                    },
                    {
                        "course_code": "COMP2340+",
                        "course_title": "Computer Systems Organization",
                        "credit_hours": 3.0,
                        "grade_earned": "A-",
                        "whatif_grade": "A-"
                    },
                    {
                        "course_code": "COMP3161+",
                        "course_title": "Introduction to Database Management Syst",
                        "credit_hours": 3.0,
                        "grade_earned": "A",
                        "whatif_grade": "A"
                    },
                    {
                        "course_code": "FOUN1101",
                        "course_title": "Caribbean Civilization",
                        "credit_hours": 3.0,
                        "grade_earned": "A-",
                        "whatif_grade": "A-"
                    },
                    {
                        "course_code": "MGMT2008+",
                        "course_title": "Organizational Behaviour",
                        "credit_hours": 3.0,
                        "grade_earned": "A",
                        "whatif_grade": "A"
                    }
                ],
                "semester_gpa": 3.8333,
                "cumulative_gpa": 3.7857,
                "degree_gpa": 3.82,
                "credits_earned_to_date": 63
            },
            {
                "term_code": "202310",
                "courses": [
                    {
                        "course_code": "ACCT1005",
                        "course_title": "Financial Accounting",
                        "credit_hours": 3.0,
                        "grade_earned": "A",
                        "whatif_grade": "A"
                    },
                    {
                        "course_code": "COMP2140",
                        "course_title": "Software Engineering",
                        "credit_hours": 3.0,
                        "grade_earned": "B+",
                        "whatif_grade": "B+"
                    },
                    {
                        "course_code": "COMP2190+",
                        "course_title": "Net-Centric Computing",
                        "credit_hours": 3.0,
                        "grade_earned": "A",
                        "whatif_grade": "A"
                    },
                    {
                        "course_code": "COMP2201",
                        "course_title": "Discrete Mathematics for Computer Scienc",
                        "credit_hours": 3.0,
                        "grade_earned": "A+",
                        "whatif_grade": "A+"
                    },
                    {
                        "course_code": "MGMT2026+",
                        "course_title": "Production & Operations Management",
                        "credit_hours": 3.0,
                        "grade_earned": "B+",
                        "whatif_grade": "B+"
                    }
                ],
                "semester_gpa": 3.78,
                "cumulative_gpa": 3.7667,
                "degree_gpa": 3.78,
                "credits_earned_to_date": 45
            },
            {
                "term_code": "202220",
                "courses": [
                    {
                        "course_code": "COMP1161",
                        "course_title": "Introduction to Object-Oriented Programm",
                        "credit_hours": 3.0,
                        "grade_earned": "A+",
                        "whatif_grade": "A+"
                    },
                    {
                        "course_code": "COMP1220",
                        "course_title": "Computing and Society",
                        "credit_hours": 3.0,
                        "grade_earned": "B+",
                        "whatif_grade": "B+"
                    },
                    {
                        "course_code": "ELET1500",
                        "course_title": "Engineering Circuit Analysis and Devices",
                        "credit_hours": 3.0,
                        "grade_earned": "B-",
                        "whatif_grade": "B-"
                    },
                    {
                        "course_code": "FOUN1014",
                        "course_title": "Critical Reading and Writing in Science",
                        "credit_hours": 3.0,
                        "grade_earned": "B",
                        "whatif_grade": "B"
                    },
                    {
                        "course_code": "MGMT2012+",
                        "course_title": "Quantitative Methods",
                        "credit_hours": 3.0,
                        "grade_earned": "A",
                        "whatif_grade": "A"
                    }
                ],
                "semester_gpa": 3.46,
                "cumulative_gpa": 3.76,
                "degree_gpa": 4.0,
                "credits_earned_to_date": 30
            },
            {
                "term_code": "202210",
                "courses": [
                    {
                        "course_code": "COMP1126",
                        "course_title": "Introduction to Computing I",
                        "credit_hours": 3.0,
                        "grade_earned": "A+",
                        "whatif_grade": "A+"
                    },
                    {
                        "course_code": "COMP1127",
                        "course_title": "Introduction to Computing II",
                        "credit_hours": 3.0,
                        "grade_earned": "A+",
                        "whatif_grade": "A+"
                    },
                    {
                        "course_code": "COMP1210",
                        "course_title": "Mathematics for Computing",
                        "credit_hours": 3.0,
                        "grade_earned": "A-",
                        "whatif_grade": "A-"
                    },
                    {
                        "course_code": "ECON1005",
                        "course_title": "Introduction to Statistics",
                        "credit_hours": 3.0,
                        "grade_earned": "A",
                        "whatif_grade": "A"
                    },
                    {
                        "course_code": "SOCI1001",
                        "course_title": "Introduction to Social Research",
                        "credit_hours": 3.0,
                        "grade_earned": "A",
                        "whatif_grade": "A"
                    }
                ],
                "semester_gpa": 4.06,
                "cumulative_gpa": 4.06,
                "degree_gpa": null,
                "credits_earned_to_date": 15
            }
        ],
        "overall": {
            "cumulative_gpa": 3.6593,
            "degree_gpa": 3.6133,
            "total_credits_earned": 96
        }
    }
}
"""

# Convert transcript JSON string into a Python dictionary.
transcript_data = json.loads(transcript_json)

# -------------------------------------
# 3. Helper Functions
# -------------------------------------

# Define accepted final (earned) grades.
ACCEPTED_GRADES = {"A+", "A", "A-", "B+", "B", "B-", "C+", "C"}

def clean_course_code(course_code: str) -> str:
    """
    Remove trailing '+' characters and trim whitespace.
    """
    return course_code.strip().rstrip('+')

def get_course_level(course_code: str) -> int:
    """
    Use the cleaned course code to determine course level.
    """
    course_code_clean = clean_course_code(course_code)
    match = re.search(r'[A-Za-z]+(\d+)', course_code_clean)
    if match:
        digits = match.group(1)
        if digits and digits[0].isdigit():
            return int(digits[0])
    return 1

def is_faculty_course(course_code: str, faculty_schema: Dict[str, Any]) -> bool:
    """
    Check if a course belongs to the faculty based on the course code prefix.
    """
    course_code_clean = clean_course_code(course_code)
    # Extract the prefix (letters) from the course code
    prefix_match = re.match(r'^([A-Za-z]+)', course_code_clean)
    if not prefix_match:
        return False
    
    prefix = prefix_match.group(1)
    
    # Check if the course prefix matches any major code in the faculty
    for department in faculty_schema.get("departments", []):
        for major in department.get("majors", []):
            if prefix == major.get("code"):
                return True
    
    return False

def check_foundation_slots(transcript: Dict[str, Any], foundation_schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluate foundation requirements using slot-based rules.
    
    For each slot:
      - If one of the alternative foundation courses (e.g., FOUN1014/FOUN1019, FOUN1101, FOUN1301)
        is earned (final grade in ACCEPTED_GRADES), the slot is satisfied.
      - For non-mandatory slots (i.e. those other than slot 1), a language course
        (from allowed language courses) may be used as a substitution.
      - A language substitution adds its course credits to the foundation total.
      
    Returns a dictionary with:
      - all_satisfied: True if every slot was satisfied.
      - slots_status: a list of the status for each slot.
      - foundation_earned: total earned foundation credits from the satisfied slots.
    """
    required_slots: List[Dict[str, Any]] = foundation_schema.get("required_slots", [])
    language_info = foundation_schema.get("language_substitution", {})
    allowed_languages = set(language_info.get("allowed_courses", []))
    max_substitutions = language_info.get("max_substitutions", 1)
    
    # Gather earned courses from transcript (only with accepted final grades).
    earned_courses = []  # list of tuples (course_code, credits)
    for term in transcript.get("data", {}).get("terms", []):
        for course in term.get("courses", []):
            grade = course.get("grade_earned", "NA")
            if grade in ACCEPTED_GRADES:
                code = clean_course_code(course.get("course_code", ""))
                credits = course.get("credit_hours", 0.0)
                earned_courses.append((code, credits))
                
    # Separate foundation courses (starting with "FOUN") and language courses.
    earned_foundation = [(code, credits) for (code, credits) in earned_courses if code.startswith("FOUN")]
    earned_language = [(code, credits) for (code, credits) in earned_courses if any(code.startswith(lang) for lang in allowed_languages)]
    
    slots_status = []
    substitutions_used = 0
    foundation_total = 0.0
    for slot in required_slots:
        alternatives = set(slot.get("alternatives", []))
        mandatory = slot.get("mandatory", False)
        slot_status = {"alternatives": list(alternatives)}
        
        # Check if any foundation course satisfies this slot.
        matching_foundation = [ (code, credits) for (code, credits) in earned_foundation if code in alternatives ]
        if matching_foundation:
            chosen = matching_foundation[0]
            slot_status["satisfied_by"] = "foundation"
            slot_status["course"] = chosen[0]
            slot_status["credits"] = chosen[1]
            foundation_total += chosen[1]
        else:
            # For non-mandatory slots, allow language substitution.
            if not mandatory and substitutions_used < max_substitutions and earned_language:
                chosen = earned_language[0]
                earned_language.remove(chosen)  # Remove the used language course
                substitutions_used += 1
                slot_status["satisfied_by"] = "language substitution"
                slot_status["course"] = chosen[0]
                slot_status["credits"] = chosen[1]
                foundation_total += chosen[1]
            else:
                slot_status["satisfied_by"] = None
        slots_status.append(slot_status)
        
    all_satisfied = all(item["satisfied_by"] is not None for item in slots_status)
    return {
        "all_satisfied": all_satisfied,
        "slots_status": slots_status,
        "foundation_earned": foundation_total
    }

# -------------------------------------
# 4. Checking Functions for Faculty and Major Requirements
# -------------------------------------

def check_faculty_requirements(transcript: Dict[str, Any],
                               faculty_schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluate faculty-wide requirements.
    
    Earned credits are accumulated only from courses with a final accepted grade.
    Courses with a grade of "NA" are considered in–progress and tallied as potential credits.
    The foundation requirements are evaluated using the slot-based check.
    """
    total_required = faculty_schema.get("total_credits_faculty", 0)
    level1_required = faculty_schema.get("level_requirements", {}).get("level_1", {}).get("min_credits", 0)
    level1_faculty_required = faculty_schema.get("level_requirements", {}).get("level_1", {}).get("min_faculty_credits", 18)
    level23_required = faculty_schema.get("level_requirements", {}).get("level_2_and_3", {}).get("min_credits", 0)
    foundation_required = faculty_schema.get("foundation_requirements", {}).get("total_foundation_credits", 9)
    
    total_earned = 0.0
    level1_earned = 0.0
    level1_faculty_earned = 0.0
    level23_earned = 0.0
    
    total_potential = 0.0
    level1_potential = 0.0
    level1_faculty_potential = 0.0
    level23_potential = 0.0
    
    # List to track level 1 FST courses for reporting
    level1_faculty_courses = []
    
    for term in transcript.get("data", {}).get("terms", []):
        for course in term.get("courses", []):
            credits = course.get("credit_hours", 0.0)
            course_code = clean_course_code(course.get("course_code", ""))
            level = get_course_level(course_code)
            grade = course.get("grade_earned", "NA")
            is_faculty = is_faculty_course(course_code, faculty_schema)
            
            if grade in ACCEPTED_GRADES:
                total_earned += credits
                if level == 1:
                    level1_earned += credits
                    if is_faculty:
                        level1_faculty_earned += credits
                        level1_faculty_courses.append((course_code, credits))
                elif level in [2, 3]:
                    level23_earned += credits
            elif grade == "NA":
                total_potential += credits
                if level == 1:
                    level1_potential += credits
                    if is_faculty:
                        level1_faculty_potential += credits
                elif level in [2, 3]:
                    level23_potential += credits
    
    missing = {}
    if total_earned < total_required:
        missing["total_credits"] = total_required - total_earned
    if level1_earned < level1_required:
        missing["level_1_credits"] = level1_required - level1_earned
    if level1_faculty_earned < level1_faculty_required:
        missing["level_1_faculty_credits"] = level1_faculty_required - level1_faculty_earned
    if level23_earned < level23_required:
        missing["level_2_and_3_credits"] = level23_required - level23_earned
    
    foundation_status = check_foundation_slots(transcript, faculty_schema.get("foundation_requirements", {}))
    # Check both slot satisfaction and whether the sum of credits is enough.
    if not foundation_status["all_satisfied"] or foundation_status["foundation_earned"] < foundation_required:
        missing["foundation_credits"] = foundation_required - foundation_status["foundation_earned"]
    
    return {
        "faculty": faculty_schema.get("faculty", ""),
        "passes_faculty": len(missing) == 0,
        "credits_earned": {
            "total": total_earned,
            "level_1": level1_earned,
            "level_1_faculty": level1_faculty_earned,
            "level_2_and_3": level23_earned
        },
        "potential_credits": {
            "total": total_potential,
            "level_1": level1_potential,
            "level_1_faculty": level1_faculty_potential,
            "level_2_and_3": level23_potential
        },
        "foundation_status": foundation_status,
        "missing_requirements": missing,
        "level1_faculty_courses": level1_faculty_courses
    }

def check_major_requirements_with_levels(transcript: Dict[str, Any],
                                         major_schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluate a major's requirements organized in level-based blocks.
    
    Only courses with a final accepted grade count as earned.
    Courses with a grade of "NA" are tallied as potential but do not count as completed for course requirements.
    """
    results = []
    all_blocks_passed = True
    
    level_blocks = major_schema.get("requirements", {}).get("levels", [])
    
    courses_by_level = {}
    for term in transcript.get("data", {}).get("terms", []):
        for course in term.get("courses", []):
            grade = course.get("grade_earned", "NA")
            credits = course.get("credit_hours", 0.0)
            code = clean_course_code(course.get("course_code", ""))
            level = get_course_level(code)
            courses_by_level.setdefault(level, []).append((code, credits, grade))
    
    for block in level_blocks:
        block_name = block.get("level_name", "Unknown Level")
        block_required_credits = block.get("required_credits", 0)
        block_required_courses = set(block.get("required_courses", []))
        
        if "1" in block_name:
            relevant_levels = [1]
        elif "2 and 3" in block_name:
            relevant_levels = [2, 3]
        else:
            relevant_levels = [2, 3]
        
        total_earned = 0.0
        total_potential = 0.0
        completed_required_courses = set()
        
        for lvl in relevant_levels:
            for (course_code, credits, grade) in courses_by_level.get(lvl, []):
                if grade in ACCEPTED_GRADES:
                    total_earned += credits
                    if course_code in block_required_courses:
                        completed_required_courses.add(course_code)
                elif grade == "NA":
                    total_potential += credits
        
        block_missing = {}
        if total_earned < block_required_credits:
            block_missing["credits"] = block_required_credits - total_earned
        missing_courses = block_required_courses - completed_required_courses
        if missing_courses:
            block_missing["required_courses"] = list(missing_courses)
        
        block_passes = len(block_missing) == 0
        if not block_passes:
            all_blocks_passed = False
        
        results.append({
            "block_name": block_name,
            "required_credits": block_required_credits,
            "total_earned_credits": total_earned,
            "potential_credits": total_potential,
            "completed_required_courses": list(completed_required_courses),
            "missing": block_missing,
            "passes": block_passes
        })
    
    summary = {
        "major": major_schema.get("major", ""),
        "blocks": results,
        "passes_major": all_blocks_passed
    }
    
    return summary

def check_all_requirements(transcript: Dict[str, Any],
                           faculty_schema: Dict[str, Any],
                           major_schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Combine the faculty and level-based major checks.
    
    Graduation eligibility is based solely on earned (completed) courses.
    In-progress (potential) credits are reported separately.
    """
    faculty_result = check_faculty_requirements(transcript, faculty_schema)
    major_result = check_major_requirements_with_levels(transcript, major_schema)
    passes_all = faculty_result["passes_faculty"] and major_result["passes_major"]
    return {
        "passes_all_requirements": passes_all,
        "faculty_result": faculty_result,
        "major_result": major_result
    }



def check_potential_graduation(result: Dict[str, Any], transcript: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluate if the student would meet graduation requirements if they pass all in-progress courses.
    
    This combines earned credits and potential credits from in-progress courses with grade "NA".
    """
    faculty_result = result["faculty_result"]
    major_result = result["major_result"]
    
    # Check if adding potential credits would fulfill faculty requirements
    potential_faculty_passes = True
    potential_faculty_missing = {}
    
    # Copy the credits earned dictionary and add potential credits
    potential_credits = {
        "total": faculty_result["credits_earned"]["total"] + faculty_result["potential_credits"]["total"],
        "level_1": faculty_result["credits_earned"]["level_1"] + faculty_result["potential_credits"]["level_1"],
        "level_1_faculty": faculty_result["credits_earned"]["level_1_faculty"] + faculty_result["potential_credits"]["level_1_faculty"],
        "level_2_and_3": faculty_result["credits_earned"]["level_2_and_3"] + faculty_result["potential_credits"]["level_2_and_3"]
    }
    
    # Check against faculty requirements
    faculty_schema = {
        "total_credits_faculty": 93,
        "level_requirements": {
            "level_1": {
                "min_credits": 24,
                "min_faculty_credits": 18
            },
            "level_2_and_3": {
                "min_credits": 60
            }
        },
        "foundation_requirements": {
            "total_foundation_credits": 9
        }
    }
    
    if potential_credits["total"] < faculty_schema["total_credits_faculty"]:
        potential_faculty_passes = False
        potential_faculty_missing["total_credits"] = faculty_schema["total_credits_faculty"] - potential_credits["total"]
    
    if potential_credits["level_1"] < faculty_schema["level_requirements"]["level_1"]["min_credits"]:
        potential_faculty_passes = False
        potential_faculty_missing["level_1_credits"] = faculty_schema["level_requirements"]["level_1"]["min_credits"] - potential_credits["level_1"]
    
    if potential_credits["level_1_faculty"] < faculty_schema["level_requirements"]["level_1"]["min_faculty_credits"]:
        potential_faculty_passes = False
        potential_faculty_missing["level_1_faculty_credits"] = faculty_schema["level_requirements"]["level_1"]["min_faculty_credits"] - potential_credits["level_1_faculty"]
    
    if potential_credits["level_2_and_3"] < faculty_schema["level_requirements"]["level_2_and_3"]["min_credits"]:
        potential_faculty_passes = False
        potential_faculty_missing["level_2_and_3_credits"] = faculty_schema["level_requirements"]["level_2_and_3"]["min_credits"] - potential_credits["level_2_and_3"]
    
    # Check if foundation requirements would be met
    foundation_status = faculty_result["foundation_status"]
    if not foundation_status["all_satisfied"] or foundation_status["foundation_earned"] < faculty_schema["foundation_requirements"]["total_foundation_credits"]:
        potential_faculty_passes = False
        potential_faculty_missing["foundation_credits"] = faculty_schema["foundation_requirements"]["total_foundation_credits"] - foundation_status["foundation_earned"]
    
    # Check potential major requirements status
    potential_major_passes = True
    potential_major_missing = []
    
    # Get all in-progress courses
    in_progress_courses = []
    for term in transcript.get("data", {}).get("terms", []):
        for course in term.get("courses", []):
            if course.get("grade_earned") == "NA":
                in_progress_courses.append(clean_course_code(course.get("course_code", "")))
    
    for block in major_result["blocks"]:
        block_potential = {
            "block_name": block["block_name"],
            "passes": True,
            "missing": {}
        }
        
        potential_block_credits = block["total_earned_credits"] + block["potential_credits"]
        
        # Check if potential credits meet requirement
        if potential_block_credits < block["required_credits"]:
            block_potential["passes"] = False
            block_potential["missing"]["credits"] = block["required_credits"] - potential_block_credits
            potential_major_passes = False
        
        # Check for required courses that might be in progress
        if "missing" in block and "required_courses" in block["missing"]:
            still_missing_courses = []
            
            # Find required courses that will remain missing even after completing in-progress courses
            for course_code in block["missing"]["required_courses"]:
                if course_code not in in_progress_courses:
                    still_missing_courses.append(course_code)
            
            if still_missing_courses:
                block_potential["missing"]["required_courses"] = still_missing_courses
                potential_major_passes = False
        
        if not block_potential["passes"]:
            potential_major_missing.append(block_potential)
    
    # Combine results
    potential_graduation_status = {
        "potential_graduate": potential_faculty_passes and potential_major_passes,
        "potential_faculty_passes": potential_faculty_passes,
        "potential_faculty_missing": potential_faculty_missing,
        "potential_major_passes": potential_major_passes,
        "potential_major_missing": potential_major_missing,
        "potential_credits": potential_credits,
        "in_progress_courses": in_progress_courses
    }
    
    return potential_graduation_status

# Then, update the call to this function in the main code:
result = check_all_requirements(transcript_data, faculty_schema, major_schema_comp)
potential_graduation = check_potential_graduation(result, transcript_data)

# -------------------------------------
# 5. Run the System and Report the Output
# -------------------------------------

result = check_all_requirements(transcript_data, faculty_schema, major_schema_comp)
potential_graduation = check_potential_graduation(result, transcript_data)

if result["passes_all_requirements"]:
    print("Congratulations! You meet all graduation requirements.")
else:
    print("Some requirements are still missing:")

    if not result["faculty_result"]["passes_faculty"]:
        print("\nFaculty-level requirements missing:")
        for key, value in result["faculty_result"]["missing_requirements"].items():
            print(f"  - {key}: {value}")
        
        print("\nLevel 1 faculty courses (18 credits required):")
        faculty_courses = result["faculty_result"]["level1_faculty_courses"]
        if faculty_courses:
            total_faculty_credits = sum(credits for _, credits in faculty_courses)
            print(f"  Earned {total_faculty_credits} faculty credits out of 18 required")
            for code, credits in faculty_courses:
                print(f"  - {code}: {credits} credits")
        else:
            print("  No Level 1 faculty courses completed yet")
        
        print("\nEarned vs Potential Faculty Credits:")
        for cat, earned in result["faculty_result"]["credits_earned"].items():
            potential = result["faculty_result"]["potential_credits"].get(cat, 0.0)
            print(f"  {cat.replace('_', ' ').capitalize()}: Earned = {earned}, Potential = {potential}")
        
        print("\nFoundation Status:")
        for slot in result["faculty_result"]["foundation_status"]["slots_status"]:
            if slot.get("satisfied_by"):
                print(f"  - Slot {slot['alternatives']} satisfied by {slot['satisfied_by']} (Course: {slot.get('course')}, Credits: {slot.get('credits')})")
            else:
                print(f"  - Slot {slot['alternatives']} is NOT satisfied.")
            
    if not result["major_result"]["passes_major"]:
        for block in result["major_result"]["blocks"]:
            if not block["passes"]:
                print(f"\n{block['block_name']} Requirements Missing:")
                for m_key, m_val in block["missing"].items():
                    if m_key == "credits":
                        print(f"  - Additional {m_val} credit(s) needed in {block['block_name']}.")
                    elif m_key == "required_courses":
                        print(f"  - Missing required courses: {', '.join(m_val)}")
                print(f"  Earned Credits = {block['total_earned_credits']}, Potential Credits = {block['potential_credits']}")

print("\nDetailed Faculty Credit Summary:")
for cat, credits in result["faculty_result"]["credits_earned"].items():
    potential = result["faculty_result"]["potential_credits"].get(cat, 0.0)
    print(f"  {cat.replace('_', ' ').capitalize()}: {credits} earned, {potential} potential")

print("\nMajor Credits Earned (by Level Block):")
for block in result["major_result"]["blocks"]:
    print(f"  {block['block_name']}: {block['total_earned_credits']} earned, {block['potential_credits']} potential")

print(f"\nOverall Major Pass Status: {result['major_result']['passes_major']}")
print(f"Overall Graduation Eligibility (Earned Requirements Only): {result['passes_all_requirements']}")

# Print faculty courses detected
print("\nFaculty Courses Detected:")
fst_courses = []
for term in transcript_data.get("data", {}).get("terms", []):
    for course in term.get("courses", []):
        code = clean_course_code(course.get("course_code", ""))
        credits = course.get("credit_hours", 0.0)
        if is_faculty_course(code, faculty_schema):
            grade = course.get("grade_earned", "NA")
            fst_courses.append(f"{code} ({credits} credits, grade: {grade})")

if fst_courses:
    print("  " + "\n  ".join(fst_courses))
else:
    print("  No faculty courses detected")

# Print potential graduation status
print("\n" + "="*50)
print("POTENTIAL GRADUATION STATUS")
print("="*50)
print("If all in-progress courses are completed with passing grades:")

if potential_graduation["potential_graduate"]:
    print("\n✅ ELIGIBLE TO GRADUATE upon successful completion of current courses")
else:
    print("\n❌ NOT ELIGIBLE TO GRADUATE even after completing current courses")
    
    if not potential_graduation["potential_faculty_passes"]:
        print("\nFaculty requirements that would still be missing:")
        for key, value in potential_graduation["potential_faculty_missing"].items():
            print(f"  - {key}: {value}")
    
    if not potential_graduation["potential_major_passes"]:
        print("\nMajor requirements that would still be missing:")
        for block in potential_graduation["potential_major_missing"]:
            print(f"  {block['block_name']}:")
            for m_key, m_val in block["missing"].items():
                if m_key == "credits":
                    print(f"    - Additional {m_val} credit(s) needed")
                elif m_key == "required_courses":
                    print(f"    - Still missing required courses: {', '.join(m_val)}")

print("\nPotential credit totals after completing current courses:")
for cat, credits in potential_graduation["potential_credits"].items():
    print(f"  {cat.replace('_', ' ').capitalize()}: {credits}")

print("\nAdditional courses needed for graduation eligibility:")
if potential_graduation["potential_graduate"]:
    print("  None - student will be eligible to graduate upon completion of current courses")
else:
    # Calculate what's still needed
    total_additional_credits = potential_graduation["potential_faculty_missing"].get("total_credits", 0)
    level_2_3_additional = potential_graduation["potential_faculty_missing"].get("level_2_and_3_credits", 0)
    
    print(f"  Total additional credits needed: {total_additional_credits}")
    if level_2_3_additional > 0:
        print(f"  Additional Level 2/3 credits needed: {level_2_3_additional}")
    
    missing_courses = []
    for block in potential_graduation["potential_major_missing"]:
        if "required_courses" in block["missing"]:
            for course in block["missing"]["required_courses"]:
                missing_courses.append(course)
    
    if missing_courses:
        print(f"  Required courses still needed: {', '.join(missing_courses)}")