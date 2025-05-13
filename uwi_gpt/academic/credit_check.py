import re
import json
import copy # Needed for deep copies
from typing import Dict, Any, List, Optional

# -------------------------------------
# 1. Define Constants
# -------------------------------------

# Define accepted grades
ACCEPTED_GRADES = {"A+", "A", "A-", "B+", "B", "B-", "C+", "C"}

# Define the accepted language courses
ACCEPTED_LANGUAGE_COURSES = [
    "CHIN1001",  # Chinese (Mandarin) 1A
    "FREN0101",  # Beginners' French
    "JAPA1001",  # Japanese Language 1
    "LING1819",  # Beginners' Caribbean Sign Language
    "SPAN0101"   # Beginners' Spanish
]

# -------------------------------------
# 2. Helper Functions
# -------------------------------------

def clean_course_code(course_code: str) -> str:
    """Clean course code by removing trailing '+' and whitespace."""
    return course_code.strip().rstrip('+')

def get_course_level(course_code: str) -> int:
    """Extract the level (1, 2, 3) from a course code."""
    course_code_clean = clean_course_code(course_code)
    match = re.search(r'[A-Za-z]+(\d)\d*', course_code_clean)
    if match:
        first_digit = match.group(1)
        if first_digit.isdigit() and first_digit != '0':
            return int(first_digit)
    return 1 # Default to level 1 if pattern doesn't match typical codes

def get_course_prefix(course_code: str) -> Optional[str]:
    """Extract the subject prefix (e.g., 'COMP') from a course code."""
    course_code_clean = clean_course_code(course_code)
    prefix_match = re.match(r'^([A-Za-z]+)', course_code_clean)
    if prefix_match:
        return prefix_match.group(1)
    return None

def is_faculty_course(course_code: str, faculty_schema: Dict[str, Any]) -> bool:
    """Check if a course belongs to the faculty based on its prefix."""
    prefix = get_course_prefix(course_code)
    if not prefix:
        return False

    for dept in faculty_schema.get("departments", []):
        for major in dept.get("majors", []):
            if prefix == major.get("code"):
                return True
    return False

def is_excluded_course(course_code: str, faculty_schema: Dict[str, Any]) -> bool:
    """Check if a course is in the faculty's foundation excluded courses list."""
    excluded_courses = set(faculty_schema.get("foundation_requirements", {}).get("excluded_courses", []))
    return clean_course_code(course_code) in excluded_courses

# -------------------------------------
# 3. Refactored Faculty Schema Definition
# -------------------------------------

# 3a. Define Base Faculty Schema Structure
BASE_FACULTY_SCHEMA = {
    "faculty": None,  # e.g., "FST", "FSS", "HE"
    "faculty_name": None, # e.g., "Faculty of Science and Technology"
    "credit_requirements": {
        "total_credits": 0,
        "level_1": {
            "min_credits": 0,
            "min_faculty_credits": None, # Optional, use None if not applicable
            "notes": ""
        },
        "level_2_and_3": {
            "min_credits": 0,
            # HE has specific level_2/level_3 breakdowns, handle in specifics
            "notes": ""
        }
    },
    "departments": [], # List will be replaced entirely by specifics
    "foundation_requirements": {
        "total_foundation_credits": 9, # Common default
        "required_slots": [], # List will be replaced entirely
        "substitution_rules": { # Default is no substitution
             "allowed": False,
             "allowed_courses": [],
             "max_substitutions": 0,
             "excluded_slots": []
             # Optional notes key can be added in specifics if needed
        },
        "excluded_courses": [], # List will be replaced entirely
        "notes": ""
    },
    "special_requirements": {
        "research_course": { # Default is not required
            "required": False,
            "allowed_courses": []
        },
        "language_requirement": { # Default is not required
            "required": False,
            "allowed_courses": [],
            "level_restriction": None,
            "exemption_rules": None,
            "notes": ""
        },
        "out_of_major": { # Default is not required
            "required": False,
            "min_credits": 0,
            "notes": ""
        }
    },
    "notes": [] # List will be replaced entirely by specifics
}

# 3b. Helper Function for Deep Update
def deep_update(base: Dict, update: Dict) -> Dict:
    """
    Recursively update a dictionary.

    Modifies 'base' dictionary in place with values from 'update'.
    Handles nested dictionaries. Lists and other types from 'update'
    will completely replace the corresponding values in 'base'.
    """
    for key, value in update.items():
        if isinstance(value, dict) and key in base and isinstance(base[key], dict):
            # If it's a dictionary and exists in base as a dictionary, recurse
            deep_update(base[key], value)
        else:
            # Otherwise, overwrite or add the key/value from the update dict
            base[key] = value
    return base # Return the modified base dictionary

# 3c. Define Faculty Specific Overrides

# --- FST Specifics ---
fst_specifics = {
    "faculty": "FST",
    "faculty_name": "Faculty of Science and Technology",
    "credit_requirements": {
        "total_credits": 93,
        "level_1": {"min_credits": 24, "min_faculty_credits": 18, "notes": "Eighteen (18) must be from FST courses"},
        "level_2_and_3": {"min_credits": 60, "notes": "All courses relating to the declared major(s) and or minor(s) must be completed"}
    },
    "departments": [
        {"department": "COMPUTING", "majors": [{"name": "Computer Science", "code": "COMP"}, {"name": "Information Technology", "code": "INFO"}, {"name": "Software Engineering", "code": "SWEN"}]},
        {"department": "PHYSICS", "majors": [{"name": "Electronics", "code": "ELET"}]},
        {"department": "MATHEMATICS", "majors": [{"name": "Mathematics", "code": "MATH"}, {"name": "Statistics", "code": "STAT"}]},
    ],
    "foundation_requirements": {
         "required_slots": [
             {"category": "English Language/Writing", "alternatives": ["FOUN1014", "FOUN1019"], "mandatory": True, "notes": "FOUN1014: Critical Reading and Writing in Science and Technology & Medical Science OR FOUN1019: Critical Reading and Writing in the Disciplines"},
             {"category": "Caribbean Civilization", "alternatives": ["FOUN1101"], "mandatory": False, "notes": "FOUN1101: Caribbean Civilization"},
             {"category": "Law and Society", "alternatives": ["FOUN1301"], "mandatory": False, "notes": "FOUN1301: Law, Governance, Economy and Society"}
         ],
         "substitution_rules": {
             "allowed": True,
             "allowed_courses": ACCEPTED_LANGUAGE_COURSES,
             "max_substitutions": 1,
             "excluded_slots": [0] # First slot (English) cannot be substituted
         },
         "excluded_courses": ["FOUN1201"],
         "notes": "Students registered in FST should NOT register for FOUN1201: Science, Medicine and Technology in Society."
    },
    # special_requirements -> language_requirement -> required=False (from BASE) is correct
    "notes": [
        "Minimum 93 credits required for BSc degree.",
        "Students may substitute one Foundation course (except for English Language/Writing courses) with a foreign language course. Accepted language courses include: CHIN1001, FREN0101, JAPA1001, LING1819, and SPAN0101.",
        "Exemptions for language courses may be granted from time to time by the Board for Undergraduate Studies."
    ]
}

# --- FSS Specifics ---
fss_specifics = {
    "faculty": "FSS",
    "faculty_name": "Faculty of Social Sciences",
    "credit_requirements": {
        "total_credits": 90,
        "level_1": {"min_credits": 30, "notes": "Level 1 credits include Foundation and Foreign Language requirements."}, # min_faculty_credits remains None
        "level_2_and_3": {"min_credits": 60} # notes remains ""
    },
    "departments": [
        {"department": "SOCIAL SCIENCES", "majors": [
            {"name": "Management Studies", "code": "MGMT"}, {"name": "Economics", "code": "ECON"},
            {"name": "Sociology", "code": "SOCI"}, {"name": "Psychology", "code": "PSYC"},
            {"name": "Political Science", "code": "GOVT"}, {"name": "Social Work", "code": "SOWK"},
            {"name": "International Relations", "code": "INRL"} # Add others if needed
        ]}
    ],
    "foundation_requirements": {
         "required_slots": [
             {"category": "English Language/Writing", "alternatives": ["FOUN1013", "FOUN1019"], "mandatory": True, "notes": "Writing Component"},
             {"category": "Science/Civilization", "alternatives": ["FOUN1101", "FOUN1201"], "mandatory": True, "notes": "Science/Civilization Component"},
             {"category": "Foreign Language", "alternatives": ACCEPTED_LANGUAGE_COURSES, "mandatory": True, "notes": "Language Component - see detailed foreign language requirement"}
         ],
         # substitution_rules defaults (allowed=False) are correct for FSS
         "excluded_courses": ["FOUN1301"],
         "notes": "FOUN1301 does not count towards FSS programmes without Dean's permission."
    },
    "special_requirements": {
        # research_course default (required=False) is correct
        "language_requirement": {
             "required": True, # Override base
             "allowed_courses": ACCEPTED_LANGUAGE_COURSES,
             # level_restriction remains None
             "exemption_rules": { # Detailed rules specific to FSS
                 "exemption_types": [
                     {"name": "CSEC/CAPE Pass", "description": "Regional students with CSEC (Grade 1-3) or CAPE Unit I/II (Grades 1-5) or equivalent", "credit_given": False, "alternative_requirements": "Students must select any two from: FOUN1101, FOUN1201, or one Level I Free Elective"},
                     {"name": "Non-English Native", "description": "International students whose first language is not English and who matriculated with ESL qualification", "credit_given": False, "alternative_requirements": "Students must select any two from: FOUN1101, FOUN1201, or one Level I Free Elective"},
                     {"name": "Mature Student", "description": "Mature students must show proficiency using Prior Learning Assessment", "credit_given": False, "alternative_requirements": ""}
                 ],
                 "application_process": "Eligible students must apply for Exemptions without Credit on the Automated Student Request System via the SAS portal."
             },
             "notes": "ALL students who have been accepted or readmitted into The University of the West Indies in the academic year 2024/2025 to read for an undergraduate degree and whose native language is English are required to register for and successfully complete a prescribed three (3) credit Foreign Language, Sign Language or Caribbean Creole course."
         }
         # out_of_major default (required=False) is correct
    },
    "notes": [
        "Minimum 90 credits required for degree.",
        "Minimum overall GPA of 2.0 required for award of degree.",
        "Foundation Requirements (9 credits): One of FOUN1013/19 AND one of FOUN1101/1201 AND one prescribed Language/Sign/Creole course.",
        "Foreign Language Requirement: ALL students whose native language is English must complete a prescribed language course.",
        "Regional students with CSEC/CAPE language passes may apply for exemption without credit.",
        "International students whose first language is not English may apply for exemption without credit."
    ]
}

