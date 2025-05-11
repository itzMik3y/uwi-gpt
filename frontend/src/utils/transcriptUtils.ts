// src/lib/utils/transcriptUtils.ts

// Helper function (if not already globally available or imported from elsewhere)
const normalizeCourseCode = (code: string): string => {
  if (!code) return '';
  return code.replace(/\+$/, '');
};

// --- Paste the interfaces here ---
// interface ReconstructedTranscriptCourse { ... }
// interface ReconstructedTranscriptTerm { ... }
// interface StudentInfo { ... }
// interface FinalReconstructedTranscript { ... }

// --- Paste the helper function here ---
// function generateTermCodeForPlannedSemester(...) { ... }

// --- Paste the main reconstruction function here ---
// export function reconstructTranscriptWithDesiredStructure(...) { ... }
// Make sure to export it!

// Example of interfaces and functions (assuming they are all in this file)
export interface ReconstructedTranscriptCourse {
  course_code: string;
  course_title: string;
  credit_hours: number;
  grade_earned: string;
  whatif_grade: string;
}

export interface ReconstructedTranscriptTerm {
  term_code: string;
  courses: ReconstructedTranscriptCourse[];
  semester_gpa: number | null;
  cumulative_gpa: number | null;
  degree_gpa: number | null;
  credits_earned_to_date: number | null;
}

export interface StudentInfo {
  is_native_english: boolean;
  has_language_qualification: boolean;
  is_international: boolean;
}

export interface FinalReconstructedTranscript {
  terms: ReconstructedTranscriptTerm[];
  student_info: StudentInfo;
}

// Forward declare TranscriptData and YearPlanData if they are imported from elsewhere
// or define simplified versions here if they are complex and only specific fields are needed.
// For simplicity, assuming they are defined/imported where reconstructTranscriptWithDesiredStructure is used,
// or you can define them here based on the fields accessed.
// For this example, let's assume they are similar to how they were described.

export interface OriginalTranscriptData { // Simplified from TranscriptData for clarity
  terms: Array<{
    term_code: string;
    courses: Array<{
      course_code: string;
      course_title: string;
      credit_hours: number;
      grade_earned: string;
      whatif_grade: string;
    }>;
    semester_gpa: number | null;
    cumulative_gpa: number | null;
    degree_gpa: number | null;
    credits_earned_to_date: number | null;
  }>;
  overall?: { // Make overall optional as the new structure doesn't use it directly at root
    cumulative_gpa: number | null;
    degree_gpa: number | null;
    total_credits_earned: number | null;
  };
}

export interface OriginalCourseItem {
  id: string;
  code: string;
  title: string;
  credits: number;
  status: 'completed' | 'in-progress' | 'planned';
  // ... other fields if necessary
}

export interface OriginalYearPlanData {
  year: number;
  academicYear: string;
  semesters: Array<{
    id: string;
    number: number;
    status: 'completed' | 'in-progress' | 'planning';
    courses: OriginalCourseItem[];
  }>;
}


function generateTermCodeForPlannedSemester(
  academicYearStr: string,
  sequentialYearNum: number,
  semesterNumber: number
): string {
  if (academicYearStr && academicYearStr.includes('/') && academicYearStr.length >= 7) {
    const startYear = parseInt(academicYearStr.substring(0, 4));
    if (!isNaN(startYear)) {
      if (semesterNumber === 1) return `${startYear}10`;
      if (semesterNumber === 2) return `${startYear}20`;
      if (semesterNumber === 3) return `${startYear}30`;
    }
  }
  return `PLAN_Y${sequentialYearNum}_S${semesterNumber}`;
}

