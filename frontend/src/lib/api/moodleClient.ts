// src/lib/api/moodleClient.ts
import axios, { AxiosError, AxiosInstance, AxiosRequestConfig } from 'axios';
import {
  MoodleData,
  MoodleCourse,
  MoodleCalendarEvent,
  MoodleLoginRequest,
  CombinedLoginResponse,
  MoodleErrorResponse,
  AuthResponse,
  UnbookResponse,
} from '@/types/moodle';
import { StudentBooking } from '@/types/moodle';


// Token storage keys
export const TOKEN_STORAGE_KEY = 'uwi_access_token';
export const REFRESH_TOKEN_STORAGE_KEY = 'uwi_refresh_token';
export const TOKEN_EXPIRY_KEY = 'uwi_token_expiry';

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
  private accessToken: string | null = null;
  private refreshToken: string | null = null;
  private tokenExpiry: number | null = null;

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

    // Initialize from localStorage if available (client-side only)
    if (typeof window !== 'undefined') {
      this.loadTokensFromStorage();
    }

    // Add request interceptor to handle token expiry
    this.client.interceptors.request.use(
      async (config) => {
        // If token is about to expire, try to refresh it
        if (this.shouldRefreshToken()) {
          await this.refreshAccessToken();
        }
        
        // Add the token to the request if available
        if (this.accessToken) {
          config.headers['Authorization'] = `Bearer ${this.accessToken}`;
        }
        
        return config;
      },
      (error) => Promise.reject(error)
    );

    // Add response interceptor for error handling
    this.client.interceptors.response.use(
      (response) => response,
      async (error) => {
        const originalRequest = error.config;
        
        // Handle 401 errors by refreshing token and retrying (if not already retried)
        if (error.response?.status === 401 && !originalRequest._retry && this.refreshToken) {
          originalRequest._retry = true;
          
          try {
            await this.refreshAccessToken();
            
            // Update the Authorization header and retry
            originalRequest.headers['Authorization'] = `Bearer ${this.accessToken}`;
            return this.client(originalRequest);
          } catch (refreshError) {
            // If refresh fails, clear tokens and reject
            this.clearTokens();
            return Promise.reject(this.normalizeError(refreshError));
          }
        }
        
        return Promise.reject(this.normalizeError(error));
      }
    );
  }

  /**
   * Load tokens from localStorage (client-side only)
   */
  private loadTokensFromStorage(): void {
    this.accessToken = localStorage.getItem(TOKEN_STORAGE_KEY);
    this.refreshToken = localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY);
    const expiryStr = localStorage.getItem(TOKEN_EXPIRY_KEY);
    this.tokenExpiry = expiryStr ? parseInt(expiryStr, 10) : null;
  }

  /**
   * Save tokens to localStorage (client-side only)
   */
  private saveTokensToStorage(): void {
    if (typeof window === 'undefined') return;
    
    if (this.accessToken) {
      localStorage.setItem(TOKEN_STORAGE_KEY, this.accessToken);
    } else {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
    }
    
    if (this.refreshToken) {
      localStorage.setItem(REFRESH_TOKEN_STORAGE_KEY, this.refreshToken);
    } else {
      localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY);
    }
    
    if (this.tokenExpiry) {
      localStorage.setItem(TOKEN_EXPIRY_KEY, this.tokenExpiry.toString());
    } else {
      localStorage.removeItem(TOKEN_EXPIRY_KEY);
    }
  }

  /**
   * Check if token should be refreshed (less than 5 minutes remaining)
   */
  private shouldRefreshToken(): boolean {
    if (!this.accessToken || !this.tokenExpiry) return false;
    
    // Refresh if less than 5 minutes remaining
    const fiveMinutesInMs = 5 * 60 * 1000;
    return Date.now() + fiveMinutesInMs > this.tokenExpiry;
  }

  /**
   * Refresh the access token using the refresh token
   */
  private async refreshAccessToken(): Promise<void> {
    if (!this.refreshToken) {
      throw new Error('No refresh token available');
    }
    
    try {
      // Call the refresh token endpoint
      const response = await axios.post<AuthResponse>(
        `${this.baseUrl}/auth/refresh`,
        { refresh_token: this.refreshToken }
      );
      
      // Update tokens with new values
      this.setTokensFromResponse(response.data);
    } catch (error) {
      // If refresh fails, clear tokens
      this.clearTokens();
      throw error;
    }
  }

  /**
   * Set tokens from auth response
   */
  private setTokensFromResponse(authResponse: AuthResponse): void {
    this.accessToken = authResponse.access_token;
    this.refreshToken = authResponse.refresh_token;
    this.tokenExpiry = authResponse.expires_at * 1000; // Convert to milliseconds
    
    this.saveTokensToStorage();
  }

  /**
   * Set the auth token for future requests
   */
  public setTokens(accessToken: string, refreshToken: string, expiresAt: number): void {
    this.accessToken = accessToken;
    this.refreshToken = refreshToken;
    this.tokenExpiry = expiresAt * 1000; // Convert to milliseconds
    
    this.saveTokensToStorage();
  }

  /**
   * Clear all tokens
   */
  public clearTokens(): void {
    this.accessToken = null;
    this.refreshToken = null;
    this.tokenExpiry = null;
    
    if (typeof window !== 'undefined') {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
      localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY);
      localStorage.removeItem(TOKEN_EXPIRY_KEY);
    }
  }

  /**
   * Get the current auth token
   */
  public getAccessToken(): string | null {
    return this.accessToken;
  }

  /**
   * Check if user is authenticated
   */
  public isAuthenticated(): boolean {
    return !!this.accessToken && !!this.tokenExpiry && Date.now() < this.tokenExpiry;
  }

  /**
   * Log in to Moodle and get an auth token
   */
  public async login(
    credentials: MoodleLoginRequest
  ): Promise<AuthResponse> {
    const response = await this.client.post<AuthResponse>(
      '/auth/token',
      {
        username: credentials.username,
        password: credentials.password,
      }
    );

    // Store tokens
    this.setTokensFromResponse(response.data);
    
    return response.data;
  }

  /**
   * Get user data from /auth/me endpoint
   */
  public async getUserData(): Promise<CombinedLoginResponse> {
    if (!this.isAuthenticated()) {
      throw new Error('Authentication required. Please log in first.');
    }

    try {
      const response = await this.client.get<CombinedLoginResponse>('/auth/me');
      return response.data;
    } catch (error) {
      throw this.normalizeError(error);
    }
  }

  /**
   * Get list of user courses
   */
  public async getCourses(): Promise<MoodleCourse[]> {
    if (!this.isAuthenticated()) {
      throw new Error('Authentication required. Please log in first.');
    }

    try {
      const response = await this.getUserData();
      return response.moodle_data.courses.courses;
    } catch (error) {
      throw this.normalizeError(error);
    }
  }

  /**
   * Get calendar events for the user
   */
  public async getCalendarEvents(): Promise<MoodleCalendarEvent[]> {
    if (!this.isAuthenticated()) {
      throw new Error('Authentication required. Please log in first.');
    }

    try {
      const response = await this.getUserData();
      return response.moodle_data.calendar_events.events;
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
   * Get available appointment slots
   */
  public async getAvailableSlots(): Promise<any[]> {
    if (!this.isAuthenticated()) {
      throw new Error('Authentication required. Please log in first.');
    }

    try {
      const response = await this.client.get<any[]>(
        '/moodle/scheduler/slots/available'
      );
      return response.data;
    } catch (error) {
      throw this.normalizeError(error);
    }
  }

  /**
   * Book an appointment slot
   */
  public async bookSlot(slotId: number): Promise<any> {
    if (!this.isAuthenticated()) {
      throw new Error('Authentication required. Please log in first.');
    }

    try {
      const response = await this.client.post(
        '/moodle/scheduler/bookings',
        { slot_id: slotId }
      );
      return response.data;
    } catch (error) {
      throw this.normalizeError(error);
    }
  }

  /**
   * Get the current student's bookings
   */
  public async getStudentBookings(): Promise<StudentBooking[]> {
    if (!this.isAuthenticated()) {
      throw new Error('Authentication required. Please log in first.');
    }

    try {
      const response = await this.client.get<StudentBooking[]>(
        '/moodle/scheduler/bookings/student'
      );
      return response.data;
    } catch (error) {
      throw this.normalizeError(error);
    }
  }
  /**
 * Cancel a booking
 */
// src/lib/api/moodleClient.ts
public async cancelBooking(slotId: number): Promise<UnbookResponse> {
  if (!this.isAuthenticated()) {
    throw new Error("Authentication required");
  }
  // DELETE /moodle/scheduler/bookings/{slotId}
  const response = await this.client.delete<UnbookResponse>(
    `/moodle/scheduler/bookings/${slotId}`
  );
  return response.data;
}
public async deleteAccount(): Promise<void> {
  if (!this.isAuthenticated()) {
    throw new Error('Authentication required. Please log in first.');
  }

  try {
    await this.client.delete('/auth/account/delete');
    // If the DELETE request is successful (204 No Content),
    // the user's session and account are gone from the backend.
    // Clear local tokens as well.
    this.clearTokens();
  } catch (error) {
    // The error interceptor will handle 401s by trying to refresh.
    // If refresh fails or it's another error, it will be thrown.
    // If delete itself fails (e.g., 500), tokens might still be locally valid,
    // but the account deletion failed. The error will be propagated.
    throw this.normalizeError(error);
  }
}

}

// Create and export a singleton instance
const MOODLE_API_URL = process.env.NEXT_PUBLIC_MOODLE_API_URL || 'http://localhost:8000';
export const moodleApi = new MoodleApiClient(MOODLE_API_URL);