"""
This module defines prompt templates for a RAG-based QA system.
It includes explicit instructions to handle messy markdown formatting
in the retrieved context, as well as specialized templates for general,
credit/requirement, and course-specific queries.
Includes placeholders for user context information and grade/level interpretation rules.
"""
import logging
# Import necessary module from LangChain (if using PromptTemplate)
try:
    from langchain.prompts import PromptTemplate
except ImportError:
    PromptTemplate = None
    logging.warning("Langchain not installed. Prompts will be treated as basic f-strings.")

# --- Base Instructions (Common to all) ---
BASE_INSTRUCTIONS = """
You are a highly knowledgeable university AI assistant (UWI Mona). Your answers must be strictly grounded in the provided context and must not include any external information. Follow these principles:
1.  **Strict Grounding:** Use only the data in the retrieved documents (Context section below). Do not add information not present.
2.  **Citation:** Cite the source filename(s) immediately after the relevant information using HTML bold tags, e.g., [<b>syllabus.pdf</b>] or [<b>catalog.pdf</b>, <b>handbook.doc</b>].
3.  **Output Formatting:** Structure answers clearly. If tabular data is most appropriate, generate a neat HTML table using `<table>`, `<thead>`, `<tbody>`, `<tr>`, `<th>`, and `<td>`. Otherwise, use Markdown syntax (e.g., `##`/`###` for headings, `-` for lists, `**` for bold) for readability.
4.  **Interpret Messy Context:** If context has formatting errors (markdown symbols, inconsistent structure), focus on extracting the factual content and present it accurately in clean HTML or Markdown as instructed.
5.  **Handle Missing Info:** If context is insufficient or ambiguous, state clearly what cannot be confirmed from the provided documents.
6.  **Grade & Level Rules:** Only the grades A+, A, A-, B+, B, B-, C+, and C are considered passing. Course level is defined by the first digit of the course code (e.g., in COMP3901 and COMP3161, the first digit "3" indicates level 3).
"""

# --- User Context Injection (extended with full grade history) ---
USER_CONTEXT_INSTRUCTIONS = """

**User Information:**
The query is coming from the following student:
- Name: {user_name}
- Student ID: {student_id}
- Current Courses Summary: {user_courses_summary}
- Latest Recorded Cumulative GPA: {user_gpa}
- Full Grade History (JSON): {grade_history_json}

**Grade & Level Interpretation Rules:**
- Passing grades: A+, A, A-, B+, B, B-, C+, C.
- A course is considered passed if its grade is one of the passing grades.
- Course level is the first digit of the course code (e.g., COMP3901 → level 3).

Tailor your response appropriately for this student, using these rules when interpreting the grade history and course codes.
"""

# --- Note on Context Formatting ---
MARKDOWN_INSTRUCTIONS = """
**Note on Context Formatting:**
The Context below may include markdown formatting. Interpret the intended content and present your answer in clean HTML or Markdown as instructed above. Disregard stray markdown symbols.
"""

# --- Specific Prompt Template Strings ---
DEFAULT_PROMPT_TEMPLATE_STR = (
    BASE_INSTRUCTIONS +
    USER_CONTEXT_INSTRUCTIONS +
    MARKDOWN_INSTRUCTIONS +
    """
**Context:**
{context}

**Question:**
{question}

**Answer (use HTML tables or Markdown as appropriate):**
"""
)

CREDIT_PROMPT_TEMPLATE_STR = (
    BASE_INSTRUCTIONS +
    USER_CONTEXT_INSTRUCTIONS +
    MARKDOWN_INSTRUCTIONS +
    """
**Context:**
{context}

**Question:**
{question}

**Instructions for Credit/Requirement Queries:**
- Focus on precise details: prerequisites, credits, levels, eligibility, policies.
- If presenting multiple requirements or course attributes, display them in a neat HTML table. Otherwise, use Markdown lists or paragraphs.
- Cite each factual detail using HTML bold tags for the source filename.
- State clearly if details are missing from the context.

**Answer (use HTML tables or Markdown as appropriate):**
"""
)

COURSE_PROMPT_TEMPLATE_STR = (
    BASE_INSTRUCTIONS +
    USER_CONTEXT_INSTRUCTIONS +
    MARKDOWN_INSTRUCTIONS +
    """
You are answering a question about a specific course.
**Context:**
{context}

**Question:**
{question}

**Instructions for Course Queries:**
- Identify the specific course from the question.
- Use only relevant context portions for that course.
- Extract details: Code, Title, Credits, Prerequisites (or Co/Anti-requisites), Level, Semester, Description/Topics.
- If comparing multiple courses or aspects, present them in an HTML table; otherwise, use Markdown headings and lists.
- Cite each detail using HTML bold tags for the source filename.
- State clearly if details are missing from the context.

**Answer (use HTML tables or Markdown as appropriate):**
"""
)

# --- Create PromptTemplate Objects (if LangChain is available) ---
# Ensure input_variables list includes the new user context keys

# Define the set of input variables expected by the templates
prompt_input_variables = [
    "context", "question",
    "user_name", "student_id",
    "user_courses_summary", "user_gpa",
    "grade_history_json"
]

if PromptTemplate:
    try:
        DEFAULT_PROMPT = PromptTemplate(
            input_variables=prompt_input_variables,
            template=DEFAULT_PROMPT_TEMPLATE_STR
        )
        CREDIT_PROMPT = PromptTemplate(
            input_variables=prompt_input_variables,
            template=CREDIT_PROMPT_TEMPLATE_STR
        )
        COURSE_PROMPT = PromptTemplate(
            input_variables=prompt_input_variables,
            template=COURSE_PROMPT_TEMPLATE_STR
        )
    except Exception as e:
        logging.error(f"Failed to create LangChain PromptTemplate objects: {e}. Falling back to strings.", exc_info=True)
        DEFAULT_PROMPT = DEFAULT_PROMPT_TEMPLATE_STR
        CREDIT_PROMPT = CREDIT_PROMPT_TEMPLATE_STR
        COURSE_PROMPT = COURSE_PROMPT_TEMPLATE_STR
else:
    DEFAULT_PROMPT = DEFAULT_PROMPT_TEMPLATE_STR
    CREDIT_PROMPT = CREDIT_PROMPT_TEMPLATE_STR
    COURSE_PROMPT = COURSE_PROMPT_TEMPLATE_STR

# --- Function to Return Prompts ---
def get_prompts_dict():
    """
    Returns a dictionary of available prompt templates (either PromptTemplate objects or strings).
    """
    prompts = {
        "default_prompt": DEFAULT_PROMPT,
        "credit_prompt": CREDIT_PROMPT,
        "course_prompt": COURSE_PROMPT,
    }
    if "default_prompt" not in prompts or not prompts["default_prompt"]:
         prompts["default_prompt"] = DEFAULT_PROMPT_TEMPLATE_STR
         logging.warning("Default prompt was missing or invalid, using basic string.")
    return prompts

__all__ = [
    "DEFAULT_PROMPT",
    "CREDIT_PROMPT",
    "COURSE_PROMPT",
    "get_prompts_dict",
    "DEFAULT_PROMPT_TEMPLATE_STR",
    "CREDIT_PROMPT_TEMPLATE_STR",
    "COURSE_PROMPT_TEMPLATE_STR",
]