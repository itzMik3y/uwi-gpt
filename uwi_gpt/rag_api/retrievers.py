#!/usr/bin/env python
"""
rag_api/retrievers.py - Custom retriever classes for the RAG API
"""

import logging
from typing import List
from pydantic import PrivateAttr
from rank_bm25 import BM25Okapi
from langchain.schema import BaseRetriever
import string
logger = logging.getLogger(__name__)

class BM25Retriever(BaseRetriever):
    """
    A retriever that uses BM25 algorithm for keyword-based retrieval.
    Uses improved tokenization that removes punctuation.
    """
    _documents: list = PrivateAttr()
    _tokenized: list = PrivateAttr() # Keep as list for simplicity if original used list
    _k: int = PrivateAttr()
    _bm25 = PrivateAttr()

    def __init__(self, documents: list, k: int = 10):
        """
        Initialize the BM25 retriever.

        Args:
            documents: List of Document objects (ensure they have page_content)
            k: Number of documents to retrieve
        """
        super().__init__()
        if not documents:
             raise ValueError("Documents list cannot be empty for BM25Retriever.")
        self._documents = documents

        # --- MODIFIED TOKENIZATION LOGIC ---
        # Create a translation table to remove punctuation
        translator = str.maketrans('', '', string.punctuation)
        self._tokenized = []
        for doc in documents:
            if hasattr(doc, 'page_content') and isinstance(doc.page_content, str):
                 # Convert to lowercase
                 text = doc.page_content.lower()
                 # Remove punctuation using the translator
                 text_no_punct = text.translate(translator)
                 # Split the cleaned text into tokens by whitespace
                 tokens = text_no_punct.split()
                 self._tokenized.append(tokens)
            else:
                 # Handle cases where document structure might be unexpected
                 # You might want to log a warning or skip the document
                 self._tokenized.append([]) # Add empty list for placeholder
                 # Consider adding logging here if this happens
        # --- END MODIFIED TOKENIZATION LOGIC ---

        self._k = k
        # Consider adding logging back if you remove it from test script
        # logger.info(f"Initializing BM25Okapi with {len(self._tokenized)} tokenized documents.")
        self._bm25 = BM25Okapi(self._tokenized)
        # logger.info("BM25Retriever initialized.")


    def _get_relevant_documents(self, query: str, **kwargs) -> list:
        """
        Get documents relevant to the query using BM25 algorithm.

        Args:
            query: The query string
            **kwargs: Additional arguments

        Returns:
            List of relevant documents
        """
        # --- ALSO CLEAN AND TOKENIZE QUERY THE SAME WAY ---
        query_lower = query.lower()
        translator = str.maketrans('', '', string.punctuation) # Reuse translator
        query_no_punct = query_lower.translate(translator)
        tokens = query_no_punct.split()
        # --- END QUERY TOKENIZATION UPDATE ---

        # Get BM25 scores for the query against all documents
        scores = self._bm25.get_scores(tokens)

        # Combine documents with their scores
        scored_docs = list(zip(self._documents, scores))

        # Sort documents by score in descending order
        # Filter out documents with score <= 0 (optional but good practice)
        relevant_scored_docs = sorted(
            [item for item in scored_docs if item[1] > 0],
            key=lambda x: x[1],
            reverse=True
        )

        # Return the top k documents
        # Original code didn't filter scores > 0 before sorting/slicing,
        # sticking to that structure unless filtering is desired.
        # If you want to ensure only positive scores are returned:
        # top_k_docs = [doc for doc, score in relevant_scored_docs[:self._k]]
        # return top_k_docs

        # Replicating original logic structure (sort all, then slice)
        # but using cleaned tokens for scoring:
        scored_docs_sorted = sorted(scored_docs, key=lambda x: x[1], reverse=True)
        return [doc for doc, score in scored_docs_sorted[:self._k]]

    # Keep this line if your LangChain version expects it,
    # but be aware of the deprecation warning.
    get_relevant_documents = _get_relevant_documents



class EnsembleRetriever(BaseRetriever):
    """
    A retriever that combines multiple retrievers with different weights.
    
    This retriever allows for the combination of different retrieval strategies
    (e.g., semantic and keyword-based) to get the best overall results.
    """
    _retrievers: list = PrivateAttr()
    _weights: list = PrivateAttr()
    _threshold: float = PrivateAttr()

    def __init__(self, retrievers: list, weights: list, threshold: float = 0.1):
        """
        Initialize the ensemble retriever.
        
        Args:
            retrievers: List of retriever objects
            weights: List of weights for each retriever
            threshold: Minimum score threshold for documents to be included
        """
        super().__init__()
        if len(retrievers) != len(weights):
            raise ValueError("The number of retrievers must match the number of weights.")
        self._retrievers = retrievers
        self._weights = weights
        self._threshold = threshold

    def _get_relevant_documents(self, query: str, **kwargs) -> list:
        """
        Get documents relevant to the query using multiple retrievers.
        
        Args:
            query: The query string
            **kwargs: Additional arguments
            
        Returns:
            List of relevant documents
        """
        doc_scores = {}
        for retriever, weight in zip(self._retrievers, self._weights):
            docs = retriever.get_relevant_documents(query, **kwargs)
            for rank, doc in enumerate(docs):
                score = weight * (1.0 / (rank + 1))
                # Slightly boost if there's a heading
                if doc.metadata.get("heading", "N/A") != "N/A":
                    score *= 1.1
                doc_id = doc.metadata.get("source_file", doc.id)
                if doc_id in doc_scores:
                    doc_scores[doc_id]["score"] += score
                else:
                    doc_scores[doc_id] = {"doc": doc, "score": score}
        # Filter out docs below threshold
        filtered = [item["doc"] for item in doc_scores.values() if item["score"] >= self._threshold]
        # Sort by final ensemble score
        sorted_docs = sorted(
            filtered,
            key=lambda d: doc_scores[d.metadata.get("source_file", d.id)]["score"],
            reverse=True
        )
        return sorted_docs

    get_relevant_documents = _get_relevant_documents