#!/usr/bin/env python
"""
rag_api/retrievers.py - Custom retriever classes for the RAG API
with enhanced BM25 tokenization and adaptive weighting
"""

import logging
import re
import string
from typing import List, Dict, Any
from pydantic import PrivateAttr
from rank_bm25 import BM25Okapi
from langchain.schema import BaseRetriever

# Add lemmatization support
import nltk
from nltk.stem import WordNetLemmatizer
from nltk.corpus import wordnet

logger = logging.getLogger(__name__)

# Download required NLTK resources (can be done at startup)
try:
    nltk.download('wordnet', quiet=True)
    nltk.download('punkt', quiet=True)
    nltk.download('averaged_perceptron_tagger', quiet=True)
except Exception as e:
    logger.warning(f"Failed to download NLTK resources: {e}")

def get_wordnet_pos(word):
    """Map POS tag to first character lemmatize() accepts"""
    tag = nltk.pos_tag([word])[0][1][0].upper()
    tag_dict = {"J": wordnet.ADJ,
                "N": wordnet.NOUN,
                "V": wordnet.VERB,
                "R": wordnet.ADV}
    return tag_dict.get(tag, wordnet.NOUN)

class EnhancedBM25Retriever(BaseRetriever):
    """
    An improved BM25 retriever that uses lemmatization for better matching
    between different word forms.
    """
    _documents: list = PrivateAttr()
    _tokenized: list = PrivateAttr()
    _lemmatized: list = PrivateAttr()
    _k: int = PrivateAttr()
    _bm25: BM25Okapi = PrivateAttr()
    _use_lemmatization: bool = PrivateAttr()
    _lemmatizer: WordNetLemmatizer = PrivateAttr()

    def __init__(self, documents: list, k: int = 10, use_lemmatization: bool = True):
        """
        Initialize the enhanced BM25 retriever.

        Args:
            documents: List of Document objects (ensure they have page_content)
            k: Number of documents to retrieve
            use_lemmatization: Whether to use lemmatization (can be turned off for speed)
        """
        super().__init__()
        if not documents:
            raise ValueError("Documents list cannot be empty for EnhancedBM25Retriever.")
        
        self._documents = documents
        self._k = k
        self._use_lemmatization = use_lemmatization
        
        # Initialize lemmatizer if needed
        if use_lemmatization:
            self._lemmatizer = WordNetLemmatizer()
        
        # Create a translation table to remove punctuation
        translator = str.maketrans('', '', string.punctuation)
        
        self._tokenized = []
        self._lemmatized = []
        
        for doc in documents:
            if hasattr(doc, 'page_content') and isinstance(doc.page_content, str):
                # Convert to lowercase
                text = doc.page_content.lower()
                # Remove punctuation
                text_no_punct = text.translate(translator)
                # Split into tokens
                tokens = text_no_punct.split()
                self._tokenized.append(tokens)
                
                # Lemmatize tokens if enabled
                if use_lemmatization:
                    lemmatized_tokens = []
                    for token in tokens:
                        pos = get_wordnet_pos(token)
                        lemma = self._lemmatizer.lemmatize(token, pos)
                        lemmatized_tokens.append(lemma)
                    self._lemmatized.append(lemmatized_tokens)
            else:
                self._tokenized.append([])
                if use_lemmatization:
                    self._lemmatized.append([])
        
        # Create BM25 index
        if use_lemmatization:
            logger.info(f"Initializing BM25Okapi with {len(self._lemmatized)} lemmatized documents.")
            self._bm25 = BM25Okapi(self._lemmatized)
        else:
            logger.info(f"Initializing BM25Okapi with {len(self._tokenized)} tokenized documents.")
            self._bm25 = BM25Okapi(self._tokenized)
        
        logger.info("Enhanced BM25Retriever initialized.")

    def _get_relevant_documents(self, query: str, **kwargs) -> list:
        """
        Get documents relevant to the query using BM25 algorithm with lemmatization.

        Args:
            query: The query string
            **kwargs: Additional arguments

        Returns:
            List of relevant documents
        """
        # Clean and tokenize query
        query_lower = query.lower()
        translator = str.maketrans('', '', string.punctuation)
        query_no_punct = query_lower.translate(translator)
        tokens = query_no_punct.split()
        
        # Lemmatize query tokens if enabled
        if self._use_lemmatization:
            lemmatized_query = []
            for token in tokens:
                pos = get_wordnet_pos(token)
                lemma = self._lemmatizer.lemmatize(token, pos)
                lemmatized_query.append(lemma)
            search_tokens = lemmatized_query
        else:
            search_tokens = tokens
        
        # Get BM25 scores
        scores = self._bm25.get_scores(search_tokens)
        
        # Combine documents with their scores
        scored_docs = list(zip(self._documents, scores))
        
        # Sort documents by score in descending order
        scored_docs_sorted = sorted(scored_docs, key=lambda x: x[1], reverse=True)
        
        # Add log for debugging scores
        if logger.isEnabledFor(logging.DEBUG):
            top_scores = [f"{doc.metadata.get('source_file', 'unknown')}: {score:.4f}" 
                         for doc, score in scored_docs_sorted[:5]]
            logger.debug(f"BM25 top scores: {top_scores}")
        
        return [doc for doc, score in scored_docs_sorted[:self._k]]

    get_relevant_documents = _get_relevant_documents

# For backward compatibility
BM25Retriever = EnhancedBM25Retriever

