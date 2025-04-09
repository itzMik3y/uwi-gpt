// src/lib/auth/authService.ts
import { moodleApi } from '@/lib/api/moodleClient';
import { MoodleLoginRequest } from '@/types/moodle';

// Local storage keys
const AUTH_TOKEN_KEY = 'moodle_auth_token';
const USER_EMAIL_KEY = 'moodle_user_email';

interface AuthSession {
//   token: string;
  email: string;
}

/**
 * Authentication service with token management
 */
export const authService = {
  /**
   * Login with Moodle credentials
   */
  login: async (credentials: MoodleLoginRequest): Promise<AuthSession> => {
    const response = await moodleApi.login(credentials);
    
    // Store token and email
    // localStorage.setItem(AUTH_TOKEN_KEY, response.token);
    localStorage.setItem(USER_EMAIL_KEY, credentials.username);
    
    return {
    //   token: response.token,
      email: credentials.username
    };
  },

  /**
   * Logout the current user
   */
  logout: (): void => {
    // Clear token and user data
    localStorage.removeItem(AUTH_TOKEN_KEY);
    localStorage.removeItem(USER_EMAIL_KEY);
    moodleApi.clearToken();
  },

  /**
   * Check if user is authenticated
   */
  isAuthenticated: (): boolean => {
    return !!localStorage.getItem(AUTH_TOKEN_KEY);
  },

  /**
   * Get the current auth token
   */
  getToken: (): string | null => {
    return localStorage.getItem(AUTH_TOKEN_KEY);
  },

  /**
   * Get the current user email
   */
  getUserEmail: (): string | null => {
    return localStorage.getItem(USER_EMAIL_KEY);
  },

  /**
   * Initialize auth from stored token on app start
   */
  initializeAuth: (): void => {
    const token = localStorage.getItem(AUTH_TOKEN_KEY);
    if (token) {
      moodleApi.setToken(token);
    }
  }
};