# --- FHE Specifics ---
fhe_specifics = {
    "faculty": "HE",
    "faculty_name": "Faculty of Humanities and Education",
    "credit_requirements": {
        "total_credits": 90,
        "level_1": {"min_credits": 30, "notes": "Level 1 must include specific Foundation courses and potentially a basic foreign language course."},
        "level_2_and_3": {
            "min_credits": 60,
            # HE Specific level breakdown:
            "level_2": {"min_credits": 30, "min_faculty_credits": 21, "notes": "At least 21 credits must be exclusively Level 2"},
            "level_3": {"min_credits": 30, "min_faculty_credits": 24, "notes": "At least 24 credits must be exclusively Level 3"}
            # notes remains ""
        }
    },
    "departments": [
        {"department": "HUMANITIES AND EDUCATION", "majors": [
            {"name": "History", "code": "HIST"}, {"name": "Literature", "code": "LITT"},
            {"name": "Philosophy", "code": "PHIL"}, {"name": "Linguistics", "code": "LING"},
            {"name": "Spanish", "code": "SPAN"}, {"name": "French", "code": "FREN"} # Add others if needed
        ]}
    ],
    "foundation_requirements": {
         "required_slots": [
             {"category": "Writing", "alternatives": ["FOUN1016", "FOUN1019"], "mandatory": True, "notes": ""},
             {"category": "Research", "alternatives": ["FOUN1002"], "mandatory": True, "notes": ""},
             {"category": "Mixed", "alternatives": ["FOUN1201", "FOUN1301"], "mandatory": True, "notes": ""}
         ]
         # substitution_rules default (allowed=False) is correct
         # excluded_courses default ([]) is correct
         # notes default ("") is correct
    },
    "special_requirements": {
         "research_course": {"required": True, "allowed_courses": ["RESH3001", "HIST3999", "PHIL3XXX"]}, # Specify allowed research courses
         "language_requirement": {"required": True, "allowed_courses": ACCEPTED_LANGUAGE_COURSES, "level_restriction": 1, "notes": "Check regulation 5.1 for details"}, # Specify L1 restriction
         "out_of_major": {"required": True, "min_credits": 9, "notes": "At least NINE credits must be taken from within the Humanities and Education group but outside the student's declared Major/Special."}
    },
    "notes": [
        "A Faculty Research-linked course is required.",
        "Level II requires at least 30 credits (min 21 exclusively LII - check major reqs), including FOUN1201/1301.",
        "Level III requires at least 30 credits (min 24 exclusively LIII - check major reqs)."
    ]
}

# 3d. Generate Final Standardized Schemas
fst_schema_standardized = deep_update(copy.deepcopy(BASE_FACULTY_SCHEMA), fst_specifics)
fss_schema_standardized = deep_update(copy.deepcopy(BASE_FACULTY_SCHEMA), fss_specifics)
fhe_schema_standardized = deep_update(copy.deepcopy(BASE_FACULTY_SCHEMA), fhe_specifics)


# -------------------------------------
# 4. Define Major and Minor Schemas
# -------------------------------------

# Major schemas remain unchanged for now
major_schema_comp = {
    "major": "Computer Science", "faculty": "FST",
    "requirements": { "levels": [
        {"level_name": "Level 1", "required_credits": 15, "required_courses": ["COMP1220", "COMP1126", "COMP1127", "COMP1161", "COMP1210"]},
        {"level_name": "Level 2 and 3", "required_credits": 39, "required_courses": ["COMP2140", "COMP2171", "COMP2190", "COMP2201", "COMP2211", "COMP2340", "COMP3101", "COMP3161", "COMP3220", "COMP3901"]}
    ]}
}

# In Section 4. Define Major and Minor Schemas

major_schema_swen = {
    "major": "Software Engineering", "faculty": "FST",
    "requirements": { "levels": [
         {"level_name": "Level 1",
          "required_credits": 15,
          "required_courses": ["COMP1126", "COMP1127", "COMP1161", "COMP1210", "COMP1220"]
         },
         {"level_name": "Level 2 and 3",
          "required_credits": 39, # Target minimum credits for the block
          "required_courses": [ # List the 'standard' required courses
              "COMP2140", "COMP2171", "COMP2190", "COMP2201", "COMP2211",
              # COMP3911 is the standard requirement here
              "COMP3911",
              "SWEN3130", "SWEN3145", "SWEN3165", "SWEN3185", "SWEN3920"
          ],
          # NEW FIELD: Define allowed substitutions for required courses
          "alternative_substitutions": [
              {
                  "required": "COMP3911",    # The course listed in required_courses
                  "alternative": "COMP3912", # The course that can replace it
                  "alternative_credits": 6   # Explicitly state the alternative's credits
              }
              # Add more substitution rules here if needed
          ],
          "notes": [ # Changed notes to a list for clarity
              "Minimum 39 credits required at Levels 2 & 3.",
              "Requires 3 credits L2/L3 elective from Computing (e.g., COMP, INFO, SWEN prefixes).",
              "COMP3911 (3 credits) may be substituted with COMP3912 (6 credits). Taking COMP3912 contributes 6 credits to the Level 2&3 total."
              ]
         }
     ]}
}

minor_schema_mgmt = {
    "minor": "Management Studies",
    "faculty": "FSS", # Note: Technically this isn't *needed* by check_minor_requirements, but good for context
    "requirements": {
        "min_total_credits_l2_l3": 15,
        "required_courses": ["MGMT2008", "MGMT3031"],
        "electives": {
            "min_credits": 9,
            "allowed_levels": [2, 3],
            "allowed_prefixes": ["MGMT"],
            "excluded_courses": ["MGMT3022", "MGMT3061", "MGMT3062", "MGMT3069"]
        },
        "notes": [
            "Level 1 prerequisites for chosen L2/L3 courses assumed complete based on user clarification.",
            "Anti-requisites not automatically checked by this script."
        ]
    }
}

minor_schema_math = {
    "minor": "Mathematics",
    "faculty": "FST",  # Assuming Mathematics falls under FST for context
    "requirements": {
        # --- Level 1 Requirements ---
        # Note: The current 'check_minor_requirements' function primarily focuses on L2/L3.
        #       You might need to update that function or perform a separate check
        #       if you want to strictly enforce these L1 requirements automatically.
        "level_1_requirements": {
             "min_credits": 12,  # As stated in the image
             "required_courses": ["MATH1141", "MATH1142", "MATH1151", "MATH1152"], # All 4 seem required
             "notes": "Requires 12 credits from MATH1141, MATH1142, MATH1151, MATH1152."
        },

        # --- Level 2 and 3 Requirements ---
        "min_total_credits_l2_l3": 18, # Stated minimum L2/L3 credits
        "required_courses": [        # Core L2/L3 courses that MUST be included
            "MATH2401",
            "MATH2410",
            "MATH3155",
            "MATH3412"
        ],
        "electives": {
            "min_credits": 6,          # 18 total = 12 required (4*3) + 6 electives
            "allowed_levels": [2, 3],
            "allowed_prefixes": [],    # We use specific courses instead
            "excluded_courses": [],    # None specified in the image
            "allowed_courses": [
                "MATH2403", "MATH2404", "MATH2407", "MATH2411", "MATH2420",
                "MATH2421", "MATH2431", "MATH2702", "STAT2001", "MATH3401",
                "MATH3402", "MATH3411", "MATH3414", # MATH3403 & MATH3404 removed
                "MATH3421", "MATH3422", "MATH3424",
                "MATH3425", "MATH3426", # MATH3425 & MATH3426 added
                "STAT3001", "STAT3002"
            ]
        },
        "notes": [ # General notes for the minor
             "Requires 18 credits from approved Level 2 & 3 MATH/STAT courses.",
             "Must include the 4 core required L2/L3 courses plus 6 credits from the advanced electives list."
        ]
    }
}

# You would add this alongside your other schemas:
# major_schema_comp = { ... }
# major_schema_swen = { ... }
# minor_schema_mgmt = { ... }
# minor_schema_math = { ... } # Add this new schema
# -------------------------------------
# 5. Load and Process Transcript
# -------------------------------------