export function reconstructTranscriptWithDesiredStructure(
  originalTranscript: OriginalTranscriptData | null,
  yearPlan: OriginalYearPlanData[]
): FinalReconstructedTranscript {
  // ... (Paste the full function logic provided in the previous answer)
  // Ensure it uses the interfaces defined/imported in this file.
  const reconstructedTerms: ReconstructedTranscriptTerm[] = [];
  const termMapForProcessing = new Map<string, ReconstructedTranscriptTerm>();

  let lastActualCumulativeGpa: number | null = originalTranscript?.overall?.cumulative_gpa ?? null;
  let lastActualDegreeGpa: number | null = originalTranscript?.overall?.degree_gpa ?? null;
  let lastActualCreditsEarned: number | null = originalTranscript?.overall?.total_credits_earned ?? 0;

  if (originalTranscript && originalTranscript.terms) {
    const sortedOriginalTerms = [...originalTranscript.terms].sort((a, b) => {
        if (a.term_code === 'CURRENT' && b.term_code !== 'CURRENT') return 1;
        if (a.term_code !== 'CURRENT' && b.term_code === 'CURRENT') return -1;
        return (a.term_code || "").localeCompare(b.term_code || "");
    });

    sortedOriginalTerms.forEach(originalTermData => { // Renamed to avoid conflict
      const copiedTerm: ReconstructedTranscriptTerm = JSON.parse(JSON.stringify(originalTermData)); // Make sure this matches ReconstructedTranscriptTerm
      reconstructedTerms.push(copiedTerm);
      termMapForProcessing.set(copiedTerm.term_code, copiedTerm);

      if (originalTermData.cumulative_gpa !== null) lastActualCumulativeGpa = originalTermData.cumulative_gpa;
      if (originalTermData.degree_gpa !== null) lastActualDegreeGpa = originalTermData.degree_gpa;
      if (originalTermData.credits_earned_to_date !== null) lastActualCreditsEarned = originalTermData.credits_earned_to_date;
    });
  }

  yearPlan.forEach(yearEntry => {
    yearEntry.semesters.forEach(semesterInPlan => {
      const plannedCoursesInSemester = semesterInPlan.courses.filter(
        course => course.status === 'planned'
      );

      if (plannedCoursesInSemester.length > 0) {
        const termCode = generateTermCodeForPlannedSemester(
          yearEntry.academicYear,
          yearEntry.year,
          semesterInPlan.number
        );

        let termObject = termMapForProcessing.get(termCode);

        if (!termObject) {
          termObject = {
            term_code: termCode,
            courses: [],
            semester_gpa: null,
            cumulative_gpa: null, // To be filled later
            degree_gpa: null,     // To be filled later
            credits_earned_to_date: null, // To be filled later
          };
          reconstructedTerms.push(termObject);
          termMapForProcessing.set(termCode, termObject);
        }

        plannedCoursesInSemester.forEach(plannedCourse => {
          const courseAlreadyInTerm = termObject!.courses.some(
            existingCourse => normalizeCourseCode(existingCourse.course_code) === normalizeCourseCode(plannedCourse.code)
          );

          if (!courseAlreadyInTerm) {
            termObject!.courses.push({
              course_code: plannedCourse.code,
              course_title: plannedCourse.title,
              credit_hours: plannedCourse.credits,
              grade_earned: 'NA',
              whatif_grade: 'NA',
            });
          }
        });
      }
    });
  });

  reconstructedTerms.sort((a, b) => {
    const isAPlan = a.term_code.startsWith('PLAN_');
    const isBPlan = b.term_code.startsWith('PLAN_');
    const isACurrent = a.term_code === 'CURRENT';
    const isBCurrent = b.term_code === 'CURRENT';

    if (isACurrent && !isBCurrent) return 1;
    if (!isACurrent && isBCurrent) return -1;
    if (isACurrent && isBCurrent) return 0;

    if (isAPlan && !isBPlan) return 1;
    if (!isAPlan && isBPlan) return -1;
    return a.term_code.localeCompare(b.term_code);
  });

  let runningCumulativeGpa = originalTranscript?.overall?.cumulative_gpa ?? null;
  let runningDegreeGpa = originalTranscript?.overall?.degree_gpa ?? null;
  let runningCreditsEarned = originalTranscript?.overall?.total_credits_earned ?? 0;

  reconstructedTerms.forEach(term => {
    const originalTermDataSource = originalTranscript?.terms.find(ot => ot.term_code === term.term_code);
    const hasActualData = originalTermDataSource && originalTermDataSource.semester_gpa !== null;

    if (hasActualData) {
      runningCumulativeGpa = originalTermDataSource.cumulative_gpa;
      runningDegreeGpa = originalTermDataSource.degree_gpa;
      runningCreditsEarned = originalTermDataSource.credits_earned_to_date;
      
      term.cumulative_gpa = runningCumulativeGpa;
      term.degree_gpa = runningDegreeGpa;
      term.credits_earned_to_date = runningCreditsEarned;
      term.semester_gpa = originalTermDataSource.semester_gpa;
    } else {
      if (!originalTermDataSource || originalTermDataSource.semester_gpa === null) {
          term.semester_gpa = null;
      }
      term.cumulative_gpa = runningCumulativeGpa;
      term.degree_gpa = runningDegreeGpa;
      term.credits_earned_to_date = runningCreditsEarned;
    }
  });

  const student_info: StudentInfo = {
    is_native_english: true,
    has_language_qualification: false,
    is_international: false,
  };

  return {
    terms: reconstructedTerms,
    student_info,
  };
}