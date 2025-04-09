#!/usr/bin/env python
"""
Standalone script to test the BM25Retriever tokenization and retrieval.
"""

import logging
from typing import List, Dict, Any
from types import SimpleNamespace # Used to mock LangChain's Document class
import string

# --- Dependencies copied from your retriever code ---
from pydantic import PrivateAttr, BaseModel # Added BaseModel for potential future use
from rank_bm25 import BM25Okapi
from langchain.schema import BaseRetriever
# --- End Dependencies ---

# Configure basic logging for the test
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Mock Document Class ---
# We need a simple object that behaves like langchain.schema.Document
# It needs 'page_content' (string) and 'metadata' (dict) attributes.
class MockDocument:
    def __init__(self, page_content: str, metadata: Dict[str, Any]):
        self.page_content = page_content
        self.metadata = metadata

    def __repr__(self):
        # Provide a cleaner representation for printing
        return f"MockDocument(content='{self.page_content[:50]}...', metadata={self.metadata})"

# --- BM25Retriever Class (Copied directly from your provided code) ---
class BM25Retriever(BaseRetriever):
    """
    A retriever that uses BM25 algorithm for keyword-based retrieval.
    Uses improved tokenization that removes punctuation.
    """
    _documents: List[MockDocument] = PrivateAttr() # Adjusted type hint
    _tokenized: List[List[str]] = PrivateAttr()   # Adjusted type hint
    _k: int = PrivateAttr()
    _bm25 = PrivateAttr()

    def __init__(self, documents: List[MockDocument], k: int = 10): # Adjusted type hint
        """
        Initialize the BM25 retriever.

        Args:
            documents: List of Document objects (or mock objects)
            k: Number of documents to retrieve
        """
        super().__init__()
        if not documents:
             raise ValueError("Documents list cannot be empty.")
        self._documents = documents
        logger.info("Tokenizing documents for BM25 (with punctuation removal)...")

        # --- MODIFIED TOKENIZATION LOGIC ---
        # Create a translation table to remove punctuation
        translator = str.maketrans('', '', string.punctuation)
        self._tokenized = []
        for doc in documents:
            # Convert to lowercase
            text = doc.page_content.lower()
            # Remove punctuation using the translator
            text_no_punct = text.translate(translator)
            # Split the cleaned text into tokens by whitespace
            tokens = text_no_punct.split()
            self._tokenized.append(tokens)
        # --- END MODIFIED TOKENIZATION LOGIC ---

        self._k = k
        logger.info(f"Initializing BM25Okapi with {len(self._tokenized)} tokenized documents.")
        self._bm25 = BM25Okapi(self._tokenized)
        logger.info("BM25Retriever initialized.")

    def _get_relevant_documents(self, query: str, **kwargs) -> List[MockDocument]: # Adjusted type hint
        """
        Get documents relevant to the query using BM25 algorithm.

        Args:
            query: The query string
            **kwargs: Additional arguments

        Returns:
            List of relevant documents
        """
        logger.info(f"Received query for BM25: '{query}'")

        # --- ALSO CLEAN AND TOKENIZE QUERY THE SAME WAY ---
        query_lower = query.lower()
        translator = str.maketrans('', '', string.punctuation) # Reuse translator
        query_no_punct = query_lower.translate(translator)
        query_tokens = query_no_punct.split()
        # --- END QUERY TOKENIZATION UPDATE ---

        logger.info(f"Query tokenized to: {query_tokens}")

        # Get BM25 scores for the query against all documents
        all_scores = self._bm25.get_scores(query_tokens)
        logger.info(f"Calculated {len(all_scores)} BM25 scores.")

        # Combine documents with their scores
        scored_docs = list(zip(self._documents, all_scores))

        # Sort documents by score in descending order
        # Filter out documents with score <= 0 as they are typically non-matches
        relevant_scored_docs = sorted(
            [item for item in scored_docs if item[1] > 0],
            key=lambda x: x[1],
            reverse=True
        )
        logger.info(f"Found {len(relevant_scored_docs)} documents with score > 0.")

        # Return the top k documents
        top_k_docs = [doc for doc, score in relevant_scored_docs[:self._k]]
        logger.info(f"Returning top {len(top_k_docs)} documents based on k={self._k}.")
        return top_k_docs

    # --- Helper method added for testing scores ---
    # Also update this to tokenize query consistently
    def get_scores_for_query(self, query: str) -> Dict[int, float]:
        """Calculates and returns BM25 scores for a query mapped by original doc index."""
        query_lower = query.lower()
        translator = str.maketrans('', '', string.punctuation)
        query_no_punct = query_lower.translate(translator)
        query_tokens = query_no_punct.split() # Clean query tokens here too

        all_scores = self._bm25.get_scores(query_tokens)
        # Map score to original document index
        scores_by_index = {i: score for i, score in enumerate(all_scores)}
        return scores_by_index

    get_relevant_documents = _get_relevant_documents