# Transcript data in JSON format
transcript_json = """
{
    "success": true,
    "data": {
        "student_name": "Johnson",
        "student_id": "620106542",
        "terms": [
            {
                "term_code": "202320",
                "courses": [
                    {
                        "course_code": "COMP3901+",
                        "course_title": "Group Project",
                        "credit_hours": 3.0,
                        "grade_earned": "A+",
                        "whatif_grade": "NA"
                    }
                ],
                "semester_gpa": 0.0,
                "cumulative_gpa": 2.7089,
                "degree_gpa": 2.7542,
                "credits_earned_to_date": 102
            },
            {
                "term_code": "202310",
                "courses": [
                    {
                        "course_code": "COMP3101+",
                        "course_title": "Operating Systems",
                        "credit_hours": 3.0,
                        "grade_earned": "B-",
                        "whatif_grade": "B-"
                    },
                    {
                        "course_code": "COMP3220+",
                        "course_title": "Principles of Artificial Intelligence",
                        "credit_hours": 3.0,
                        "grade_earned": "B-",
                        "whatif_grade": "B-"
                    }
                ],
                "semester_gpa": 2.7,
                "cumulative_gpa": 2.7089,
                "degree_gpa": 2.7542,
                "credits_earned_to_date": 99
            },
            {
                "term_code": "202220",
                "courses": [
                    {
                        "course_code": "COMP2340+",
                        "course_title": "Computer Systems Organization",
                        "credit_hours": 3.0,
                        "grade_earned": "B",
                        "whatif_grade": "B"
                    },
                    {
                        "course_code": "COMP3161+",
                        "course_title": "Introduction to Database Management Syst",
                        "credit_hours": 3.0,
                        "grade_earned": "B",
                        "whatif_grade": "B"
                    }
                ],
                "semester_gpa": 3.0,
                "cumulative_gpa": 2.7093,
                "degree_gpa": 2.7591,
                "credits_earned_to_date": 93
            },
            {
                "term_code": "202210",
                "courses": [
                    {
                        "course_code": "SWEN3145+",
                        "course_title": "Software Modeling",
                        "credit_hours": 3.0,
                        "grade_earned": "FMP",
                        "whatif_grade": "FMP"
                    }
                ],
                "semester_gpa": 0.0,
                "cumulative_gpa": 2.6951,
                "degree_gpa": 2.735,
                "credits_earned_to_date": 87
            },
            {
                "term_code": "202120",
                "courses": [
                    {
                        "course_code": "EDTK2025+",
                        "course_title": "Introduction To Computer Technology in E",
                        "credit_hours": 3.0,
                        "grade_earned": "A-",
                        "whatif_grade": "A-"
                    },
                    {
                        "course_code": "INFO3155+",
                        "course_title": "Information Assurance and Security",
                        "credit_hours": 3.0,
                        "grade_earned": "A",
                        "whatif_grade": "A"
                    },
                    {
                        "course_code": "SWEN3165+",
                        "course_title": "Software Testing",
                        "credit_hours": 3.0,
                        "grade_earned": "A-",
                        "whatif_grade": "A-"
                    },
                    {
                        "course_code": "SWEN3185+",
                        "course_title": "Formal Methods and Software Reliability",
                        "credit_hours": 3.0,
                        "grade_earned": "F2",
                        "whatif_grade": "F2"
                    }
                ],
                "semester_gpa": 3.175,
                "cumulative_gpa": 2.6951,
                "degree_gpa": 2.735,
                "credits_earned_to_date": 87
            },
            {
                "term_code": "202110",
                "courses": [
                    {
                        "course_code": "COMP3911+",
                        "course_title": "Internship in Computing I",
                        "credit_hours": 3.0,
                        "grade_earned": "A",
                        "whatif_grade": "A"
                    },
                    {
                        "course_code": "EDTK3004+",
                        "course_title": "Educational Technology",
                        "credit_hours": 3.0,
                        "grade_earned": "A-",
                        "whatif_grade": "A-"
                    },
                    {
                        "course_code": "PHYS2701+",
                        "course_title": "Essentials of Renewable Energy Technolog",
                        "credit_hours": 3.0,
                        "grade_earned": "B-",
                        "whatif_grade": "B-"
                    },
                    {
                        "course_code": "SWEN3130+",
                        "course_title": "Software Project Management",
                        "credit_hours": 3.0,
                        "grade_earned": "A",
                        "whatif_grade": "A"
                    },
                    {
                        "course_code": "SWEN3145+",
                        "course_title": "Software Modeling",
                        "credit_hours": 3.0,
                        "grade_earned": "F2",
                        "whatif_grade": "F2"
                    }
                ],
                "semester_gpa": 3.14,
                "cumulative_gpa": 2.6432,
                "degree_gpa": 2.625,
                "credits_earned_to_date": 78
            },
            {
                "term_code": "202020",
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
                        "grade_earned": "B",
                        "whatif_grade": "B"
                    },
                    {
                        "course_code": "INFO3180+",
                        "course_title": "Dynamic Web Development II",
                        "credit_hours": 3.0,
                        "grade_earned": "A+",
                        "whatif_grade": "A+"
                    },
                    {
                        "course_code": "SWEN3185+",
                        "course_title": "Formal Methods and Software Reliability",
                        "credit_hours": 3.0,
                        "grade_earned": "F3",
                        "whatif_grade": "F3"
                    }
                ],
                "semester_gpa": 2.65,
                "cumulative_gpa": 2.5656,
                "degree_gpa": 2.3909,
                "credits_earned_to_date": 66
            },
            {
                "term_code": "202010",
                "courses": [
                    {
                        "course_code": "COMP2140+",
                        "course_title": "Software Engineering",
                        "credit_hours": 3.0,
                        "grade_earned": "B",
                        "whatif_grade": "B"
                    },
                    {
                        "course_code": "INFO2180+",
                        "course_title": "Dynamic Web Development 1",
                        "credit_hours": 3.0,
                        "grade_earned": "A+",
                        "whatif_grade": "A+"
                    }
                ],
                "semester_gpa": 3.65,
                "cumulative_gpa": 2.5536,
                "degree_gpa": 2.2429,
                "credits_earned_to_date": 57
            },
            {
                "term_code": "201940",
                "courses": [
                    {
                        "course_code": "COMP2201+",
                        "course_title": "Discrete Mathematics for Computer Scienc",
                        "credit_hours": 3.0,
                        "grade_earned": "B",
                        "whatif_grade": "B"
                    }
                ],
                "semester_gpa": 3.0,
                "cumulative_gpa": 2.4692,
                "degree_gpa": 1.68,
                "credits_earned_to_date": 51
            },
            {
                "term_code": "201920",
                "courses": [
                    {
                        "course_code": "COMP2211+",
                        "course_title": "Analysis of Algorithms",
                        "credit_hours": 3.0,
                        "grade_earned": "EI",
                        "whatif_grade": "EI"
                    }
                ],
                "semester_gpa": 0.0,
                "cumulative_gpa": 2.448,
                "degree_gpa": 1.35,
                "credits_earned_to_date": 48
            },
            {
                "term_code": "201910",
                "courses": [
                    {
                        "course_code": "COMP2140+",
                        "course_title": "Software Engineering",
                        "credit_hours": 3.0,
                        "grade_earned": "FE1",
                        "whatif_grade": "FE1"
                    },
                    {
                        "course_code": "COMP2190+",
                        "course_title": "Net-Centric Computing",
                        "credit_hours": 3.0,
                        "grade_earned": "C",
                        "whatif_grade": "C"
                    },
                    {
                        "course_code": "COMP2201+",
                        "course_title": "Discrete Mathematics for Computer Scienc",
                        "credit_hours": 3.0,
                        "grade_earned": "FE1",
                        "whatif_grade": "FE1"
                    }
                ],
                "semester_gpa": 1.8,
                "cumulative_gpa": 2.55,
                "degree_gpa": 1.8,
                "credits_earned_to_date": 48
            },
            {
                "term_code": "201820",
                "courses": [
                    {
                        "course_code": "CHIN1002",
                        "course_title": "Beginner's Chinese II",
                        "credit_hours": 3.0,
                        "grade_earned": "C",
                        "whatif_grade": "C"
                    },
                    {
                        "course_code": "COMP1161",
                        "course_title": "Introduction to Object-Oriented Programm",
                        "credit_hours": 3.0,
                        "grade_earned": "B",
                        "whatif_grade": "B"
                    },
                    {
                        "course_code": "COMP1210",
                        "course_title": "Mathematics for Computing",
                        "credit_hours": 3.0,
                        "grade_earned": "C+",
                        "whatif_grade": "C+"
                    },
                    {
                        "course_code": "ECON1003",
                        "course_title": "Mathematics for Social Sciences I",
                        "credit_hours": 3.0,
                        "grade_earned": "A",
                        "whatif_grade": "A"
                    },
                    {
                        "course_code": "FOUN1101",
                        "course_title": "Caribbean Civilization",
                        "credit_hours": 3.0,
                        "grade_earned": "B+",
                        "whatif_grade": "B+"
                    }
                ],
                "semester_gpa": 2.92,
                "cumulative_gpa": 2.6571,
                "degree_gpa": null,
                "credits_earned_to_date": 45
            },
            {
                "term_code": "201810",
                "courses": [
                    {
                        "course_code": "CHIN1001",
                        "course_title": "Beginner's Chinese I",
                        "credit_hours": 3.0,
                        "grade_earned": "C+",
                        "whatif_grade": "C+"
                    },
                    {
                        "course_code": "COMP1161",
                        "course_title": "Introduction to Object-Oriented Programm",
                        "credit_hours": 3.0,
                        "grade_earned": "FE1",
                        "whatif_grade": "FE1"
                    },
                    {
                        "course_code": "COMP1210",
                        "course_title": "Mathematics for Computing",
                        "credit_hours": 3.0,
                        "grade_earned": "FE1",
                        "whatif_grade": "FE1"
                    },
                    {
                        "course_code": "FOUN1014",
                        "course_title": "Critical Reading and Writing in Science",
                        "credit_hours": 3.0,
                        "grade_earned": "C",
                        "whatif_grade": "C"
                    }
                ],
                "semester_gpa": 1.925,
                "cumulative_gpa": 2.575,
                "degree_gpa": null,
                "credits_earned_to_date": 30
            },
            {
                "term_code": "201740",
                "courses": [
                    {
                        "course_code": "COMP1161",
                        "course_title": "Introduction to Object-Oriented Programm",
                        "credit_hours": 3.0,
                        "grade_earned": "FE1",
                        "whatif_grade": "FE1"
                    }
                ],
                "semester_gpa": 1.7,
                "cumulative_gpa": 2.7917,
                "degree_gpa": null,
                "credits_earned_to_date": 24
            },
            {
                "term_code": "201720",
                "courses": [
                    {
                        "course_code": "COMP1161",
                        "course_title": "Introduction to Object-Oriented Programm",
                        "credit_hours": 3.0,
                        "grade_earned": "FE1",
                        "whatif_grade": "FE1"
                    },
                    {
                        "course_code": "FOUN1014",
                        "course_title": "Critical Reading and Writing in Science",
                        "credit_hours": 3.0,
                        "grade_earned": "F1",
                        "whatif_grade": "F1"
                    },
                    {
                        "course_code": "SWEN1003",
                        "course_title": "Current and Future Trends in Computing f",
                        "credit_hours": 3.0,
                        "grade_earned": "B+",
                        "whatif_grade": "B+"
                    },
                    {
                        "course_code": "SWEN1005",
                        "course_title": "Mobile Web Programming",
                        "credit_hours": 3.0,
                        "grade_earned": "B-",
                        "whatif_grade": "B-"
                    },
                    {
                        "course_code": "SWEN1007",
                        "course_title": "Software Engineering Essentials",
                        "credit_hours": 3.0,
                        "grade_earned": "B+",
                        "whatif_grade": "B+"
                    },
                    {
                        "course_code": "SWEN1008",
                        "course_title": "Technical Writing for Software Engineers",
                        "credit_hours": 3.0,
                        "grade_earned": "A+",
                        "whatif_grade": "A+"
                    }
                ],
                "semester_gpa": 2.8333,
                "cumulative_gpa": 2.8909,
                "degree_gpa": null,
                "credits_earned_to_date": 24
            },
            {
                "term_code": "201710",
                "courses": [
                    {
                        "course_code": "COMP1126",
                        "course_title": "Introduction to Computing I",
                        "credit_hours": 3.0,
                        "grade_earned": "A-",
                        "whatif_grade": "A-"
                    },
                    {
                        "course_code": "COMP1127",
                        "course_title": "Introduction to Computing II",
                        "credit_hours": 3.0,
                        "grade_earned": "B",
                        "whatif_grade": "B"
                    },
                    {
                        "course_code": "COMP1210",
                        "course_title": "Mathematics for Computing",
                        "credit_hours": 3.0,
                        "grade_earned": "FE1",
                        "whatif_grade": "FE1"
                    },
                    {
                        "course_code": "COMP1220",
                        "course_title": "Computing and Society",
                        "credit_hours": 3.0,
                        "grade_earned": "B-",
                        "whatif_grade": "B-"
                    },
                    {
                        "course_code": "SWEN1006",
                        "course_title": "Research Methods for Software Engineers",
                        "credit_hours": 3.0,
                        "grade_earned": "A-",
                        "whatif_grade": "A-"
                    }
                ],
                "semester_gpa": 2.96,
                "cumulative_gpa": 2.96,
                "degree_gpa": null,
                "credits_earned_to_date": 12
            }
        ],
        "overall": {
            "cumulative_gpa": 2.7089,
            "degree_gpa": 2.7542,
            "total_credits_earned": 102
        }
    }
}
"""

# Parse transcript data
transcript_data = json.loads(transcript_json)


# -------------------------------------
# 6. Requirement Checking Functions
# -------------------------------------

