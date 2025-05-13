// app/api/ragClient.ts

import { TOKEN_STORAGE_KEY, REFRESH_TOKEN_STORAGE_KEY, TOKEN_EXPIRY_KEY } from '@/lib/api/moodleClient';
// Ensure Message type is imported or defined if not in rag.ts
import { RagQueryRequest, RagQueryResponse, Message } from '@/types/rag';

// Get API URL from environment variable or use default
const API_URL = process.env.NEXT_PUBLIC_RAG_API_URL || 'http://localhost:8000';

// Longer timeout for RAG queries (120 seconds)
const RAG_QUERY_TIMEOUT = 120000;

/**
 * RAG API client with authentication support
 */
class RagApiClient {
  private baseUrl: string;
  private accessToken: string | null = null;
  private refreshToken: string | null = null;
  private tokenExpiry: number | null = null;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
    
    // Initialize from localStorage if available (client-side only)
    if (typeof window !== 'undefined') {
      this.loadTokensFromStorage();
    }
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
   * Check if token should be refreshed (less than 5 minutes remaining)
   */
  private shouldRefreshToken(): boolean {
    if (!this.accessToken || !this.tokenExpiry) return false;
    
    // Refresh if less than 5 minutes remaining
    const fiveMinutesInMs = 5 * 60 * 1000;
    return Date.now() + fiveMinutesInMs > this.tokenExpiry;
  }

  /**
   * Get authentication headers for requests
   */
  private getAuthHeaders(): Record<string, string> {
    // Reload tokens from storage to ensure we have the latest
    if (typeof window !== 'undefined') {
      this.loadTokensFromStorage();
    }
    
    const headers: Record<string, string> = {};
    
    if (this.accessToken) {
      headers['Authorization'] = `Bearer ${this.accessToken}`;
    }
    
    return headers;
  }

  /**
   * Create AbortController with timeout
   */
  private createAbortControllerWithTimeout(timeoutMs: number): { 
    controller: AbortController; 
    timeoutId: number | NodeJS.Timeout;
  } {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    return { controller, timeoutId };
  }

  /**
   * Check if user is authenticated
   */
  public isAuthenticated(): boolean {
    return !!this.accessToken && !!this.tokenExpiry && Date.now() < this.tokenExpiry;
  }

