// app/api/utils.ts
import { cn } from "@/lib/utils";

/**
 * Common utility functions for API calls
 */
export const utils = {
  /**
   * Fetch with timeout to prevent hanging requests
   * @param url The URL to fetch
   * @param options Fetch options
   * @param timeout Timeout in milliseconds (default: 30000)
   */
  async fetchWithTimeout(
    url: string, 
    options: RequestInit = {}, 
    timeout = 30000
  ): Promise<Response> {
    // Create an abort controller with timeout
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);
    
    try {
      const response = await fetch(url, {
        ...options,
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      return response;
    } catch (error) {
      clearTimeout(timeoutId);
      throw error;
    }
  },
  
  /**
   * Check if the user is authenticated
   */
  isAuthenticated(): boolean {
    // This would check for a valid token in localStorage or cookies
    return !!localStorage.getItem('auth_token');
  },
  
  /**
   * Get the auth headers for authenticated requests
   */
  getAuthHeaders(): HeadersInit {
    const token = localStorage.getItem('auth_token');
    return token ? {
      'Authorization': `Bearer ${token}`
    } : {};
  },
  
  /**
   * Combine class names using the cn utility
   * This is just a re-export for convenience
   */
  cn,
  
  /**
   * Format a date to a human-readable string
   */
  formatDate(date: Date | string): string {
    if (typeof date === 'string') {
      date = new Date(date);
    }
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: 'numeric',
      hour12: true
    });
  },
  
  /**
   * Truncate text to a specific length with ellipsis
   */
  truncateText(text: string, maxLength = 100): string {
    if (text.length <= maxLength) return text;
    return text.slice(0, maxLength) + '...';
  }
};