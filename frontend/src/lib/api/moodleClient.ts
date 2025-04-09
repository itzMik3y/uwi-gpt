// src/lib/api/moodleClient.ts
import axios, { AxiosError, AxiosInstance, AxiosRequestConfig } from 'axios';
import { 
  MoodleData, 
  MoodleCourse, 
  MoodleCalendarEvent, 
  MoodleLoginRequest,
  MoodleLoginResponse,
  MoodleErrorResponse
} from '@/types/moodle';

// API error type definition
export interface ApiError {
  message: string;
  code?: string;
  status?: number;
  data?: unknown;
}

export class MoodleApiClient {
  private client: AxiosInstance;
  private baseUrl: string;
  private token: string | null = null;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
    this.client = axios.create({
      baseURL: baseUrl,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
    });

    // Add response interceptor for error handling
    this.client.interceptors.response.use(
      (response) => response,
      (error) => Promise.reject(this.normalizeError(error))
    );
  }

  /**
   * Set the auth token for future requests
   */
  public setToken(token: string): void {
    this.token = token;
    this.client.defaults.headers.common['Authorization'] = `Bearer ${token}`;
  }

  /**
   * Clear the auth token
   */
  public clearToken(): void {
    this.token = null;
    delete this.client.defaults.headers.common['Authorization'];
  }

  /**
   * Get the current auth token
   */
  public getToken(): string | null {
    return this.token;
  }

  /**
   * Log in to Moodle and get an auth token
   */
  public async login(credentials: MoodleLoginRequest): Promise<MoodleData> {
    try {
      // This endpoint both authenticates and returns data in one step
      const response = await this.client.post<MoodleData>(
        '/moodle/data', 
        {
          username: credentials.username,
          password: credentials.password
        }
      );
      
      // The response directly contains the user data, courses, and calendar events
      // Let's store the user email for authentication state
      if (response.data && response.data.user_info && response.data.user_info.email) {
        // We don't have a token in the response, but we can use the credentials
        // to indicate successful authentication
        this.token = 'authenticated'; // Pseudo-token
        console.log(response.data)
        localStorage.setItem('moodle_username', response.data.user_info.email);
        localStorage.setItem('moodle_password', credentials.password);
        localStorage.setItem('moodle_auth_state', 'authenticated');
      }
      
      return response.data;
    } catch (error) {
      throw this.normalizeError(error);
    }
  }
  
  public async getUserData(): Promise<MoodleData> {
    // Since our API returns all data at login, we would need to re-authenticate
    // to get fresh data. This is a design consideration - you might want to 
    // modify this based on your needs.
    if (!this.token) {
      throw new Error('Authentication required. Please log in first.');
    }
  
    // This implementation assumes your credentials are stored securely
    // and would re-fetch the data using the stored credentials
    const username = localStorage.getItem('moodle_username');
    const password = localStorage.getItem('moodle_password');
    
    if (!username || !password) {
      throw new Error('Credentials not found. Please log in again.');
    }
    
    return this.login({ username, password });
  }
  /**
   * Get list of user courses
   */
  public async getCourses(): Promise<MoodleCourse[]> {
    if (!this.token) {
      throw new Error('Authentication required. Please log in first.');
    }

    try {
      const response = await this.client.get<MoodleData>('/moodle/data');
      return response.data.courses.courses;
    } catch (error) {
      throw this.normalizeError(error);
    }
  }

  /**
   * Get calendar events for the user
   */
  public async getCalendarEvents(): Promise<MoodleCalendarEvent[]> {
    if (!this.token) {
      throw new Error('Authentication required. Please log in first.');
    }

    try {
      const response = await this.client.get<MoodleData>('/moodle/data');
      return response.data.calendar_events.events;
    } catch (error) {
      throw this.normalizeError(error);
    }
  }

  /**
   * Get course by ID
   */
  public async getCourseById(courseId: number): Promise<MoodleCourse | null> {
    try {
      const courses = await this.getCourses();
      return courses.find(course => course.id === courseId) || null;
    } catch (error) {
      throw this.normalizeError(error);
    }
  }

  /**
   * Normalize different error types into a consistent format
   */
  private normalizeError(error: unknown): ApiError {
    if (axios.isAxiosError(error)) {
      const axiosError = error as AxiosError<MoodleErrorResponse>;
      
      // Handle Moodle specific error format
      if (axiosError.response?.data?.error) {
        return {
          message: axiosError.response.data.error,
          code: axiosError.response.data.errorcode,
          status: axiosError.response?.status,
          data: axiosError.response?.data,
        };
      }
      
      return {
        message: axiosError.message || 'An error occurred with the API request',
        code: axiosError.code,
        status: axiosError.response?.status,
        data: axiosError.response?.data,
      };
    }
    
    if (error instanceof Error) {
      return {
        message: error.message,
      };
    }
    
    return {
      message: 'An unknown error occurred',
      data: error,
    };
  }

  /**
   * Custom API call to the Moodle Web Service
   */
  public async callMoodleFunction<T = any>(
    wsfunction: string, 
    params: Record<string, any> = {},
    config?: AxiosRequestConfig
  ): Promise<T> {
    if (!this.token) {
      throw new Error('Authentication required. Please log in first.');
    }

    try {
      const response = await this.client.post<T>(
        '/webservice/rest/server.php',
        null,
        {
          params: {
            wsfunction,
            moodlewsrestformat: 'json',
            wstoken: this.token,
            ...params
          },
          ...config
        }
      );
      return response.data;
    } catch (error) {
      throw this.normalizeError(error);
    }
  }
}

// Create and export a singleton instance
const MOODLE_API_URL = process.env.NEXT_PUBLIC_MOODLE_API_URL || 'http://localhost:8000';
export const moodleApi = new MoodleApiClient(MOODLE_API_URL);