  /**
   * Sends a query to the RAG API and gets a response
   * @param query The user's question
   * @param history Optional array of previous messages for context
   * @param filters Optional filters to apply to the query
   */
  async sendQuery(
    query: string,
    history?: Message[], // Added history parameter
    filters?: RagQueryRequest['filters']
  ): Promise<RagQueryResponse> {
    const endpoint = `${this.baseUrl}/rag/query`;
    const requestData: RagQueryRequest = {
      query,
      ...(history && { history }), // Include history if provided
      ...(filters && { filters })
    };
    
    try {
      console.log('Sending RAG query:', requestData);
      
      const { controller, timeoutId } = this.createAbortControllerWithTimeout(RAG_QUERY_TIMEOUT);
      
      try {
        const response = await fetch(endpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...this.getAuthHeaders()
          },
          body: JSON.stringify(requestData),
          signal: controller.signal,
          cache: 'no-store',
        });
        
        clearTimeout(timeoutId);
        
        if (!response.ok) {
          const errorText = await response.text();
          console.error(`RAG API Error (${response.status}):`, errorText);
          
          if (response.status === 504 || response.status === 408) {
            throw new Error('Request timed out. The server is taking too long to respond.');
          }
          
          if (response.status === 401) {
            throw new Error('Authentication required. Please log in again.');
          }
          
          throw new Error(`RAG API Error: ${response.status} - ${errorText || 'Unknown error'}`);
        }
        
        const data = await response.json();
        console.log('RAG API response received:', data);
        return data;
      } finally {
        clearTimeout(timeoutId);
      }
    } catch (error) {
      console.error('Error querying RAG API:', error);
      
      // Check if it's an AbortError (timeout)
      if (error instanceof Error && error.name === 'AbortError') {
        throw new Error('Request timed out. The server is taking too long to respond.');
      }
      
      throw error;
    }
  }

  /**
   * Streams a query response from the RAG API using fetch and ReadableStream
   * @param query The user's question
   * @param history Optional array of previous messages for context
   * @param onChunk Callback for each text chunk received
   * @param onError Callback for errors
   * @param onComplete Callback when streaming is complete
   * @param filters Optional filters to apply to the query
   */
  streamQuery(
    query: string,
    history: Message[] | undefined, // Added history parameter
    onChunk: (text: string) => void,
    onError: (error: Error) => void,
    onComplete: (processingTime?: number, userContext?: any) => void, // Added userContext to onComplete
    filters?: RagQueryRequest['filters']
  ): () => void {
    const endpoint = `${this.baseUrl}/rag/stream_query`;
    const requestData: RagQueryRequest = {
      query,
      ...(history && { history }), // Include history if provided
      ...(filters && { filters })
    };

    console.log('Streaming RAG query:', requestData);

    // Create an AbortController for cancellation and timeout
    const controller = new AbortController();
    const { signal } = controller;
    
    // Set timeout
    const timeoutId = setTimeout(() => {
      controller.abort();
      onError(new Error('Request timed out. The server is taking too long to respond.'));
    }, RAG_QUERY_TIMEOUT);

    // Start the fetch request
    fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
        ...this.getAuthHeaders()
      },
      body: JSON.stringify(requestData),
      signal,
      cache: 'no-store'
    })
    .then(response => {
      if (!response.ok) {
        // Handle authentication errors specifically
        if (response.status === 401) {
          throw new Error('Authentication required. Please log in again.');
        }
        // Try to get error message from response body for other errors
        return response.text().then(text => {
          throw new Error(`HTTP error: ${response.status} - ${text || 'Unknown error'}`);
        });
      }
      
      if (!response.body) {
        throw new Error('ReadableStream not supported in this browser.');
      }
      
      // Get a reader from the response body
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      
      // Function to process chunks with explicit Promise<void> return type
      function processChunks(): Promise<void> {
        return reader.read().then(({ done, value }) => {
          if (done) {
            clearTimeout(timeoutId);
            // Note: The original onComplete only took processingTime.
            // If the 'end' event from backend now includes user_context,
            // it should be passed here. For now, assuming it might.
            onComplete(); 
            return;
          }
          
          // Decode the chunk and process events
          const chunk = decoder.decode(value, { stream: true });
          
          // Split the chunk into SSE events
          const events = chunk.split('\n\n').filter(Boolean);
          
          events.forEach(eventStr => {
            const eventLines = eventStr.split('\n');
            
            // Extract event type and data
            let eventType = 'message'; // Default event type
            let eventData = null;
            
            eventLines.forEach(line => {
              if (line.startsWith('event:')) {
                eventType = line.substring(6).trim();
              } else if (line.startsWith('data:')) {
                eventData = line.substring(5).trim();
              }
            });
            
            // Handle different event types
            if (eventData) {
              try {
                const parsedData = JSON.parse(eventData);
                
                if (eventType === 'message' && parsedData.text) {
                  onChunk(parsedData.text);
                } else if (eventType === 'error') {
                  onError(new Error(parsedData.detail || 'Unknown streaming error'));
                } else if (eventType === 'end') {
                  // Pass both processing_time and user_context if available
                  onComplete(parsedData.processing_time, parsedData.user_context);
                }
              } catch (e) {
                // If JSON.parse fails, it might be a simple text chunk without JSON structure
                // This can happen if the stream directly sends text for the 'message' event
                // without wrapping it in JSON. For now, we assume JSON as per current logic.
                console.error('Error parsing SSE data:', e, "Raw data:", eventData);
                // onError(new Error('Error parsing streamed data.'));
              }
            }
          });
          
          // Continue reading
          return processChunks();
        });
      }
      
      // Start processing chunks
      return processChunks();
    })
    .catch(error => {
      clearTimeout(timeoutId);
      
      // Handle specific errors
      if (error.name === 'AbortError') {
        onError(new Error('Request was aborted after timeout or cancellation.'));
      } else {
        console.error('Streaming error:', error);
        onError(error);
      }
    });
    
    // Return function to abort the stream
    return () => {
      console.log("Aborting stream query.");
      clearTimeout(timeoutId);
      controller.abort();
    };
  }

  /**
   * Fetches available sources for RAG queries
   */
  async getSources(): Promise<string[]> {
    const endpoint = `${this.baseUrl}/rag/sources`;
    
    try {
      const { controller, timeoutId } = this.createAbortControllerWithTimeout(30000); // 30s timeout
      
      try {
        const response = await fetch(endpoint, {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            ...this.getAuthHeaders()
          },
          signal: controller.signal
        });
        
        clearTimeout(timeoutId);
        
        if (!response.ok) {
          // Handle authentication errors specifically
          if (response.status === 401) {
            console.error('Authentication required for RAG sources');
            return []; // Or throw error, depending on desired behavior
          }
          throw new Error(`Failed to fetch sources: ${response.status}`);
        }
        
        return await response.json();
      } finally {
        clearTimeout(timeoutId);
      }
    } catch (error) {
      console.error('Error fetching RAG sources:', error);
      // Return empty array instead of throwing to avoid breaking the UI if sources are optional
      return [];
    }
  }
}

// Create and export a singleton instance
export const ragClient = new RagApiClient(API_URL);
