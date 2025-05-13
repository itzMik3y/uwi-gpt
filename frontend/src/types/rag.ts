// app/types/rag.ts

/**
 * Types for the RAG API
 */

export interface RagDocument {
  source: string;
  docType?: string;
  policyArea?: string;
  content: string;
}

// This is the existing Message interface, ensure it's defined or imported
// if it's in a different file.
export interface Message {
  id: string;
  content: string;
  sender: 'user' | 'bot';
  timestamp: string;
}

export interface RagQueryRequest {
  query: string;
  history?: Message[]; // Added: To send previous messages
  filters?: {
    docType?: string;
    policyArea?: string;
    source?: string;
  };
}

export interface RagQueryResponse {
  answer: string;
  processing_time: number;
  context?: string;
  documents?: RagDocument[];
  // If your backend sends back user_context, ensure it's typed here
  user_context?: any; // You might want to type this more specifically
}