class AdaptiveEnsembleRetriever(BaseRetriever):
    """
    An adaptive retriever that adjusts weights based on query characteristics.
    """
    _retrievers: dict = PrivateAttr()
    _threshold: float = PrivateAttr()

    def __init__(self, retrievers: Dict[str, BaseRetriever], threshold: float = 0.1):
        """
        Initialize the adaptive ensemble retriever.
        
        Args:
            retrievers: Dictionary of retriever objects with keys like 'hybrid', 'semantic', 'bm25'
            threshold: Minimum score threshold for documents to be included
        """
        super().__init__()
        self._retrievers = retrievers
        self._threshold = threshold

    def _get_weights_for_query(self, query: str) -> Dict[str, float]:
        """
        Determine appropriate weights based on query characteristics.
        
        Args:
            query: The query string
            
        Returns:
            Dictionary mapping retriever names to weights
        """
        # Default weights
        weights = {
            "hybrid": 1.0,
            "semantic": 0.8,
            "bm25": 0.8,
            "mmr": 0.7
        }
        
        # Check for course codes (e.g., COMP3456)
        if re.search(r'\b[A-Z]{4}\d{4}\b', query):
            # For course codes, boost BM25 for exact matches
            logger.info("Query contains course code - boosting BM25 weight")
            weights["bm25"] = 1.5
            weights["hybrid"] = 1.2
            weights["semantic"] = 0.7
        
        # Check for keyword/definition queries (usually short)
        elif len(query.split()) <= 3:
            logger.info("Short query detected - boosting BM25 weight")
            weights["bm25"] = 1.2
            weights["hybrid"] = 1.0
            weights["semantic"] = 0.8
            
        # Check for complex conceptual queries (usually longer)
        elif len(query.split()) >= 8:
            logger.info("Complex query detected - boosting semantic weight")
            weights["semantic"] = 1.2
            weights["hybrid"] = 1.3
            weights["bm25"] = 0.7
            weights["mmr"] = 0.9  # Diversity helps with complex queries
        
        # Check for policy or requirement questions
        elif any(word in query.lower() for word in ["policy", "requirement", "rule", "regulation"]):
            logger.info("Policy/requirement query detected")
            weights["hybrid"] = 1.3
            weights["semantic"] = 1.1
            weights["mmr"] = 0.9  # Diversity helps with policy questions
        
        return weights

    def _get_relevant_documents(self, query: str, **kwargs) -> list:
        """
        Get documents relevant to the query using adaptive weighting.
        
        Args:
            query: The query string
            **kwargs: Additional arguments
            
        Returns:
            List of relevant documents
        """
        # Determine weights based on query
        weights = self._get_weights_for_query(query)
        
        # Get documents from each retriever with their weights
        doc_scores = {}
        for name, retriever in self._retrievers.items():
            if name not in weights:
                logger.warning(f"No weight defined for retriever '{name}', skipping")
                continue
                
            weight = weights[name]
            try:
                docs = retriever.get_relevant_documents(query, **kwargs)
                
                for rank, doc in enumerate(docs):
                    score = weight * (1.0 / (rank + 1))
                    
                    # Boost if there's a heading
                    if doc.metadata.get("heading", "N/A") != "N/A":
                        score *= 1.1
                    
                    # Use consistent document ID
                    if hasattr(doc, 'id'):
                        doc_id = doc.id
                    elif hasattr(doc, 'metadata') and 'source_file' in doc.metadata:
                        doc_id = doc.metadata['source_file']
                    else:
                        doc_id = id(doc)  # Fallback to object ID
                    
                    if doc_id in doc_scores:
                        doc_scores[doc_id]["score"] += score
                    else:
                        doc_scores[doc_id] = {"doc": doc, "score": score}
                        
            except Exception as e:
                logger.error(f"Error getting documents from {name} retriever: {e}")
        
        # Filter out docs below threshold
        filtered = [item["doc"] for item in doc_scores.values() if item["score"] >= self._threshold]
        
        # Sort by final ensemble score
        def get_doc_id(doc):
            if hasattr(doc, 'id'):
                return doc.id
            elif hasattr(doc, 'metadata') and 'source_file' in doc.metadata:
                return doc.metadata['source_file']
            else:
                return id(doc)
        
        sorted_docs = sorted(
            filtered,
            key=lambda d: doc_scores[get_doc_id(d)]["score"],
            reverse=True
        )
        
        # Log information about the result
        logger.info(f"AdaptiveEnsembleRetriever found {len(sorted_docs)} documents with weights {weights}")
        
        return sorted_docs

    get_relevant_documents = _get_relevant_documents

# Helper function to create the adaptive ensemble retriever
def create_adaptive_ensemble_retriever(hybrid_retriever, semantic_retriever, bm25_retriever, mmr_retriever=None):
    """Create an adaptive ensemble retriever with the provided retrievers"""
    retrievers = {
        "hybrid": hybrid_retriever,
        "semantic": semantic_retriever,
        "bm25": bm25_retriever
    }
    
    # Add MMR retriever if provided
    if mmr_retriever is not None:
        retrievers["mmr"] = mmr_retriever
        
    return AdaptiveEnsembleRetriever(retrievers)

# Keep the old EnsembleRetriever for backward compatibility
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
        logger.warning("Using deprecated EnsembleRetriever, consider using AdaptiveEnsembleRetriever instead")

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