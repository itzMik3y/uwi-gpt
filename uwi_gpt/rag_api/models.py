#!/usr/bin/env python
"""
rag_api/models.py - Pydantic models for the RAG API
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class MessageModel(BaseModel):
    """Model for a single message in a conversation history."""
    id: str
    content: str
    sender: str # Expected to be 'user' or 'bot'
    timestamp: str # ISO format string or similar

class QueryRequest(BaseModel):
    """Model for a query request to the RAG API."""
    query: str
    history: Optional[List[MessageModel]] = Field(None, description="Previous chat messages for context")
    filters: Optional[Dict[str, str]] = Field(None, description="Optional filters for the RAG query")

class QueryResponse(BaseModel):
    """Model for a query response from the RAG API."""
    answer: str
    processing_time: float
    context: Optional[str] = Field(None, description="The context string used by the LLM to generate the answer")
    user_context: Optional[Dict[str, Any]] = Field(None, description="User-specific context information, mirroring /auth/me structure")
    documents: Optional[List[Dict[str, Any]]] = Field(None, description="Optional list of retrieved document metadata")

class SwitchLLMRequest(BaseModel):
    """Model for switching the LLM backend."""
    backend: str  # Example values: "ollama", "gemini"

# You could also include other related models here if needed, for example,
# a model for the structure of individual documents if you decide to type
# the `documents` field in QueryResponse more strictly.
# class RagDocumentMetadata(BaseModel):
#     source: str
#     doc_type: Optional[str] = None
#     policy_area: Optional[str] = None
#     # ... other relevant metadata fields

# class QueryResponse(BaseModel):
#     # ...
#     documents: Optional[List[RagDocumentMetadata]] = None