def check_foundation_slots_specific_courses(transcript: Dict[str, Any], faculty_schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enhanced version of check_foundation_slots that uses specific course codes
    for language substitutions and handles excluded courses.
    """
    # Get foundation schema
    foundation_schema = faculty_schema.get("foundation_requirements", {})
    if not foundation_schema:
        return {"all_slots_satisfied": True, "meets_total_credits": True, "slots_status": [],
                "foundation_earned_credits": 0.0, "total_foundation_required": 0}

    # Extract requirements
    required_slots = foundation_schema.get("required_slots", [])
    sub_rules = foundation_schema.get("substitution_rules", {})
    allowed_substitution = sub_rules.get("allowed", False)
    allowed_language_courses = set(sub_rules.get("allowed_courses", [])) if allowed_substitution else set()
    max_substitutions = sub_rules.get("max_substitutions", 0) if allowed_substitution else 0
    excluded_slots_indices = set(sub_rules.get("excluded_slots", []))
    excluded_courses = set(foundation_schema.get("excluded_courses", []))
    total_foundation_required = foundation_schema.get("total_foundation_credits", 9)

    # Get all earned courses with details
    earned_courses_details = []
    for term in transcript.get("data", {}).get("terms", []):
        for course in term.get("courses", []):
            grade = course.get("grade_earned", "NA")
            if grade in ACCEPTED_GRADES:
                code = clean_course_code(course.get("course_code", ""))
                # Skip excluded courses
                if code in excluded_courses:
                    continue

                credits_ = course.get("credit_hours", 0.0)
                earned_courses_details.append({"code": code, "credits": credits_})

    # Split by type - using exact course codes
    earned_foundation = [c for c in earned_courses_details if c["code"].startswith("FOUN")]
    earned_language = []
    if allowed_substitution and allowed_language_courses:
        earned_language = [c for c in earned_courses_details if c["code"] in allowed_language_courses]

    # Process slots
    slots_status = []
    substitutions_used = 0
    foundation_credits_earned = 0.0
    used_course_codes = set()  # Track all courses used

    for slot_index, slot in enumerate(required_slots):
        alternatives = set(slot.get("alternatives", []))
        is_substitutable = not slot.get("mandatory", False) and slot_index not in excluded_slots_indices

        slot_status = {
            "category": slot.get("category", f"Slot {slot_index+1}"),
            "alternatives": list(alternatives),
            "notes": slot.get("notes", ""),
            "satisfied_by": None
        }

        found_match = False

        # 1. Try foundation courses first
        for f_course in earned_foundation:
            if f_course["code"] in alternatives and f_course["code"] not in used_course_codes:
                slot_status.update({
                    "satisfied_by": "foundation",
                    "course": f_course["code"],
                    "credits": f_course["credits"]
                })
                foundation_credits_earned += f_course["credits"]
                used_course_codes.add(f_course["code"])
                found_match = True
                break

        # 2. Try language substitution if applicable (using exact course codes)
        if not found_match and is_substitutable and allowed_substitution and substitutions_used < max_substitutions:
            for l_course in earned_language:
                if l_course["code"] not in used_course_codes:
                    slot_status.update({
                        "satisfied_by": "language substitution",
                        "course": l_course["code"],
                        "credits": l_course["credits"]
                    })
                    foundation_credits_earned += l_course["credits"]
                    used_course_codes.add(l_course["code"])
                    substitutions_used += 1
                    found_match = True
                    break

        slots_status.append(slot_status)

    # Check if any excluded courses were taken
    excluded_taken = []
    for term in transcript.get("data", {}).get("terms", []):
        for course in term.get("courses", []):
            code = clean_course_code(course.get("course_code", ""))
            if code in excluded_courses:
                grade = course.get("grade_earned", "NA")
                if grade != "NA": # Only report if actually taken and graded
                    excluded_taken.append(code)


    # Final checks
    all_slots_satisfied = all(item["satisfied_by"] is not None for item in slots_status)
    # Ensure foundation credits don't exceed required if only counting towards foundation
    foundation_credits_earned = min(foundation_credits_earned, total_foundation_required)
    meets_total_credits = foundation_credits_earned >= total_foundation_required


    return {
        "all_slots_satisfied": all_slots_satisfied,
        "meets_total_credits": meets_total_credits,
        "slots_status": slots_status,
        "foundation_earned_credits": foundation_credits_earned,
        "total_foundation_required": total_foundation_required,
        "excluded_courses_taken": excluded_taken,
        "substitutions_used": substitutions_used,
        "max_substitutions_allowed": max_substitutions
    }

def check_language_requirement_specific_courses(transcript: Dict[str, Any], faculty_schema: Dict[str, Any], student_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Check language requirements using specific course codes and exemption rules.
    """
    lang_req = faculty_schema.get("special_requirements", {}).get("language_requirement", {})

    if not lang_req.get("required", False):
        return {"required": False, "completed": None, "exempted": False}

    allowed_language_courses = set(lang_req.get("allowed_courses", []))

    # Check for exemption
    exemption_info = {"exempted": False, "reason": "", "alternative_requirements": ""}
    if lang_req.get("exemption_rules") and student_info:
        # --- Simplified Exemption Logic based on FSS example ---
        is_native_english = student_info.get('is_native_english', True)
        has_language_qualification = student_info.get('has_language_qualification', False)
        is_international_non_english = student_info.get('is_international', False) and not is_native_english

        exemption_reason = ""
        alternative_req = ""
        if has_language_qualification:
             exemption_reason = "CSEC/CAPE language qualification"
             for rule in lang_req["exemption_rules"].get("exemption_types", []):
                 if "CSEC/CAPE Pass" in rule.get("name", ""):
                      alternative_req = rule.get("alternative_requirements", "")
                      break
        elif is_international_non_english:
             exemption_reason = "International student with non-English first language"
             for rule in lang_req["exemption_rules"].get("exemption_types", []):
                 if "Non-English Native" in rule.get("name", ""):
                      alternative_req = rule.get("alternative_requirements", "")
                      break

        if exemption_reason:
            return {
                "required": True, "completed": None, "exempted": True,
                "exemption_reason": exemption_reason,
                "alternative_requirements": alternative_req,
                "alternative_fulfilled": None # Requires further checking logic
            }
        # --- End Simplified Exemption Logic ---

    # If not exempted, check if requirement is met by course completion
    completed = False
    completed_course = None
    for term in transcript.get("data", {}).get("terms", []):
        for course in term.get("courses", []):
            grade = course.get("grade_earned", "NA")
            if grade in ACCEPTED_GRADES:
                code = clean_course_code(course.get("course_code", ""))
                if code in allowed_language_courses:
                    completed = True
                    completed_course = code
                    break
        if completed:
            break

    return {
        "required": True, "completed": completed, "completed_course": completed_course,
        "exempted": False, "status": "Completed" if completed else "Required but not completed"
    }


def check_faculty_requirements_standardized(transcript: Dict[str, Any], faculty_schema: Dict[str, Any], student_major_code: Optional[str] = None, student_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Check faculty requirements using the standardized schema structure.
    """
    credit_reqs = faculty_schema.get("credit_requirements", {})
    total_required = credit_reqs.get("total_credits", 0)
    level1_reqs = credit_reqs.get("level_1", {})
    level1_required = level1_reqs.get("min_credits", 0)
    level1_faculty_required = level1_reqs.get("min_faculty_credits") # Can be None
    level23_reqs = credit_reqs.get("level_2_and_3", {})
    level23_required = level23_reqs.get("min_credits", 0)

    special_reqs = faculty_schema.get("special_requirements", {})
    research_req = special_reqs.get("research_course", {})
    research_required = research_req.get("required", False)
    fac_research_courses = set(research_req.get("allowed_courses", [])) if research_required else set()
    language_req = special_reqs.get("language_requirement", {})
    language_required = language_req.get("required", False)
    outofmajor_req = special_reqs.get("out_of_major", {})
    outofmajor_required = outofmajor_req.get("required", False)
    fac_min_outofmajor = outofmajor_req.get("min_credits", 0) if outofmajor_required else 0 # Use 0 if not required

    earned = {"total": 0.0, "level_1": 0.0, "level_1_faculty": 0.0, "level_2_and_3": 0.0}
    potential = {"total": 0.0, "level_1": 0.0, "level_1_faculty": 0.0, "level_2_and_3": 0.0}
    level1_faculty_courses_list = []
    outofmajor_credits = 0.0
    completed_research = False

    # Add faculty code to schema dict for later use if needed
    faculty_schema['faculty_code'] = faculty_schema.get('faculty')
    if outofmajor_required:
         faculty_schema['student_major_code'] = student_major_code


    for term in transcript.get("data", {}).get("terms", []):
        for course in term.get("courses", []):
            credits = course.get("credit_hours", 0.0)
            code = clean_course_code(course.get("course_code", ""))
            level = get_course_level(code)
            grade = course.get("grade_earned", "NA")
            prefix = get_course_prefix(code)
            is_fac = is_faculty_course(code, faculty_schema)

            if grade in ACCEPTED_GRADES:
                # Skip excluded foundation courses for credit counting towards faculty reqs
                if is_excluded_course(code, faculty_schema):
                    continue

                earned["total"] += credits
                if level == 1:
                    earned["level_1"] += credits
                    if is_fac:
                        earned["level_1_faculty"] += credits
                        level1_faculty_courses_list.append((code, credits))
                elif level in [2, 3]:
                    earned["level_2_and_3"] += credits

                if research_required and code in fac_research_courses:
                    completed_research = True

                # Count out-of-major credits (only if requirement exists)
                if outofmajor_required and is_fac and student_major_code and prefix != student_major_code:
                    outofmajor_credits += credits

            elif grade == "NA": # In-progress courses
                # Skip potential credits from excluded foundation courses too
                if is_excluded_course(code, faculty_schema):
                     continue

                potential["total"] += credits
                if level == 1:
                    potential["level_1"] += credits
                    if is_fac: potential["level_1_faculty"] += credits
                elif level in [2, 3]:
                    potential["level_2_and_3"] += credits

    # Check language requirement status
    language_status = check_language_requirement_specific_courses(transcript, faculty_schema, student_info)
    language_completed = language_status.get("completed", False) or language_status.get("exempted", False)

    # Check foundation requirements status
    foundation_status = check_foundation_slots_specific_courses(transcript, faculty_schema)

    # Check requirements and identify missing ones
    missing = {}
    if earned["total"] < total_required:
        missing["total_credits"] = round(total_required - earned["total"], 1)
    if earned["level_1"] < level1_required:
        missing["level_1_credits"] = round(level1_required - earned["level_1"], 1)
    if level1_faculty_required is not None and earned["level_1_faculty"] < level1_faculty_required:
         missing["level_1_faculty_credits"] = round(level1_faculty_required - earned["level_1_faculty"], 1)
    if earned["level_2_and_3"] < level23_required:
        missing["level_2_and_3_credits"] = round(level23_required - earned["level_2_and_3"], 1)

    if not foundation_status["all_slots_satisfied"]:
        missing["foundation_slots"] = "Not all required foundation slots satisfied"
    # Check foundation credits *after* potentially capping in check_foundation_slots
    if not foundation_status["meets_total_credits"]:
        missing["foundation_credits"] = round(foundation_status["total_foundation_required"] - foundation_status["foundation_earned_credits"], 1)


    if research_required and not completed_research:
        missing["research_linked_course"] = f"Required Research course missing (e.g., {', '.join(list(fac_research_courses))})"
    if language_required and not language_completed:
        missing["language_requirement"] = "Required Language requirement not met/exempted."
    if outofmajor_required and outofmajor_credits < fac_min_outofmajor:
        missing["outofmajor_credits"] = f"{round(fac_min_outofmajor - outofmajor_credits, 1)} credits needed outside major {student_major_code}."

    # Add outofmajor to earned credits dict only if requirement exists for the faculty
    if outofmajor_required:
        earned["outofmajor_credits"] = outofmajor_credits

    # Include faculty specific status in earned dict for reporting
    earned["faculty_specific_status"] = {
         "research_course_completed": completed_research if research_required else None
    }


    return {
        "faculty": faculty_schema.get("faculty", ""),
        "passes_faculty": len(missing) == 0,
        "credits_earned": earned,
        "potential_credits": potential, # Potential gain from NA courses
        "foundation_status": foundation_status,
        "language_status": language_status if language_required else None, # Store the full status dict or None
        "missing_requirements": missing,
        "level1_faculty_courses_list": level1_faculty_courses_list
    }

# In Section 6. Requirement Checking Functions

def check_major_requirements_with_levels(transcript: Dict[str, Any], major_schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Check major requirements organized by level blocks, handling alternatives.
    """
    results = []
    all_blocks_passed = True
    level_blocks = major_schema.get("requirements", {}).get("levels", [])
    courses_by_level = {1: [], 2: [], 3: [], 4: []} # Level 4 just in case
    earned_course_codes = set()
    # Track potential credits per level block and codes
    potential_courses = {'credits_by_level': {1: 0.0, 2: 0.0, 3: 0.0}, 'codes': set()}

    # Process transcript once
    for term in transcript.get("data", {}).get("terms", []):
        for course in term.get("courses", []):
            code = clean_course_code(course.get("course_code", ""))
            credits = course.get("credit_hours", 0.0)
            level = get_course_level(code)
            grade = course.get("grade_earned", "NA")

            if grade in ACCEPTED_GRADES:
                earned_course_codes.add(code)
                if level in courses_by_level:
                    courses_by_level[level].append({"code": code, "credits": credits, "grade": grade})
            elif grade == "NA": # In-progress
                 if level in potential_courses['credits_by_level']:
                      potential_courses['credits_by_level'][level] += credits
                 potential_courses['codes'].add(code)


    # Check each major block
    for block in level_blocks:
        block_name = block.get("level_name", "Unknown Level")
        block_required_credits = block.get("required_credits", 0)
        block_required_courses_set = set(block.get("required_courses", []))
        # Get substitution rules for this block
        block_substitutions = block.get("alternative_substitutions", [])
        substitution_map = {sub['required']: sub['alternative'] for sub in block_substitutions}

        # Determine relevant levels for this block (simplified logic)
        relevant_levels = []
        if "Level 1" in block_name: relevant_levels = [1]
        elif "Level 2 and 3" in block_name: relevant_levels = [2, 3]
        elif "Level 2" in block_name: relevant_levels = [2]
        elif "Level 3" in block_name: relevant_levels = [3]
        else: relevant_levels = [1, 2, 3] # Default guess if name doesn't match

        # Calculate earned credits (sums actual credits of earned courses)
        block_earned_credits = sum(c["credits"] for lvl in relevant_levels for c in courses_by_level.get(lvl, []))
        # Calculate potential credits from NA courses in relevant levels
        block_potential_credits = sum(potential_courses['credits_by_level'].get(lvl, 0.0) for lvl in relevant_levels)

        # --- Check required courses, considering alternatives ---
        completed_required_in_block_list = []
        missing_required_courses_list = []
        for req_course in block_required_courses_set:
            is_satisfied = False
            if req_course in earned_course_codes:
                is_satisfied = True
                completed_required_in_block_list.append(req_course)
            else:
                # Check if an alternative was taken instead
                alternative_course = substitution_map.get(req_course)
                if alternative_course and alternative_course in earned_course_codes:
                    is_satisfied = True
                    # Report satisfaction via the alternative
                    completed_required_in_block_list.append(f"{req_course} (satisfied by {alternative_course})")

            if not is_satisfied:
                missing_required_courses_list.append(req_course)
        # --- End required course check ---

        # Check what's missing based on earned courses
        block_missing = {}
        # Credit check compares earned (actual sum) against required target
        if block_earned_credits < block_required_credits:
            block_missing["credits"] = round(block_required_credits - block_earned_credits, 1)

        # Check if any required courses (or their alternatives) are missing
        if missing_required_courses_list:
            block_missing["required_courses"] = missing_required_courses_list

        block_passes = len(block_missing) == 0
        if not block_passes:
            all_blocks_passed = False

        results.append({
            "block_name": block_name,
            "required_credits": block_required_credits,
            "required_courses": list(block_required_courses_set), # Show original list
            "alternative_substitutions": block_substitutions, # Include for context
            "earned_credits_in_block": block_earned_credits,
            "potential_credits_in_block": block_potential_credits,
            "completed_required_in_block": completed_required_in_block_list, # Shows how requirement met
            "missing": block_missing,
            "passes": block_passes,
            "notes": block.get("notes", "") # Keep existing notes field
        })

    return {
        "major": major_schema.get("major", ""),
        "faculty": major_schema.get("faculty", ""),
        "blocks": results,
        "passes_major": all_blocks_passed,
        "potential_courses": potential_courses # Pass potential info for graduation check
    }

# Replace the existing check_minor_requirements function with this one:

def check_minor_requirements(transcript: Dict[str, Any], minor_schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Check minor requirements, including optional Level 1 and standard Level 2/3 checks.
    """
    requirements = minor_schema.get("requirements", {})
    missing_summary = {} # Store all missing items
    passes_minor = True # Assume passes until a failure is found

    # --- Gather all earned course codes ---
    all_earned_course_codes = set()
    earned_courses_by_level = {1: [], 2: [], 3: []} # Store details for credit calculation
    potential_minor_courses = [] # Store potential NA courses matching L2/L3 criteria

    for term in transcript.get("data", {}).get("terms", []):
        for course in term.get("courses", []):
            code = clean_course_code(course.get("course_code", ""))
            credits = course.get("credit_hours", 0.0)
            level = get_course_level(code)
            prefix = get_course_prefix(code)
            grade = course.get("grade_earned", "NA")
            details = {"code": code, "credits": credits, "level": level, "prefix": prefix}

            if grade in ACCEPTED_GRADES:
                all_earned_course_codes.add(code)
                if level in earned_courses_by_level:
                     earned_courses_by_level[level].append(details)
            elif grade == "NA":
                 # Store potential L2/L3 courses for later check
                 allowed_elective_levels_check = set(requirements.get("electives", {}).get("allowed_levels", [2, 3]))
                 allowed_elective_prefixes_check = set(requirements.get("electives", {}).get("allowed_prefixes", []))
                 is_potential_elective_candidate = (
                      level in allowed_elective_levels_check and
                      (not allowed_elective_prefixes_check or prefix in allowed_elective_prefixes_check)
                 )
                 if is_potential_elective_candidate:
                      potential_minor_courses.append(details)


    # --- 1. Check Level 1 Requirements (if defined) ---
    l1_reqs = requirements.get("level_1_requirements")
    completed_l1_required = []
    missing_l1_required = []
    passes_l1 = True
    if l1_reqs:
        l1_required_set = set(l1_reqs.get("required_courses", []))
        completed_l1_required = list(l1_required_set.intersection(all_earned_course_codes))
        missing_l1_required = list(l1_required_set - all_earned_course_codes)
        if missing_l1_required:
            missing_summary["level_1_required_courses"] = missing_l1_required
            passes_l1 = False
            passes_minor = False # Overall minor fails if L1 fails
        # Could add L1 credit check if needed:
        # l1_credits_earned = sum(c['credits'] for c in earned_courses_by_level[1] if c['code'] in l1_required_set)
        # if l1_credits_earned < l1_reqs.get("min_credits", 0):
        #     missing_summary["level_1_credits"] = round(l1_reqs.get("min_credits", 0) - l1_credits_earned, 1)
        #     passes_l1 = False; passes_minor = False

    # --- 2. Check Level 2/3 Requirements ---
    min_total_l2_l3 = requirements.get("min_total_credits_l2_l3", 0)
    required_l2l3_set = set(requirements.get("required_courses", [])) # L2/L3 required core
    electives_req = requirements.get("electives", {})
    min_elective_credits = electives_req.get("min_credits", 0)
    allowed_elective_levels = set(electives_req.get("allowed_levels", [2, 3]))
    # Use specific allowed courses if available, otherwise prefixes
    allowed_elective_courses = set(electives_req.get("allowed_courses", []))
    allowed_elective_prefixes = set(electives_req.get("allowed_prefixes", [])) if not allowed_elective_courses else set()
    excluded_courses_set = set(electives_req.get("excluded_courses", []))

    # Filter earned courses for L2/L3 minor contributions
    earned_l2_l3_courses_details = earned_courses_by_level[2] + earned_courses_by_level[3]

    # Check L2/L3 required courses against ALL earned codes
    completed_l2l3_required = list(required_l2l3_set.intersection(all_earned_course_codes))
    missing_l2l3_required = list(required_l2l3_set - all_earned_course_codes)
    if missing_l2l3_required:
        missing_summary["level_2_3_required_courses"] = missing_l2l3_required
        passes_minor = False

    # Calculate credits from relevant earned L2/L3 courses
    required_credits_earned_l2l3 = 0.0
    valid_elective_credits_earned_l2l3 = 0.0
    valid_electives_list_l2l3 = []
    used_for_l2l3_required = set()

    # Sum credits for completed L2/L3 required courses
    for req_code in completed_l2l3_required:
        for course in earned_l2_l3_courses_details:
            if course["code"] == req_code and course["code"] not in used_for_l2l3_required:
                required_credits_earned_l2l3 += course["credits"]
                used_for_l2l3_required.add(course["code"])
                break

    # Sum credits for valid L2/L3 electives
    for course in earned_l2_l3_courses_details:
        # Check if it's an elective candidate
        is_elective_candidate = False
        if allowed_elective_courses:
            if course["code"] in allowed_elective_courses:
                 is_elective_candidate = True
        elif allowed_elective_prefixes: # Only check prefixes if allowed_courses is empty
            if course["prefix"] in allowed_elective_prefixes:
                 is_elective_candidate = True
        else: # If neither allowed_courses nor allowed_prefixes specified, assume any L2/L3 is candidate
            is_elective_candidate = True

        # Check if it's valid (not excluded, not already used for required)
        if (is_elective_candidate and
            course["code"] not in excluded_courses_set and
            course["code"] not in used_for_l2l3_required): # Must not be already counted as required
            valid_elective_credits_earned_l2l3 += course["credits"]
            valid_electives_list_l2l3.append(course["code"])

    # Check if enough elective credits
    if valid_elective_credits_earned_l2l3 < min_elective_credits:
        missing_summary["elective_credits_l2_l3"] = round(min_elective_credits - valid_elective_credits_earned_l2l3, 1)
        passes_minor = False

    # Check if enough total L2/L3 minor credits
    total_minor_credits_earned_l2l3 = required_credits_earned_l2l3 + valid_elective_credits_earned_l2l3
    if total_minor_credits_earned_l2l3 < min_total_l2_l3:
        missing_summary["total_minor_credits_l2_l3"] = round(min_total_l2_l3 - total_minor_credits_earned_l2l3, 1)
        passes_minor = False

    # --- 3. Final Result ---
    return {
        "minor": minor_schema.get("minor", "Unknown"),
        "passes_minor": passes_minor, # Overall pass status
        # Level 1 Results
        "level_1_requirements_defined": bool(l1_reqs),
        "passes_level_1": passes_l1,
        "completed_l1_required_courses": completed_l1_required,
        # Level 2/3 Results
        "earned_total_credits_l2_l3": total_minor_credits_earned_l2l3,
        "required_total_credits_l2_l3": min_total_l2_l3,
        "completed_l2_l3_required_courses": completed_l2l3_required,
        "earned_elective_credits_l2_l3": valid_elective_credits_earned_l2l3,
        "required_elective_credits_l2_l3": min_elective_credits,
        "valid_l2_l3_electives_taken": valid_electives_list_l2l3,
        # Combined Missing & Potential
        "missing_requirements": missing_summary,
        "potential_minor_courses": potential_minor_courses
    }

def check_all_requirements(transcript: Dict[str, Any],
                           faculty_schema: Dict[str, Any],
                           major_schema: Dict[str, Any],
                           student_major_code: Optional[str] = None,
                           minor_schema: Optional[Dict[str, Any]] = None,
                           student_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Check all requirements (faculty, major, and optional minor).
    """
    if faculty_schema.get("faculty") != major_schema.get("faculty"):
        raise ValueError(f"Faculty mismatch: Faculty schema {faculty_schema.get('faculty')} vs Major schema {major_schema.get('faculty')}")

    faculty_result = check_faculty_requirements_standardized(transcript, faculty_schema, student_major_code, student_info)
    major_result = check_major_requirements_with_levels(transcript, major_schema)

    minor_result = None
    if minor_schema:
        minor_result = check_minor_requirements(transcript, minor_schema)

    # Determine eligibility based on FACULTY and MAJOR only
    eligible_for_graduation = faculty_result["passes_faculty"] and major_result["passes_major"]

    # Determine if ALL declared programs (including minor) are passed
    passes_all_requirements = eligible_for_graduation
    if minor_result:
        passes_all_requirements = passes_all_requirements and minor_result["passes_minor"]

    return {
        "student_major_code": student_major_code,
        "eligible_for_graduation": eligible_for_graduation, # Based on Faculty + Major
        "passes_all_requirements": passes_all_requirements, # Based on Faculty + Major + Minor
        "faculty_result": faculty_result,
        "major_result": major_result,
        "minor_result": minor_result,
        # Pass schemas along for potential check
        "faculty_schema": faculty_schema,
        "major_schema": major_schema,
        "minor_schema": minor_schema,
        # Pass transcript along for potential check to access NA courses easily
        "transcript": transcript # Pass the original transcript data
    }


def check_potential_graduation_standardized(result: Dict[str, Any],
                                            student_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Evaluate potential graduation status using the standardized schema and results from check_all_requirements.
    """
    # Extract results and schemas from the input 'result' dictionary
    faculty_result = result["faculty_result"]
    major_result = result["major_result"]
    minor_result = result.get("minor_result") # Might be None
    faculty_schema = result["faculty_schema"]
    major_schema = result["major_schema"]
    minor_schema = result.get("minor_schema") # Might be None
    student_major_code = result.get("student_major_code")
    transcript = result["transcript"] # Get transcript from result

    # --- FACULTY POTENTIAL CHECK ---
    potential_faculty_passes = faculty_result["passes_faculty"] # Start with current status
    potential_faculty_missing = copy.deepcopy(faculty_result["missing_requirements"]) # Start with current missing
    potential_fulfillment_map = {} # Map: course_code -> list of requirements it helps fulfill

    if not potential_faculty_passes:
         # Get potential credits calculated during faculty check
         potential_credits_gain = faculty_result["potential_credits"]
         earned_credits = faculty_result["credits_earned"]

         # Get requirements
         credit_reqs = faculty_schema.get("credit_requirements", {})
         total_req = credit_reqs.get("total_credits", 0)
         level1_req = credit_reqs.get("level_1", {}).get("min_credits", 0)
         level1_faculty_req = credit_reqs.get("level_1", {}).get("min_faculty_credits") # Can be None
         level23_req = credit_reqs.get("level_2_and_3", {}).get("min_credits", 0)

         special_reqs = faculty_schema.get("special_requirements", {})
         research_req = special_reqs.get("research_course", {})
         research_required = research_req.get("required", False)
         fac_research_courses = set(research_req.get("allowed_courses", [])) if research_required else set()
         language_req = special_reqs.get("language_requirement", {})
         language_required = language_req.get("required", False)
         language_courses = set(language_req.get("allowed_courses", [])) if language_required else set()
         outofmajor_req = special_reqs.get("out_of_major", {})
         outofmajor_required = outofmajor_req.get("required", False)
         fac_min_outofmajor = outofmajor_req.get("min_credits", 0) if outofmajor_required else 0

         # Get in-progress course details (re-iterate minimal processing using passed transcript)
         in_progress_courses_details = []
         for term in transcript.get("data", {}).get("terms", []): # Use transcript from result
             for course in term.get("courses", []):
                 if course.get("grade_earned") == "NA":
                     code = clean_course_code(course.get("course_code", ""))
                     credits = course.get("credit_hours", 0.0)
                     level = get_course_level(code)
                     prefix = get_course_prefix(code)
                     is_fac = is_faculty_course(code, faculty_schema)
                     is_excluded_foun = is_excluded_course(code, faculty_schema)

                     details = {"code": code, "credits": credits, "level": level, "prefix": prefix, "is_faculty": is_fac, "is_excluded_foun": is_excluded_foun}
                     in_progress_courses_details.append(details)
                     if code not in potential_fulfillment_map: potential_fulfillment_map[code] = []


         # --- Recalculate totals including potential ---
         potential_total = earned_credits.get("total", 0) + potential_credits_gain.get("total", 0)
         potential_l1 = earned_credits.get("level_1", 0) + potential_credits_gain.get("level_1", 0)
         potential_l1f = earned_credits.get("level_1_faculty", 0) + potential_credits_gain.get("level_1_faculty", 0)
         potential_l23 = earned_credits.get("level_2_and_3", 0) + potential_credits_gain.get("level_2_and_3", 0)
         potential_oom = earned_credits.get("outofmajor_credits", 0) # Start with earned (if req exists)
         potential_research_completed = earned_credits.get("faculty_specific_status", {}).get("research_course_completed", False)

         # Check initial language completion status safely
         current_lang_status = faculty_result.get("language_status") # Get the value, could be None
         potential_language_completed = False # Default if no status or not completed/exempted
         if current_lang_status: # Only check if the status dictionary exists (is not None)
             potential_language_completed = (current_lang_status.get("completed", False) or
                                             current_lang_status.get("exempted", False))


         # Add potential out-of-major credits from in-progress
         if outofmajor_required:
             for ip_course in in_progress_courses_details:
                  if not ip_course["is_excluded_foun"] and ip_course["is_faculty"] and student_major_code and ip_course["prefix"] != student_major_code:
                       potential_oom += ip_course["credits"]
                       potential_fulfillment_map[ip_course["code"]].append(f"Faculty Out-of-Major Credits ({ip_course['credits']:.1f})")


         # Check if in-progress courses fulfill other specific requirements
         for ip_course in in_progress_courses_details:
             code = ip_course["code"]
             credits = ip_course["credits"]
             if not ip_course["is_excluded_foun"]: # Excluded courses don't count for credits
                 potential_fulfillment_map[code].append(f"Faculty Total Credits ({credits:.1f})")
                 if ip_course["level"] == 1:
                     potential_fulfillment_map[code].append(f"Faculty Level 1 Credits ({credits:.1f})")
                     if ip_course["is_faculty"] and level1_faculty_req is not None:
                          potential_fulfillment_map[code].append(f"Faculty Level 1 Faculty Credits ({credits:.1f})")
                 elif ip_course["level"] in [2, 3]:
                     potential_fulfillment_map[code].append(f"Faculty Level 2/3 Credits ({credits:.1f})")

             if research_required and code in fac_research_courses:
                 potential_research_completed = True # Now potentially completed
                 potential_fulfillment_map[code].append("Faculty Research Requirement")
             if language_required and code in language_courses:
                 potential_language_completed = True # Now potentially completed
                 potential_fulfillment_map[code].append("Faculty Language Requirement")
             # Foundation slot fulfillment is complex - skip detailed check for now


         # --- Update missing dictionary based on potential values ---
         if "total_credits" in potential_faculty_missing and potential_total >= total_req:
             del potential_faculty_missing["total_credits"]
         if "level_1_credits" in potential_faculty_missing and potential_l1 >= level1_req:
             del potential_faculty_missing["level_1_credits"]
         if "level_1_faculty_credits" in potential_faculty_missing and level1_faculty_req is not None and potential_l1f >= level1_faculty_req:
             del potential_faculty_missing["level_1_faculty_credits"]
         if "level_2_and_3_credits" in potential_faculty_missing and potential_l23 >= level23_req:
             del potential_faculty_missing["level_2_and_3_credits"]
         if "outofmajor_credits" in potential_faculty_missing and outofmajor_required and potential_oom >= fac_min_outofmajor:
             del potential_faculty_missing["outofmajor_credits"]
         if "research_linked_course" in potential_faculty_missing and potential_research_completed:
             del potential_faculty_missing["research_linked_course"]
         if "language_requirement" in potential_faculty_missing and potential_language_completed:
             del potential_faculty_missing["language_requirement"]
         # Assume foundation still missing if initially missing

         potential_faculty_passes = len(potential_faculty_missing) == 0


    # --- MAJOR POTENTIAL CHECK ---
    potential_major_passes = major_result["passes_major"] # Start with current status
    potential_major_missing_blocks = [] # Stores blocks still missing requirements

    if not potential_major_passes:
         in_progress_major_codes = major_result.get("potential_courses", {}).get("codes", set())
         all_blocks_potentially_pass = True

         for block in major_result["blocks"]:
             if not block["passes"]:
                 block_potential_missing = copy.deepcopy(block["missing"])
                 block_name = block["block_name"]

                 # Check potential credits
                 potential_block_earned = block["earned_credits_in_block"] + block["potential_credits_in_block"]
                 if "credits" in block_potential_missing and potential_block_earned >= block["required_credits"]:
                     del block_potential_missing["credits"]

                 # Check potential required courses
                 if "required_courses" in block_potential_missing:
                     still_missing_req = []
                     currently_missing_reqs = block_potential_missing["required_courses"]
                     for req_course in currently_missing_reqs:
                          if req_course in in_progress_major_codes:
                              # Mark this course as potentially fulfilling major req
                              if req_course not in potential_fulfillment_map: potential_fulfillment_map[req_course] = []
                              potential_fulfillment_map[req_course].append(f"Major: Required Course for Block '{block_name}'")
                          else:
                              still_missing_req.append(req_course) # Still missing even with in-progress

                     if not still_missing_req:
                          del block_potential_missing["required_courses"] # All potentially met
                     else:
                          block_potential_missing["required_courses"] = still_missing_req # Update list

                 # If block still has missing items, add to report
                 if block_potential_missing:
                      all_blocks_potentially_pass = False
                      potential_major_missing_blocks.append({
                          "block_name": block_name,
                          "missing": block_potential_missing
                      })

         potential_major_passes = all_blocks_potentially_pass


    # --- MINOR POTENTIAL CHECK ---
    potential_minor_passes = None # Null if no minor
    potential_minor_missing = {}  # Stores requirements still missing after potential check

    if minor_result: # Only check if a minor exists
        potential_minor_passes = minor_result["passes_minor"] # Start with current status

        if not potential_minor_passes:
            # Get requirements
            minor_reqs = minor_schema.get("requirements", {})
            min_total_l2_l3 = minor_reqs.get("min_total_credits_l2_l3", 0)
            required_courses_set = set(minor_reqs.get("required_courses", [])) # L2/L3 required
            electives_req = minor_reqs.get("electives", {})
            min_elective_credits = electives_req.get("min_credits", 0)
            excluded_courses_set = set(electives_req.get("excluded_courses", [])) # Needed

            # Get current status and potential courses from minor check
            current_missing = minor_result["missing_requirements"]
            # *** UPDATED KEY ACCESS: Use _l2_l3 keys ***
            earned_elective_credits = minor_result.get("earned_elective_credits_l2_l3", 0.0)
            earned_total_credits = minor_result.get("earned_total_credits_l2_l3", 0.0)
            potential_courses_for_minor = minor_result.get("potential_minor_courses", [])
            # *** UPDATED KEY ACCESS: Check for specific L2/L3 required missing key ***
            currently_missing_required_l2l3 = set(current_missing.get("level_2_3_required_courses", []))

            # Start with current missing, try to resolve with potential
            potential_minor_missing = copy.deepcopy(current_missing)
            potential_elective_gain = 0.0
            potential_required_gain_credits = 0.0
            potentially_met_required_codes = set()

            # Check potential courses
            for p_course in potential_courses_for_minor:
                code = p_course["code"]
                credits = p_course["credits"]
                is_potential_required = code in required_courses_set # Is it an L2/L3 required course?

                # Check if it fulfills a missing L2/L3 required course
                # *** UPDATED KEY ACCESS: Check against L2/L3 missing set ***
                if "level_2_3_required_courses" in potential_minor_missing and code in currently_missing_required_l2l3:
                    potentially_met_required_codes.add(code)
                    potential_required_gain_credits += credits # Assume it contributes to total L2/L3 credits
                    if code not in potential_fulfillment_map: potential_fulfillment_map[code] = []
                    potential_fulfillment_map[code].append(f"Minor ({minor_schema.get('minor')}): L2/L3 Required Course")
                    potential_fulfillment_map[code].append(f"Minor ({minor_schema.get('minor')}): Total L2/L3 Credit ({credits:.1f})")

                # Check if it's a valid potential elective (and not a required L2/L3 course)
                elif not is_potential_required and code not in excluded_courses_set:
                     potential_elective_gain += credits
                     if code not in potential_fulfillment_map: potential_fulfillment_map[code] = []
                     potential_fulfillment_map[code].append(f"Minor ({minor_schema.get('minor')}): L2/L3 Elective Credit ({credits:.1f})")
                     potential_fulfillment_map[code].append(f"Minor ({minor_schema.get('minor')}): Total L2/L3 Credit ({credits:.1f})")

            # Update missing list for L2/L3 required courses
            # *** UPDATED KEY ACCESS ***
            if "level_2_3_required_courses" in potential_minor_missing:
                still_missing_req_minor = [c for c in currently_missing_required_l2l3 if c not in potentially_met_required_codes]
                if not still_missing_req_minor:
                    del potential_minor_missing["level_2_3_required_courses"]
                else:
                    potential_minor_missing["level_2_3_required_courses"] = still_missing_req_minor

            # Check potential elective credits
            potential_total_elective = earned_elective_credits + potential_elective_gain
            # *** UPDATED KEY ACCESS ***
            if "elective_credits_l2_l3" in potential_minor_missing and potential_total_elective >= min_elective_credits:
                del potential_minor_missing["elective_credits_l2_l3"]

            # Check potential total L2/L3 credits
            potential_total_minor = earned_total_credits + potential_required_gain_credits + potential_elective_gain
            if "total_minor_credits_l2_l3" in potential_minor_missing and potential_total_minor >= min_total_l2_l3:
                del potential_minor_missing["total_minor_credits_l2_l3"]

            # Also check if L1 requirements are still missing (if they were defined)
            if "level_1_required_courses" in potential_minor_missing:
                # L1 courses are either done or not, in-progress doesn't apply to L1 check here usually
                pass # Keep the missing L1 key if it exists

            potential_minor_passes = len(potential_minor_missing) == 0


    # --- FINAL POTENTIAL STATUS ---
    potential_graduate = potential_faculty_passes and potential_major_passes
    potential_all_requirements_satisfied = potential_graduate
    if minor_schema:
        potential_all_requirements_satisfied = potential_graduate and potential_minor_passes

    # Get list of all in-progress codes for the report
    in_progress_codes_all = list(potential_fulfillment_map.keys())

    return {
        "potential_graduate": potential_graduate, # Faculty + Major only
        "potential_all_requirements_satisfied": potential_all_requirements_satisfied, # Including minor
        "potential_faculty_passes": potential_faculty_passes,
        "potential_faculty_missing": potential_faculty_missing,
        "potential_major_passes": potential_major_passes,
        "potential_major_missing_blocks": potential_major_missing_blocks,
        "potential_minor_passes": potential_minor_passes, # Will be None if no minor
        "potential_minor_missing": potential_minor_missing if minor_schema else None, # None if no minor
        "in_progress_courses": in_progress_codes_all,
        "potential_fulfillment_map": potential_fulfillment_map
    }


# -------------------------------------
# 7. Reporting Functions
# -------------------------------------

def print_report_header(faculty, major, major_code, minor=None):
    """Print a formatted report header."""
    print(f"\n{'='*80}")
    print(f"DEGREE REQUIREMENT ANALYSIS - {faculty} / {major} ({major_code})", end="")
    if minor:
        print(f" with {minor} Minor")
    else:
        print(" (No Minor)")
    print(f"{'='*80}")

def print_foundation_report(foundation_status):
    """Print a formatted report of foundation requirements."""
    print("\n--- Foundation Requirements ---")

    all_slots_satisfied = foundation_status.get("all_slots_satisfied", False)
    meets_total_credits = foundation_status.get("meets_total_credits", False)

    print(f"Status: {'✅ Met' if all_slots_satisfied and meets_total_credits else '❌ Not Met'}")

    # Use capped credits for reporting
    foundation_earned_display = foundation_status.get('foundation_earned_credits', 0)
    foundation_required_display = foundation_status.get('total_foundation_required', 0)

    if meets_total_credits:
        print(f"  Credits: ✅ {foundation_earned_display:.1f} / " +
              f"{foundation_required_display:.1f} required")
    else:
        print(f"  Credits: ❌ {foundation_earned_display:.1f} / " +
              f"{foundation_required_display:.1f} required")

    if all_slots_satisfied:
         print(f"  Slots:   ✅ All required slots satisfied")
    else:
         print(f"  Slots:   ❌ One or more required slots not satisfied")

    sub_used = foundation_status.get('substitutions_used', 0)
    sub_allowed = foundation_status.get('max_substitutions_allowed', 0)
    print(f"  Substitutions Used: {sub_used} / {sub_allowed} allowed")


    if foundation_status.get("excluded_courses_taken"):
        print("\n  ⚠️ Warning: Excluded foundation courses taken: " +
              ", ".join(foundation_status.get("excluded_courses_taken", [])))

    print("\n  Slot Details:")
    for i, slot in enumerate(foundation_status.get("slots_status", [])):
        status_text = "✅" if slot.get("satisfied_by") else "❌"
        category = slot.get("category", f"Slot {i+1}")

        if slot.get("satisfied_by"):
            by_what = f" Satisfied by {slot.get('course')} ({slot.get('satisfied_by')})"
        else:
            alternatives = ", ".join(slot.get("alternatives", []))
            by_what = f" Needs one of: {alternatives}"

        print(f"    {status_text} {category}:{by_what}")

def print_language_requirement_report(language_status):
    """Print a formatted report of language requirements."""
    if not language_status or not language_status.get("required"):
        return # Don't print if not required

    print("\n--- Language Requirement ---")

    if language_status.get("exempted", False):
        print(f"  Status: ✅ Exempted")
        print(f"    Reason: {language_status.get('exemption_reason', 'Not specified')}")
        alt_req = language_status.get('alternative_requirements')
        if alt_req:
            print(f"    Alternative requirements: {alt_req}")
    elif language_status.get("completed", False):
        print(f"  Status: ✅ Completed")
        print(f"    Course: {language_status.get('completed_course', 'Unknown')}")
    else:
        print(f"  Status: ❌ Not satisfied")
        allowed = language_status.get("allowed_courses", [])
        if allowed:
             print(f"    Acceptable courses: {', '.join(allowed)}")

def print_credit_summary(credits_earned, faculty_schema):
    """Print a formatted credit summary based on faculty requirements."""
    print("\n--- Faculty Credit Summary ---")
    credit_requirements = faculty_schema.get("credit_requirements", {})

    total_earned = credits_earned.get("total", 0)
    total_required = credit_requirements.get("total_credits", 0)
    print(f"  Total Credits:       {total_earned:.1f} / {total_required:.1f} " +
          ("✅" if total_earned >= total_required else "❌"))

    l1_reqs = credit_requirements.get("level_1", {})
    l1_earned = credits_earned.get("level_1", 0)
    l1_required = l1_reqs.get("min_credits", 0)
    print(f"  Level 1 Credits:     {l1_earned:.1f} / {l1_required:.1f} " +
          ("✅" if l1_earned >= l1_required else "❌"))

    l1f_earned = credits_earned.get("level_1_faculty", 0)
    l1f_required = l1_reqs.get("min_faculty_credits") # Can be None
    if l1f_required is not None: # Only print if requirement exists
        print(f"  Level 1 Fac Credits: {l1f_earned:.1f} / {l1f_required:.1f} " +
              ("✅" if l1f_earned >= l1f_required else "❌"))

    l23_reqs = credit_requirements.get("level_2_and_3", {})
    l23_earned = credits_earned.get("level_2_and_3", 0)
    l23_required = l23_reqs.get("min_credits", 0)
    print(f"  Level 2&3 Credits:   {l23_earned:.1f} / {l23_required:.1f} " +
          ("✅" if l23_earned >= l23_required else "❌"))

    # HE Specific Level 2/3 breakdown (Optional more detailed report)
    if faculty_schema.get("faculty_code") == "HE":
         # To report earned credits accurately here, need separate L2/L3 calculation
         # print(f"    Level 2 (HE): TODO / {l2_min_req:.1f} total, TODO / {l2f_min_req:.1f} faculty")
         # print(f"    Level 3 (HE): TODO / {l3_min_req:.1f} total, TODO / {l3f_min_req:.1f} faculty")
         pass

    # Out of Major Requirement
    oom_req = faculty_schema.get("special_requirements", {}).get("out_of_major", {})
    if oom_req.get("required", False):
        oom_earned = credits_earned.get("outofmajor_credits", 0)
        oom_required = oom_req.get("min_credits", 0)
        oom_major_code = faculty_schema.get("student_major_code", "Declared Major")
        print(f"  Out-of-Major Cr:   {oom_earned:.1f} / {oom_required:.1f} (outside {oom_major_code}) " +
              ("✅" if oom_earned >= oom_required else "❌"))

    # Research Requirement (just status, not credits)
    research_req = faculty_schema.get("special_requirements", {}).get("research_course", {})
    if research_req.get("required", False):
         research_completed = credits_earned.get("faculty_specific_status", {}).get("research_course_completed", False)
         print(f"  Research Course:     {'✅ Completed' if research_completed else '❌ Required'}")


def print_major_requirements_report(major_result):
    """Print a formatted report of major requirements."""
    print(f"\n--- Major Requirements ({major_result.get('major', 'Unknown')}) ---")

    if major_result.get("passes_major", False):
        print(f"  Status: ✅ All major requirements satisfied")
    else:
        print(f"  Status: ❌ Missing major requirements")

    print("\n  Major Block Details:")
    for block in major_result.get("blocks", []):
        status_text = "✅" if block.get("passes", False) else "❌"
        print(f"    {status_text} {block.get('block_name', 'Unknown Block')}:")
        print(f"      Credits: {block.get('earned_credits_in_block', 0):.1f} / {block.get('required_credits', 0):.1f} required")

        missing = block.get("missing", {})
        if missing.get("required_courses"):
            print(f"      Missing Required Courses: {', '.join(missing.get('required_courses', []))}")

        completed_req = block.get("completed_required_in_block", [])
        if completed_req:
             print(f"      Completed Required Courses: {', '.join(completed_req)}")

        if block.get("notes"):
            print(f"      Notes: {block.get('notes', '')}")

# Replace the existing print_minor_requirements_report function with this one:

def print_minor_requirements_report(minor_result):
    """Print a formatted report of minor requirements, including Level 1 if applicable."""
    if not minor_result:
        return

    print(f"\n--- Minor Requirements ({minor_result.get('minor', 'Unknown')}) ---")

    passes = minor_result.get("passes_minor", False)
    print(f"Overall Status: {'✅ Requirements Met' if passes else '❌ Requirements Not Met'}")

    # --- Print Level 1 Status (if checked) ---
    if minor_result.get("level_1_requirements_defined"):
        print("\n  Level 1 Required Courses:")
        passes_l1 = minor_result.get("passes_level_1", False)
        print(f"    Status: {'✅ Completed' if passes_l1 else '❌ Incomplete'}")
        completed_l1 = minor_result.get("completed_l1_required_courses", [])
        if completed_l1:
            print(f"      Completed: {', '.join(completed_l1)}")
        missing_l1 = minor_result.get("missing_requirements", {}).get("level_1_required_courses")
        if missing_l1:
            print(f"      Missing:   {', '.join(missing_l1)}")

    # --- Print Level 2/3 Status ---
    print("\n  Level 2 & 3 Credits/Courses:")
    earned_total = minor_result.get("earned_total_credits_l2_l3", 0)
    required_total = minor_result.get("required_total_credits_l2_l3", 0)
    print(f"    Total L2/L3 Credits: {earned_total:.1f} / {required_total:.1f} required " +
          ("✅" if earned_total >= required_total else ("❌" if passes is False and minor_result.get("missing_requirements", {}).get("total_minor_credits_l2_l3") else "" ))) # Show X only if this specific req failed

    earned_elective = minor_result.get("earned_elective_credits_l2_l3", 0)
    required_elective = minor_result.get("required_elective_credits_l2_l3", 0)
    print(f"    Elective Credits:    {earned_elective:.1f} / {required_elective:.1f} required " +
          ("✅" if earned_elective >= required_elective else ("❌" if passes is False and minor_result.get("missing_requirements", {}).get("elective_credits_l2_l3") else "" )))
    if earned_elective < required_elective:
         print(f"      Valid Electives Taken: {', '.join(minor_result.get('valid_l2_l3_electives_taken',[]))}")

    completed_l2l3_required = minor_result.get("completed_l2_l3_required_courses", [])
    missing_l2l3_required = minor_result.get("missing_requirements", {}).get("level_2_3_required_courses")

    if completed_l2l3_required or missing_l2l3_required: # Only print L2/L3 required section if applicable
         print(f"    Required L2/L3 Courses: {'✅ Completed' if not missing_l2l3_required else '❌ Missing'}")
         if completed_l2l3_required:
              print(f"      Completed: {', '.join(completed_l2l3_required)}")
         if missing_l2l3_required:
              print(f"      Missing:   {', '.join(missing_l2l3_required)}")


def print_potential_graduation_report(potential_graduation):
    """Print a formatted report of potential graduation status."""
    print(f"\n{'='*80}")
    print("POTENTIAL GRADUATION STATUS (If In-Progress Courses Pass)")
    print(f"{'='*80}")

    potential_graduate = potential_graduation.get("potential_graduate", False)
    potential_all_satisfied = potential_graduation.get("potential_all_requirements_satisfied", False)
    minor_exists = potential_graduation.get("potential_minor_passes") is not None

    if potential_graduate:
        print("✅ POTENTIALLY ELIGIBLE FOR GRADUATION (Faculty + Major Requirements Met)")
        if minor_exists:
            if potential_all_satisfied:
                print("   ✅ Minor requirements also potentially met.")
            else:
                print("   ❓ Minor requirements potentially STILL MISSING.")
    else:
        print("❌ POTENTIALLY INELIGIBLE FOR GRADUATION - Requirements Still Missing:")

        if not potential_graduation.get("potential_faculty_passes", True):
            print("\n  Faculty Requirements Potentially Missing:")
            missing = potential_graduation.get("potential_faculty_missing", {})
            if not missing: print("    (None identified - check logic)") # Should not happen if passes=False
            for key, value in missing.items():
                print(f"    - {key.replace('_', ' ').capitalize()}: {value}")

        if not potential_graduation.get("potential_major_passes", True):
            print("\n  Major Requirements Potentially Missing:")
            missing_blocks = potential_graduation.get("potential_major_missing_blocks", [])
            if not missing_blocks: print("    (None identified - check logic)") # Should not happen
            for block in missing_blocks:
                print(f"    Block: {block.get('block_name', 'Unknown')}")
                for m_key, m_val in block.get("missing", {}).items():
                    if m_key == "credits":
                        print(f"      - Credits: Still short {m_val:.1f}")
                    elif m_key == "required_courses":
                        print(f"      - Required Courses: Still missing {', '.join(m_val)}")

        if minor_exists and not potential_graduation.get("potential_minor_passes", True):
            print("\n  Minor Requirements Potentially Missing:")
            missing = potential_graduation.get("potential_minor_missing", {})
            if not missing: print("    (None identified - check logic)") # Should not happen
            for key, value in missing.items():
                if key == "required_courses":
                    print(f"    - Required Courses: Still need {', '.join(value)}")
                elif key == "elective_credits":
                    print(f"    - Elective Credits: Still need {value:.1f} more")
                elif key == "total_minor_credits_l2_l3":
                    print(f"    - Total Minor Credits: Still need {value:.1f} more")
                else:
                    print(f"    - {key.replace('_', ' ').capitalize()}: {value}")

    print("\n--- How In-Progress Courses Potentially Contribute ---")
    in_progress_list = potential_graduation.get("in_progress_courses", [])
    fulfillment_map = potential_graduation.get("potential_fulfillment_map", {})

    if not in_progress_list:
        print("  No courses currently in progress.")
    else:
        printed_count = 0
        for course_code in sorted(in_progress_list):
            contributions = fulfillment_map.get(course_code, [])
            if contributions:
                printed_count += 1
                print(f"  - {course_code}:")
                # Filter out duplicates if map contains same string multiple times
                unique_contributions = sorted(list(set(contributions)))
                for contribution in unique_contributions:
                    print(f"    * {contribution}")
        if printed_count == 0 and in_progress_list:
             print("  None of the in-progress courses appear to fulfill currently outstanding requirements.")


def print_final_status(result):
    """Print a formatted final status report that clearly separates graduation eligibility from minor completion."""
    print(f"\n{'='*80}")
    print("FINAL STATUS SUMMARY (Based on Completed Courses)")
    print(f"{'='*80}")

    # Graduation eligibility (Faculty + Major only)
    if result["eligible_for_graduation"]:
        print("✅ GRADUATION ELIGIBILITY: Met (Based on Faculty and Major requirements)")
    else:
        print("❌ GRADUATION ELIGIBILITY: Not Met")
        missing_reasons = []
        if not result["faculty_result"]["passes_faculty"]:
            missing_reasons.append("Faculty requirements incomplete")
        if not result["major_result"]["passes_major"]:
            missing_reasons.append("Major requirements incomplete")
        print(f"    Reason(s): {'; '.join(missing_reasons)}")

    # Minor status (if applicable)
    if result.get("minor_result"):
        minor_name = result["minor_result"].get("minor", "Unknown")
        if result["minor_result"]["passes_minor"]:
            print(f"✅ MINOR STATUS ({minor_name}): Met")
        else:
            print(f"❌ MINOR STATUS ({minor_name}): Not Met")

    # Overall Conclusion
    print("\n--- Overall ---")
    if result["eligible_for_graduation"]:
         if result["passes_all_requirements"]:
             print("  Eligible to graduate with all declared programs completed.")
         else: # Eligible but minor failed
             print("  Eligible to graduate (Faculty/Major met), but declared Minor requirements are incomplete.")
    else: # Not eligible for graduation
         print("  Not eligible for graduation due to incomplete Faculty and/or Major requirements.")


    print(f"{'='*80}")

# -------------------------------------
# 8. Run Analysis
# -------------------------------------
def run_analysis():
    # --- Configuration ---
    # Choose Faculty, Major, and Optional Minor
    current_faculty_schema = fst_schema_standardized # Options: fst_schema_standardized, fss_schema_standardized, fhe_schema_standardized
    current_major_schema = major_schema_comp    # Options: major_schema_comp, major_schema_swen (ensure faculty matches)
    current_minor_schema = minor_schema_math     # Options: minor_schema_mgmt or None
    student_major_code = "COMP"                   # Must match the major code in current_major_schema and faculty schema departments

    # Student Info (for potential exemptions, e.g., FSS language)
    student_info = {
        'is_native_english': True,         # Example
        'has_language_qualification': False, # Example: CSEC/CAPE pass
        'is_international': False          # Example
    }
    # --- End Configuration ---


    # Run the analysis
    print_report_header(
        current_faculty_schema.get("faculty_name", current_faculty_schema.get("faculty")),
        current_major_schema.get("major"),
        student_major_code,
        current_minor_schema.get("minor") if current_minor_schema else None
    )

    # 1. Check all requirements based on completed courses
    result = check_all_requirements(
        transcript_data,
        current_faculty_schema,
        current_major_schema,
        student_major_code,
        current_minor_schema,
        student_info
    )

    # 2. Print detailed reports for current status
    # Pass the specific student major code to the credit summary for context
    result['faculty_schema']['student_major_code'] = student_major_code
    print_credit_summary(result["faculty_result"]["credits_earned"], result["faculty_schema"])
    print_foundation_report(result["faculty_result"]["foundation_status"])
    print_language_requirement_report(result["faculty_result"].get("language_status")) # Handles None if not required
    print_major_requirements_report(result["major_result"])
    if current_minor_schema:
        print_minor_requirements_report(result["minor_result"])

    # 3. Check and report potential graduation status including in-progress courses
    potential_graduation = check_potential_graduation_standardized(result, student_info) # Pass result dict
    print_potential_graduation_report(potential_graduation)

    # 4. Print final summary status based on completed courses
    print_final_status(result)

# Run the analysis
if __name__ == "__main__":
    run_analysis()