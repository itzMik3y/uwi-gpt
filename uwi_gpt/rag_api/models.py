#!/usr/bin/env python
"""
rag_api/models.py - Pydantic models for the RAG API
"""

from typing import Optional, List, ClassVar, Dict, Any
from pydantic import BaseModel, PrivateAttr

class QueryRequest(BaseModel):
    """Model for a query request"""
    query: str

class QueryResponse(BaseModel):
    """Model for a query response"""
    answer: str
    processing_time: float
    context: str
    user_context: Optional[Dict[str, Any]] = None

# rag_api/models.py
class SwitchLLMRequest(BaseModel):
    """Model for switching the LLM backend"""
    backend: str  # "ollama" or "gemini"
    # api_key: Optional[str] = None # REMOVE THIS LINE