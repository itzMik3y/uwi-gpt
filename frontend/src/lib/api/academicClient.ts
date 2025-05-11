import axios, { AxiosInstance, AxiosError } from 'axios';
import { moodleApi } from './moodleClient';

// Reuse base URL from moodle client
const BASE_URL = process.env.NEXT_PUBLIC_MOODLE_API_URL || 'http://localhost:8000';

// Create an Axios instance for academic endpoints
const academicApiClient: AxiosInstance = axios.create({ // Renamed to avoid conflict if 'academicClient' is the default export object
  baseURL: BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  },
});

// Attach the auth token to each request
academicApiClient.interceptors.request.use(
  (config) => {
    const token = moodleApi.getAccessToken();
    if (token) {
      config.headers = config.headers || {};
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Generic error type
export interface ApiError {
  message: string;
  code?: string;
  status?: number;
  data?: unknown;
}

function normalizeError(error: unknown): ApiError {
  if (axios.isAxiosError(error)) {
    const axiosErr = error as AxiosError;
    return {
      message: (axiosErr.response?.data as any)?.detail || axiosErr.message, // Try to get detail from FastAPI error
      status: axiosErr.response?.status,
      data: axiosErr.response?.data,
    };
  }
  if (error instanceof Error) {
    return { message: error.message };
  }
  return { message: 'Unknown error', data: error };
}

// Response types (partial definitions based on sample)
export interface Prerequisite {
  and_or: string | null;
  subject: string;
  number: string;
  course_code: string;
  level: string;
  grade: string;
}

export interface CourseDetail {
  ban_id: number;
  term_effective: string;
  subject_code: string;
  course_number: string;
  course_code: string;
  college: string;
  department: string;
  course_title: string;
  credit_hour_low: number;
  credit_hour_high: number;
  prerequisites: Prerequisite[];
}

// Interface for the payload of the new POST request for transcript check
// This should match the Pydantic models on the backend (UserTranscriptInput)
export interface UserCourseInput {
  course_code: string;
  course_title: string;
  credit_hours: number;
  grade_earned: string; // "NA" for planned/in-progress for this check
  whatif_grade?: string | null;
}

export interface UserTermInput {
  term_code: string;
  courses: UserCourseInput[];
  semester_gpa: number | null;
  cumulative_gpa: number | null;
  degree_gpa?: number | null;
  credits_earned_to_date: number | null;
}

export interface PlannedTranscriptPayload {
  terms: UserTermInput[];
  student_info?: Record<string, any> | null;
}


export interface CreditCheckResponse { // Assuming this interface is already defined from your previous context
  analysis: any;
  reports: string;
}

/**
 * GET /academic/credit-check
 * Requires Authorization header, returns analysis + human-readable report
 */
export async function getCreditCheck(): Promise<CreditCheckResponse> {
  try {
    const { data } = await academicApiClient.get<CreditCheckResponse>('/academic/credit-check');
    return data;
  } catch (err) {
    throw normalizeError(err);
  }
}

/**
 * GET /academic/course?q=... (fuzzy search)
 * Returns list of courses matching the query
 */
export async function searchCourses(
  params: { q?: string; course_code?: string; course_title?: string }
): Promise<CourseDetail[]> {
  try {
    const { data } = await academicApiClient.get<CourseDetail[]>('/academic/course', { params });
    return data;
  } catch (err) {
    throw normalizeError(err);
  }
}

/**
 * POST /academic/credit-check-transcript
 * Requires Authorization header, accepts a transcript payload,
 * returns analysis + human-readable report for the provided transcript.
 */
export async function getCreditCheckWithTranscript(
  payload: PlannedTranscriptPayload
): Promise<CreditCheckResponse> {
  try {
    const { data } = await academicApiClient.post<CreditCheckResponse>(
      '/academic/credit-check-transcript',
      payload
    );
    return data;
  } catch (err) {
    throw normalizeError(err);
  }
}


// Export client and functions
const academicClient = { // Changed this to match the import in page.tsx
  getCreditCheck,
  searchCourses,
  getCreditCheckWithTranscript, // Add the new function
};

export default academicClient;