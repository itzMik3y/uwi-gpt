import axios, { AxiosInstance, AxiosError } from 'axios';
import { moodleApi } from './moodleClient';

// Reuse base URL from moodle client
const BASE_URL = process.env.NEXT_PUBLIC_MOODLE_API_URL || 'http://localhost:8000';

// Create an Axios instance for academic endpoints
const academicClient: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  },
});

// Attach the auth token to each request
academicClient.interceptors.request.use(
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
      message: axiosErr.message,
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

export interface CreditCheckResponse {
  analysis: any;  // you can further type this per your schema
  reports: string;
}

/**
 * GET /academic/credit-check
 * Requires Authorization header, returns analysis + human-readable report
 */
export async function getCreditCheck(): Promise<CreditCheckResponse> {
  try {
    const { data } = await academicClient.get<CreditCheckResponse>('/academic/credit-check');
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
    const { data } = await academicClient.get<CourseDetail[]>('/academic/course', { params });
    return data;
  } catch (err) {
    throw normalizeError(err);
  }
}

// Export client and functions
export default {
  getCreditCheck,
  searchCourses,
};