# --- Main Test Execution ---
if __name__ == "__main__":
    # 1. Create Sample Documents
    sample_docs_data = [
        {"content": "This document contains information about COMP1210.", "id": "doc1"},
        {"content": "Introduction to Programming using Python.", "id": "doc2"},
        {"content": "Course outline for comp1210 (lowercase).", "id": "doc3"},
        {"content": "Prerequisites: MATH1141, COMP1210, and FOUN1101.", "id": "doc4"},
        {"content": "COMP1220 builds upon the concepts from COMP1210.", "id": "doc5"},
        {"content": "Advanced Algorithms (COMP3101).", "id": "doc6"},
        {"content": "Regarding COMP1210, the final exam is scheduled.", "id": "doc7"},
    ]
    # Convert to MockDocument objects
    mock_documents = [MockDocument(page_content=d["content"], metadata={"source": d["id"]}) for d in sample_docs_data]
    print(f"Created {len(mock_documents)} sample documents.")

    # 2. Initialize BM25Retriever
    # Set k high enough to see ranking, or set to desired retrieval number
    bm25_retriever = BM25Retriever(documents=mock_documents, k=5)

    # 3. Test Tokenization Inspection
    print("\n--- Tokenization Check ---")
    test_query = "COMP1210"
    query_tokens = test_query.lower().split()
    print(f"Query: '{test_query}'")
    print(f"Query Tokens: {query_tokens}")

    # Inspect tokenization of the first document (index 0)
    doc_index_to_inspect = 0
    if len(mock_documents) > doc_index_to_inspect:
        print(f"\nDocument {doc_index_to_inspect} Content: '{mock_documents[doc_index_to_inspect].page_content}'")
        # Access the internal _tokenized list (conventionally private)
        print(f"Document {doc_index_to_inspect} Tokens: {bm25_retriever._tokenized[doc_index_to_inspect]}")
    else:
        print(f"\nCannot inspect document index {doc_index_to_inspect}, only {len(mock_documents)} documents exist.")

    # 4. Test Retrieval
    print("\n--- Retrieval Test ---")
    print(f"Retrieving top {bm25_retriever._k} documents for query: '{test_query}'")
    retrieved_docs = bm25_retriever.get_relevant_documents(test_query)

    # 5. Display Results (including scores for clarity)
    print(f"\n--- Results (Top {len(retrieved_docs)}) ---")
    if not retrieved_docs:
        print("No relevant documents found.")
    else:
        # Get scores for context (using the helper method)
        all_doc_scores = bm25_retriever.get_scores_for_query(test_query)
        # Find the original index and score for each retrieved document
        retrieved_info = []
        for ret_doc in retrieved_docs:
            original_index = -1
            # Find the original index by matching metadata or content (metadata is better if unique)
            for i, orig_doc in enumerate(mock_documents):
                 if ret_doc.metadata['source'] == orig_doc.metadata['source']:
                      original_index = i
                      break
            score = all_doc_scores.get(original_index, "N/A") # Get score using original index
            retrieved_info.append({"doc": ret_doc, "original_index": original_index, "score": score})

        # Print ranked results with scores
        for i, info in enumerate(retrieved_info):
            print(f"Rank {i+1}:")
            print(f"  Original Index: {info['original_index']}")
            print(f"  BM25 Score: {info['score']:.4f}")
            print(f"  Content: '{info['doc'].page_content}'")
            print(f"  Metadata: {info['doc'].metadata}")
            print("-" * 10)