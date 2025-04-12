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
  
  export interface RagQueryRequest {
    query: string;
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
  }
  
  export interface Message {
    id: string;
    content: string;
    sender: 'user' | 'bot';
    timestamp: string;
  }