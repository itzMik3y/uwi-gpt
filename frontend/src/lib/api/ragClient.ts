// app/api/ragClient.ts
import { utils } from './utils';
import { RagQueryRequest, RagQueryResponse } from '@/types/rag';

// Get API URL from environment variable or use default
const API_URL = process.env.NEXT_PUBLIC_RAG_API_URL || 'http://localhost:8000';

// Longer timeout for RAG queries (120 seconds)
const RAG_QUERY_TIMEOUT = 120000;

/**
 * Client for interacting with the RAG API
 */
export const ragClient = {
  /**
   * Sends a query to the RAG API and gets a response
   * @param query The user's question
   * @param filters Optional filters to apply to the query
   */
  async sendQuery(
    query: string, 
    filters?: RagQueryRequest['filters']
  ): Promise<RagQueryResponse> {
    const endpoint = `${API_URL}/rag/query`;
    const requestData: RagQueryRequest = {
      query,
      ...(filters && { filters })
    };
    
    try {
      console.log('Sending RAG query:', requestData);
      
      // Use longer timeout for RAG queries
      const response = await utils.fetchWithTimeout(
        endpoint,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...utils.getAuthHeaders() // Add auth headers if available
          },
          body: JSON.stringify(requestData),
          // Add cache: 'no-store' to prevent caching
          cache: 'no-store',
        },
        RAG_QUERY_TIMEOUT // Use extended timeout
      );
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error(`RAG API Error (${response.status}):`, errorText);
        
        if (response.status === 504 || response.status === 408) {
          throw new Error('Request timed out. The server is taking too long to respond.');
        }
        
        throw new Error(`RAG API Error: ${response.status} - ${errorText || 'Unknown error'}`);
      }
      
      const data = await response.json();
      console.log('RAG API response received:', data);
      return data;
    } catch (error) {
      console.error('Error querying RAG API:', error);
      
      // Check if it's an AbortError (timeout)
      if (error instanceof Error && error.name === 'AbortError') {
        throw new Error('Request timed out. The server is taking too long to respond.');
      }
      
      throw error;
    }
  },
  
  /**
   * Fetches available sources for RAG queries
   */
  async getSources(): Promise<string[]> {
    const endpoint = `${API_URL}/rag/sources`;
    
    try {
      const response = await utils.fetchWithTimeout(
        endpoint,
        {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            ...utils.getAuthHeaders()
          }
        },
        30000 // 30 seconds timeout for sources
      );
      
      if (!response.ok) {
        throw new Error(`Failed to fetch sources: ${response.status}`);
      }
      
      return await response.json();
    } catch (error) {
      console.error('Error fetching RAG sources:', error);
      // Return empty array instead of throwing to avoid breaking the UI
      return [];
    }
  }
};