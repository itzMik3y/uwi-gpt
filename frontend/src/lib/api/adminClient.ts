// src/lib/api/adminClient.ts
import axios, { AxiosError, AxiosInstance } from 'axios';
import { 
  AdminLoginRequest, 
  AdminAuthResponse, 
  AdminDataResponse,
  CreateSlotsRequest,
  AdminSlotWithBooking
} from '@/types/admin';
import { AdminBookingWithStudent } from '@/types/admin';
// Token storage keys
export const ADMIN_TOKEN_STORAGE_KEY = 'uwi_admin_access_token';
export const ADMIN_REFRESH_TOKEN_STORAGE_KEY = 'uwi_admin_refresh_token';
export const ADMIN_TOKEN_EXPIRY_KEY = 'uwi_admin_token_expiry';

// API error type definition
export interface ApiError {
  message: string;
  code?: string;
  status?: number;
  data?: unknown;
}

export class AdminApiClient {
  private client: AxiosInstance;
  private baseUrl: string;
  private accessToken: string | null = null;
  private refreshToken: string | null = null;
  private tokenExpiry: number | null = null;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
    
    // Debug the baseUrl to ensure it's correct
    console.log('AdminApiClient initialized with baseUrl:', baseUrl);
    
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
      
      // Debug loaded tokens
      const hasAccessToken = !!this.accessToken;
      const hasRefreshToken = !!this.refreshToken;
      console.log('Tokens loaded from storage:', { 
        hasAccessToken, 
        hasRefreshToken,
        tokenExpiry: this.tokenExpiry,
        isAuthenticated: this.isAuthenticated()
      });
    }

    // Add request interceptor to handle token expiry and debug
    this.client.interceptors.request.use(
      async (config) => {
        console.log(`Request to ${config.url} initiated`);
        
        // If token is about to expire, try to refresh it
        if (this.shouldRefreshToken()) {
          console.log('Token expiring soon, attempting refresh');
          await this.refreshAccessToken();
        }
        
        // Add the token to the request if available
        if (this.accessToken) {
          config.headers['Authorization'] = `Bearer ${this.accessToken}`;
          console.log('Added Authorization header to request');
        } else {
          console.log('No access token available for request');
        }
        
        return config;
      },
      (error) => {
        console.error('Request interceptor error:', error);
        return Promise.reject(error);
      }
    );

    // Add response interceptor for error handling and debug
    this.client.interceptors.response.use(
      (response) => {
        console.log(`Response from ${response.config.url} received:`, { 
          status: response.status,
          statusText: response.statusText,
          dataSize: response.data ? JSON.stringify(response.data).length : 0
        });
        return response;
      },
      async (error) => {
        console.error('Response error:', error);
        
        const originalRequest = error.config;
        
        // Handle 401 errors by refreshing token and retrying (if not already retried)
        if (error.response?.status === 401 && !originalRequest._retry && this.refreshToken) {
          console.log('401 error detected, attempting token refresh');
          originalRequest._retry = true;
          
          try {
            await this.refreshAccessToken();
            
            // Update the Authorization header and retry
            originalRequest.headers['Authorization'] = `Bearer ${this.accessToken}`;
            console.log('Retrying request with new token');
            return this.client(originalRequest);
          } catch (refreshError) {
            // If refresh fails, clear tokens and reject
            console.error('Token refresh failed:', refreshError);
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
    try {
      this.accessToken = localStorage.getItem(ADMIN_TOKEN_STORAGE_KEY);
      this.refreshToken = localStorage.getItem(ADMIN_REFRESH_TOKEN_STORAGE_KEY);
      const expiryStr = localStorage.getItem(ADMIN_TOKEN_EXPIRY_KEY);
      this.tokenExpiry = expiryStr ? parseInt(expiryStr, 10) : null;
      
      console.log('Loaded tokens from storage:', {
        accessTokenExists: !!this.accessToken,
        refreshTokenExists: !!this.refreshToken,
        expiry: this.tokenExpiry
      });
    } catch (error) {
      console.error('Error loading tokens from storage:', error);
    }
  }

  /**
   * Save tokens to localStorage (client-side only)
   */
  private saveTokensToStorage(): void {
    if (typeof window === 'undefined') return;
    
    try {
      console.log('Saving tokens to storage');
      
      if (this.accessToken) {
        localStorage.setItem(ADMIN_TOKEN_STORAGE_KEY, this.accessToken);
      } else {
        localStorage.removeItem(ADMIN_TOKEN_STORAGE_KEY);
      }
      
      if (this.refreshToken) {
        localStorage.setItem(ADMIN_REFRESH_TOKEN_STORAGE_KEY, this.refreshToken);
      } else {
        localStorage.removeItem(ADMIN_REFRESH_TOKEN_STORAGE_KEY);
      }
      
      if (this.tokenExpiry) {
        localStorage.setItem(ADMIN_TOKEN_EXPIRY_KEY, this.tokenExpiry.toString());
      } else {
        localStorage.removeItem(ADMIN_TOKEN_EXPIRY_KEY);
      }
      
      console.log('Tokens saved successfully');
    } catch (error) {
      console.error('Error saving tokens to storage:', error);
    }
  }

  /**
   * Check if token should be refreshed (less than 5 minutes remaining)
   */
  private shouldRefreshToken(): boolean {
    if (!this.accessToken || !this.tokenExpiry) return false;
    
    // Refresh if less than 5 minutes remaining
    const fiveMinutesInMs = 5 * 60 * 1000;
    const shouldRefresh = Date.now() + fiveMinutesInMs > this.tokenExpiry;
    
    if (shouldRefresh) {
      console.log('Token expires soon, should refresh:', {
        now: new Date(),
        expires: new Date(this.tokenExpiry),
        timeRemaining: Math.floor((this.tokenExpiry - Date.now()) / 1000) + ' seconds'
      });
    }
    
    return shouldRefresh;
  }

  /**
   * Refresh the access token using the refresh token
   */
  private async refreshAccessToken(): Promise<void> {
    if (!this.refreshToken) {
      console.error('No refresh token available for token refresh');
      throw new Error('No refresh token available');
    }
    
    try {
      console.log('Attempting to refresh access token');
      
      // Call the refresh token endpoint
      const response = await axios.post<AdminAuthResponse>(
        `${this.baseUrl}/auth/admin/refresh`,
        { refresh_token: this.refreshToken }
      );
      
      console.log('Token refresh successful');
      
      // Update tokens with new values
      this.setTokensFromResponse(response.data);
    } catch (error) {
      console.error('Token refresh failed:', error);
      // If refresh fails, clear tokens
      this.clearTokens();
      throw error;
    }
  }

  /**
   * Set tokens from auth response
   */
  private setTokensFromResponse(authResponse: AdminAuthResponse): void {
    console.log('Setting tokens from auth response');
    this.accessToken = authResponse.access_token;
    this.refreshToken = authResponse.refresh_token;
    this.tokenExpiry = authResponse.expires_at * 1000; // Convert to milliseconds
    
    console.log('Tokens set successfully:', {
      accessTokenExists: !!this.accessToken,
      refreshTokenExists: !!this.refreshToken,
      expires: new Date(this.tokenExpiry || 0)
    });
    
    this.saveTokensToStorage();
  }

  /**
   * Clear all tokens
   */
  public clearTokens(): void {
    console.log('Clearing all tokens');
    this.accessToken = null;
    this.refreshToken = null;
    this.tokenExpiry = null;
    
    if (typeof window !== 'undefined') {
      localStorage.removeItem(ADMIN_TOKEN_STORAGE_KEY);
      localStorage.removeItem(ADMIN_REFRESH_TOKEN_STORAGE_KEY);
      localStorage.removeItem(ADMIN_TOKEN_EXPIRY_KEY);
      console.log('Tokens cleared from storage');
    }
  }

  /**
   * Check if admin is authenticated
   */
  public isAuthenticated(): boolean {
    const hasToken = !!this.accessToken;
    const hasExpiry = !!this.tokenExpiry;
    const notExpired = hasExpiry && Date.now() < this.tokenExpiry!;
    
    const isAuth = hasToken && hasExpiry && notExpired;
    
    console.log('Authentication check:', {
      hasToken,
      hasExpiry,
      notExpired,
      isAuthenticated: isAuth
    });
    
    if (hasExpiry && !notExpired) {
      console.log('Token has expired:', {
        now: new Date(),
        expiry: new Date(this.tokenExpiry!),
        difference: Math.floor((this.tokenExpiry! - Date.now()) / 1000) + ' seconds'
      });
    }
    
    return isAuth;
  }

  /**
   * Log in as admin
   */
  public async login(
    credentials: AdminLoginRequest
  ): Promise<AdminAuthResponse> {
    console.log(`Attempting login for user: ${credentials.username}`);
    
    try {
      const response = await this.client.post<AdminAuthResponse>(
        '/auth/admin/token',
        {
          username: credentials.username,
          password: credentials.password,
        }
      );
      
      console.log('Login successful, received tokens');
      
      // Store tokens
      this.setTokensFromResponse(response.data);
      
      return response.data;
    } catch (error) {
      console.error('Login failed:', error);
      throw this.normalizeError(error);
    }
  }

  /**
   * Get admin data from /auth/admin/me endpoint
   */
  public async getAdminData(): Promise<AdminDataResponse> {
    if (!this.isAuthenticated()) {
      console.error('Authentication required for getAdminData');
      throw new Error('Authentication required. Please log in first.');
    }
  
    try {
      console.log('Fetching admin data from /auth/admin/me...');
      if (this.accessToken) {
        console.log('Using access token:', this.accessToken.substring(0, 10) + '...');
      }
      
      const response = await this.client.get('/auth/admin/me');
      console.log('Admin data response received:', response.data);
      
      const data = response.data;
      
      // Transform the response to match the expected format
      // Parse the admin name into firstname and lastname
      let firstname = "Admin";
      let lastname = "";
      
      if (data.admin_info && data.admin_info.name) {
        const nameParts = data.admin_info.name.split(' ');
        if (nameParts.length > 1) {
          firstname = nameParts[0];
          lastname = nameParts.slice(1).join(' ');
        } else {
          firstname = data.admin_info.name;
        }
      }
      
      // Create the formatted response
      const formattedResponse: AdminDataResponse = {
        admin: {
          id: data.admin_info?.id || 1, // Default to 1 if not provided
          login_id: data.admin_info?.login_id || 0,
          firstname,
          lastname,
          email: data.admin_info?.email || '',
          is_superadmin: data.admin_info?.is_superadmin || false
        },
        slots: data.slots || []
      };
      
      console.log('Formatted admin data:', formattedResponse);
      return formattedResponse;
    } catch (error) {
      console.error('Error in getAdminData:', error);
      if (axios.isAxiosError(error)) {
        console.error('API error details:', {
          status: error.response?.status,
          statusText: error.response?.statusText,
          data: error.response?.data,
          config: {
            url: error.config?.url,
            method: error.config?.method,
            headers: error.config?.headers
          }
        });
      }
      throw this.normalizeError(error);
    }
  }

  /**
   * Create availability slots
   */
  public async createSlots(
    slotsData: CreateSlotsRequest
  ): Promise<AdminSlotWithBooking[]> {
    if (!this.isAuthenticated()) {
      console.error('Authentication required for createSlots');
      throw new Error('Authentication required. Please log in first.');
    }

    try {
      console.log('Creating slots:', slotsData);
      const response = await this.client.post<AdminSlotWithBooking[]>(
        '/moodle/scheduler/slots',
        slotsData
      );
      console.log('Slots created successfully:', response.data);
      return response.data;
    } catch (error) {
      console.error('Failed to create slots:', error);
      throw this.normalizeError(error);
    }
  }

  /**
   * Get admin slots
   */
  public async getSlots(): Promise<AdminSlotWithBooking[]> {
    if (!this.isAuthenticated()) {
      console.error('Authentication required for getSlots');
      throw new Error('Authentication required. Please log in first.');
    }

    try {
      console.log('Fetching admin slots...');
      const response = await this.client.get<AdminSlotWithBooking[]>(
        '/moodle/scheduler/admin/slots'
      );
      console.log('Slots fetched successfully:', response.data);
      return response.data;
    } catch (error) {
      console.error('Failed to fetch slots:', error);
      throw this.normalizeError(error);
    }
  }

  /**
   * Normalize different error types into a consistent format
   */
  private normalizeError(error: unknown): ApiError {
    console.log('Normalizing error:', error);
    
    if (axios.isAxiosError(error)) {
      const axiosError = error as AxiosError<any>;
      
      // Handle API specific error format
      if (axiosError.response?.data?.detail) {
        return {
          message: axiosError.response.data.detail,
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
   * Test connection to the backend
   * Useful for debugging connection issues
   */
  public async testConnection(): Promise<boolean> {
    try {
      console.log('Testing connection to backend...');
      // Make a simple GET request to the server root
      const response = await this.client.get('/');
      console.log('Connection test successful:', response.status);
      return true;
    } catch (error) {
      console.error('Connection test failed:', error);
      return false;
    }
  }

  /**
 * Get bookings with student details for the current admin
 */
public async getAdminBookingDetails(): Promise<AdminBookingWithStudent[]> {
  if (!this.isAuthenticated()) {
    throw new Error('Authentication required. Please log in first.');
  }

  try {
    const response = await this.client.get<AdminBookingWithStudent[]>(
      '/moodle/scheduler/bookings/admin'
    );
    return response.data;
  } catch (error) {
    throw this.normalizeError(error);
  }
}
}

// Create and export a singleton instance
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
export const adminApi = new AdminApiClient(API_URL);