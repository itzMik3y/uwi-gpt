// app/api/ragClient.ts

import { utils } from './utils';
import { RagQueryRequest, RagQueryResponse, Message } from '@/types/rag';

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
   * Streams a query response from the RAG API using fetch and ReadableStream
   * This approach works better with POST requests than EventSource
   */
 // Final implementation for app/api/ragClient.ts - streamQuery function

/**
 * Streams a query response from the RAG API using fetch and ReadableStream
 * This approach works better with POST requests than EventSource
 */
streamQuery(
  query: string,
  onChunk: (text: string) => void,
  onError: (error: Error) => void,
  onComplete: (processingTime?: number) => void,
  filters?: RagQueryRequest['filters']
): () => void {
  const endpoint = `${API_URL}/rag/stream_query`;
  const requestData: RagQueryRequest = {
    query,
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
      ...utils.getAuthHeaders()
    },
    body: JSON.stringify(requestData),
    signal,
    cache: 'no-store'
  })
  .then(response => {
    if (!response.ok) {
      throw new Error(`HTTP error: ${response.status}`);
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
          let eventType = 'message';
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
                onError(new Error(parsedData.detail || 'Unknown error'));
              } else if (eventType === 'end') {
                onComplete(parsedData.processing_time);
              }
            } catch (e) {
              console.error('Error parsing SSE data:', e);
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
      onError(new Error('Request was aborted after timeout'));
    } else {
      console.error('Streaming error:', error);
      onError(error);
    }
  });
  
  // Return function to abort the stream
  return () => {
    clearTimeout(timeoutId);
    controller.abort();
  };
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