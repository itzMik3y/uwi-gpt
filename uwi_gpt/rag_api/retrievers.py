#!/usr/bin/env python
"""
rag_api/retrievers.py - Custom retriever classes for the RAG API
with enhanced BM25 tokenization and adaptive weighting
"""

import logging
import re # Make sure re is imported
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
    _k1: float = PrivateAttr(default=1.5) # Added default
    _b: float = PrivateAttr(default=0.75)  # Added default

    # Updated __init__ to accept k1, b
    def __init__(self, documents: list, k: int = 10, use_lemmatization: bool = True, k1: float = 1.5, b: float = 0.75):
        """
        Initialize the enhanced BM25 retriever.

        Args:
            documents: List of Document objects (ensure they have page_content)
            k: Number of documents to retrieve
            use_lemmatization: Whether to use lemmatization (can be turned off for speed)
            k1: BM25 parameter k1 (controls term frequency saturation)
            b: BM25 parameter b (controls document length normalization)
        """
        super().__init__()
        if not documents:
            raise ValueError("Documents list cannot be empty for EnhancedBM25Retriever.")

        self._documents = documents
        self._k = k
        self._use_lemmatization = use_lemmatization
        self._k1 = k1 # Store k1
        self._b = b   # Store b

        # Initialize lemmatizer if needed
        if use_lemmatization:
            self._lemmatizer = WordNetLemmatizer()

        # Create a translation table to remove punctuation (apply only during tokenization)
        # translator = str.maketrans('', '', string.punctuation) # Moved translator use lower

        self._tokenized = []
        self._lemmatized = []

        # Prepare punctuation removal translator just once
        translator = str.maketrans('', '', string.punctuation)

        for doc in documents:
            if hasattr(doc, 'page_content') and isinstance(doc.page_content, str):
                text = doc.page_content.lower()
                # Remove punctuation before splitting
                text_no_punct = text.translate(translator)
                tokens = text_no_punct.split()
                self._tokenized.append(tokens)

                # Lemmatize tokens if enabled
                if use_lemmatization:
                    lemmatized_tokens = []
                    for token in tokens: # Use tokens derived from text_no_punct
                        if token: # Avoid empty strings if split creates them
                            pos = get_wordnet_pos(token)
                            lemma = self._lemmatizer.lemmatize(token, pos)
                            lemmatized_tokens.append(lemma)
                    self._lemmatized.append(lemmatized_tokens)
            else:
                # Append empty lists if document has no content or wrong type
                 self._tokenized.append([])
                 if use_lemmatization:
                     self._lemmatized.append([])


        # Create BM25 index
        corpus_to_use = self._lemmatized if use_lemmatization and self._lemmatized else self._tokenized
        if not any(corpus_to_use): # Check if corpus is empty or contains only empty lists
             logger.warning("BM25 Corpus is empty or contains only empty documents. BM25 may not function correctly.")
             # Initialize with a dummy corpus to avoid errors, though results will be poor
             self._bm25 = BM25Okapi([["dummy"]])
        else:
            logger.info(f"Initializing BM25Okapi with k1={self._k1}, b={self._b} using {'lemmatized' if use_lemmatization else 'tokenized'} corpus.")
            self._bm25 = BM25Okapi(corpus_to_use, k1=self._k1, b=self._b) # Pass k1 and b

        logger.info("Enhanced BM25Retriever initialized.")


    def _get_relevant_documents(self, query: str, **kwargs) -> list:
        """
        Get documents relevant to the query using BM25 algorithm with lemmatization.
        """
        # Clean and tokenize query, removing punctuation
        query_lower = query.lower()
        translator = str.maketrans('', '', string.punctuation)
        query_no_punct = query_lower.translate(translator)
        tokens = query_no_punct.split()

        # Lemmatize query tokens if enabled
        if self._use_lemmatization:
            lemmatized_query = []
            for token in tokens:
                if token: # Avoid empty tokens
                    pos = get_wordnet_pos(token)
                    lemma = self._lemmatizer.lemmatize(token, pos)
                    lemmatized_query.append(lemma)
            search_tokens = lemmatized_query
        else:
            search_tokens = [token for token in tokens if token] # Ensure no empty tokens

        if not search_tokens:
            logger.warning("Query produced no search tokens after processing.")
            return []

        # Get BM25 scores
        try:
            scores = self._bm25.get_scores(search_tokens)
        except Exception as e:
             logger.error(f"Error getting BM25 scores: {e}", exc_info=True)
             return [] # Return empty list on error


        # Combine documents with their scores
        # Ensure we only zip as many scores as we have documents
        num_docs = len(self._documents)
        scored_docs = list(zip(self._documents[:num_docs], scores[:num_docs]))

        # Sort documents by score in descending order
        scored_docs_sorted = sorted(scored_docs, key=lambda x: x[1], reverse=True)

        # Add log for debugging scores
        if logger.isEnabledFor(logging.DEBUG):
            top_scores = []
            for doc, score in scored_docs_sorted[:5]:
                 doc_id = getattr(doc, 'id', doc.metadata.get('source_file', 'unknown'))
                 top_scores.append(f"ID: {doc_id}, Score: {score:.4f}")
            logger.debug(f"BM25 top scores: {top_scores}")

        # Return top k documents
        return [doc for doc, score in scored_docs_sorted[:self._k]]

    get_relevant_documents = _get_relevant_documents


# For backward compatibility
BM25Retriever = EnhancedBM25Retriever

class AdaptiveEnsembleRetriever(BaseRetriever):
    """
    An adaptive retriever that adjusts weights based on query characteristics.
    """
    _retrievers: dict = PrivateAttr()
    _threshold: float = PrivateAttr() # Note: Threshold currently not applied in _get_relevant_docs logic below

    def __init__(self, retrievers: Dict[str, BaseRetriever], threshold: float = 0.1):
        """
        Initialize the adaptive ensemble retriever.
        """
        super().__init__()
        self._retrievers = retrievers
        self._threshold = threshold # Store threshold, but needs explicit application if desired

    def _is_query_about_prereqs(self, query: str) -> bool:
        """Checks if the query likely pertains to prerequisites using regex."""
        query_lower = query.lower()
        # Pattern explanation:
        # \b           - word boundary
        # (?:...)      - non-capturing group
        # pre[- ]?     - "pre" followed by optional hyphen or space
        # requisite    - the root word
        # s?           - optional 's' for plural
        # |            - OR
        # requirements? - "requirement" with optional 's'
        # \b           - word boundary
        prereq_pattern = r'\b(?:pre[- ]?requisites?|requirements?)\b'
        return bool(re.search(prereq_pattern, query_lower))

    def _get_weights_for_query(self, query: str) -> Dict[str, float]:
        """
        Determine appropriate weights based on query characteristics,
        including robust check for prerequisite variations.
        """
        # Default weights
        weights = {
            "hybrid": 1.0,
            "semantic": 0.7,
            "bm25": 0.8,
            "mmr": 0.6
        }
        query_lower = query.lower()
        is_course_code = bool(re.search(r'\b[A-Z]{4}\d{4}\b', query, re.IGNORECASE))
        is_prereq_query = self._is_query_about_prereqs(query) # Use helper function


        # Check for course codes OR prerequisite keywords (using regex check)
        if is_course_code or is_prereq_query:
            type_log = "Course Code" if is_course_code else "Prerequisite/Requirement"
            logger.info(f"{type_log} query - Boosting BM25/Hybrid weights significantly")
            weights["bm25"] = 1.8
            weights["hybrid"] = 1.6
            weights["semantic"] = 0.5
            # weights["mmr"] = 0.3

        # Keep other rules, ensure they check query_lower if needed
        elif len(query.split()) <= 3:
             logger.info("Short query detected - boosting BM25 weight")
             weights["bm25"] = 1.2
             weights["hybrid"] = 1.0
             weights["semantic"] = 0.8

        elif len(query.split()) >= 8:
             logger.info("Complex query detected - boosting semantic weight")
             weights["semantic"] = 1.2
             weights["hybrid"] = 1.3
             weights["bm25"] = 0.7
            #  weights["mmr"] = 0.9 # Restore MMR boost for complex queries

        elif any(word in query_lower for word in ["policy", "rule", "regulation"]):
             logger.info("Policy/rule query detected")
             weights["hybrid"] = 1.3
             weights["semantic"] = 1.1
            #  weights["mmr"] = 0.9 # Restore MMR boost for policy questions

        return weights

    def _get_relevant_documents(self, query: str, **kwargs) -> list:
        """
        Get documents relevant to the query using adaptive weighting and boosting,
        with robust check for prerequisite query intent.
        """
        weights = self._get_weights_for_query(query)
        doc_scores = {} # Stores {doc_id: {"doc": doc_object, "score": float}}

        # --- Extract potential course code from query for boosting ---
        query_course_code_match = re.search(r'\b([A-Z]{4}\d{4})\b', query, re.IGNORECASE)
        query_course_code = query_course_code_match.group(1).upper() if query_course_code_match else None
        query_lower = query.lower()
        # --- Use helper function to check query intent ---
        is_query_about_prereqs = self._is_query_about_prereqs(query)
        # ---

        for name, retriever in self._retrievers.items():
            if name not in weights:
                logger.warning(f"No weight defined for retriever '{name}', skipping")
                continue

            weight = weights[name]
            try:
                docs = retriever.get_relevant_documents(query, **kwargs)

                for rank, doc in enumerate(docs):
                    # --- Calculate base score ---
                    base_score_component = weight * (1.0 / (rank + 2)) # Smoothing=2

                    # --- Determine Document ID ---
                    doc_metadata = getattr(doc, 'metadata', {})
                    doc_id = getattr(doc, 'id', None) or doc_metadata.get('id', None)
                    if not doc_id:
                         source_file = doc_metadata.get("source_file", "unknown")
                         chunk_index = doc_metadata.get("chunk_index", -1)
                         doc_id = f"{source_file}_{chunk_index}" if chunk_index != -1 else id(doc)

                    # --- Apply Boosting ---
                    boost_factor = 1.0
                    doc_content_lower = getattr(doc, 'page_content', '').lower()

                    # 1. Boost for Heading
                    if doc_metadata.get("heading", "N/A") != "N/A":
                        boost_factor *= 1.1

                    # 2. Boost for Document Type
                    doc_type = doc_metadata.get("doc_type", "general")
                    if doc_type in ["course_description", "requirement"]:
                         boost_factor *= 1.2

                    # 3. Boost for Specific Course Code Match
                    associated_code = doc_metadata.get("associated_course_code", None)
                    code_match_found = False
                    if query_course_code:
                        if associated_code and associated_code.upper() == query_course_code:
                            code_match_found = True
                            boost_factor *= 1.5 # Strong boost for metadata match
                        elif query_course_code.lower() in doc_content_lower:
                             code_match_found = True # Indicate match found, maybe smaller boost later
                             boost_factor *= 1.1 # Smaller boost for just content match


                    # 4. Boost based on Prerequisite context (using query intent AND doc content)
                    # Define keywords robustly using regex for variations within the document content as well
                    prereq_keywords_pattern_doc = r'\b(?:pre[- ]?requisites?|anti[- ]?requisites?|co[- ]?requisites?|requirements?|required before)\b'
                    doc_contains_prereq_term = bool(re.search(prereq_keywords_pattern_doc, doc_content_lower))

                    if is_query_about_prereqs: # Check query intent first
                        boost_factor *= 1.2 # Base boost if query asks about prereqs
                        if doc_contains_prereq_term:
                             boost_factor *= 1.3 # Extra boost if doc also mentions them (total ~1.56x)
                             # logger.debug(f"Boosting doc {doc_id} strongly: query is prereq AND doc mentions prereq terms.")
                        # else: logger.debug(f"Boosting doc {doc_id} moderately: query is prereq.")

                    elif doc_contains_prereq_term: # Query not about prereqs, but doc mentions them
                         boost_factor *= 1.1 # Smaller boost
                         # logger.debug(f"Boosting doc {doc_id} slightly: doc mentions prereq terms.")


                    # --- Calculate Final Score & Aggregate ---
                    final_score_component = base_score_component * boost_factor
                    if doc_id in doc_scores:
                        doc_scores[doc_id]["score"] += final_score_component
                    else:
                        doc_scores[doc_id] = {"doc": doc, "score": final_score_component}

            except Exception as e:
                logger.error(f"Error getting/processing documents from {name} retriever: {e}", exc_info=True) # Added exc_info

        # --- Filter, Sort, and Return ---
        # Apply threshold if needed:
        # filtered_items = [item for item in doc_scores.values() if item["score"] >= self._threshold]
        filtered_items = list(doc_scores.values()) # Currently not applying threshold

        sorted_items = sorted(
            filtered_items,
            key=lambda item: item["score"],
            reverse=True
        )
        final_docs = [item["doc"] for item in sorted_items]

        # Optional Debugging Log
        if logger.isEnabledFor(logging.DEBUG):
             top_scores_log = []
             # Need to map final_docs back to their scores for logging
             scores_for_log = {get_doc_id(item['doc']): item['score'] for item in sorted_items[:5]}
             for doc in final_docs[:5]:
                 log_doc_id = get_doc_id(doc) # Use the same get_doc_id helper if you have it
                 score = scores_for_log.get(log_doc_id, 'N/A')
                 score_str = f"{score:.4f}" if isinstance(score, float) else str(score)
                 top_scores_log.append(f"ID: {log_doc_id}, Score: {score_str}")
             logger.debug(f"AdaptiveEnsembleRetriever top 5 final scores after boosting: {top_scores_log}")

        logger.info(f"AdaptiveEnsembleRetriever produced {len(final_docs)} documents after aggregation/boosting with weights {weights}")

        return final_docs

    get_relevant_documents = _get_relevant_documents


# Helper function (assuming it's defined elsewhere or copy it here if needed)
def get_doc_id(doc):
     """Helper to get a consistent document ID."""
     doc_metadata = getattr(doc, 'metadata', {})
     doc_id = getattr(doc, 'id', None) or doc_metadata.get('id', None) # Prefer explicit ID if available
     if not doc_id:
          # Fallback using source and chunk index if available
          source_file = doc_metadata.get("source_file", "unknown")
          chunk_index = doc_metadata.get("chunk_index", -1)
          doc_id = f"{source_file}_{chunk_index}" if chunk_index != -1 else id(doc) # Last resort: object ID
     return doc_id


# Helper function to create the adaptive ensemble retriever
def create_adaptive_ensemble_retriever(hybrid_retriever, semantic_retriever, bm25_retriever, mmr_retriever=None):
    """Create an adaptive ensemble retriever with the provided retrievers"""
    retrievers = {
        "hybrid": hybrid_retriever,
        "semantic": semantic_retriever,
        "bm25": bm25_retriever
    }

    if mmr_retriever is not None:
        retrievers["mmr"] = mmr_retriever

    # Consider passing the threshold from config if needed
    return AdaptiveEnsembleRetriever(retrievers=retrievers) # Default threshold is 0.1

# Keep the old EnsembleRetriever class definition below if needed for compatibility
# ... (EnsembleRetriever class code remains unchanged) ...
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
              try: # Add basic error handling
                 docs = retriever.get_relevant_documents(query, **kwargs)
                 for rank, doc in enumerate(docs):
                      score = weight * (1.0 / (rank + 1))
                      # Slightly boost if there's a heading
                      if getattr(doc, 'metadata', {}).get("heading", "N/A") != "N/A":
                           score *= 1.1
                      # Try to get a more stable ID
                      doc_id = getattr(doc, 'id', None) or getattr(doc, 'metadata', {}).get("source_file", id(doc))

                      if doc_id in doc_scores:
                           doc_scores[doc_id]["score"] += score
                      else:
                           doc_scores[doc_id] = {"doc": doc, "score": score}
              except Exception as e:
                 logger.error(f"Error in deprecated EnsembleRetriever with retriever {type(retriever).__name__}: {e}", exc_info=True)

         # Filter out docs below threshold
         filtered_items = [item for item in doc_scores.values() if item["score"] >= self._threshold]
         # Sort by final ensemble score
         sorted_docs = sorted(
             [item['doc'] for item in filtered_items], # Extract docs before sorting key access
             key=lambda d: doc_scores[getattr(d, 'id', None) or getattr(d, 'metadata', {}).get("source_file", id(d))]["score"],
             reverse=True
         )
         return sorted_docs

     get_relevant_documents = _get_relevant_documents

# Add to retrievers.py
class DualCollectionRetriever(BaseRetriever):
    """
    A retriever that queries two collections - one for general documents
    and another for course data - and combines the results.
    """
    _primary_retriever: Any = PrivateAttr()
    _course_retriever: Any = PrivateAttr()
    _use_reranking: bool = PrivateAttr()
    _max_documents: int = PrivateAttr()
    _max_course_documents: int = PrivateAttr()
    _cross_encoder: Any = PrivateAttr()
    
    def __init__(
        self, 
        primary_retriever: BaseRetriever, 
        course_retriever: BaseRetriever,
        use_reranking: bool = True,
        max_documents: int = 15,
        max_course_documents: int = 5,
        cross_encoder=None
    ):
        """
        Initialize the dual collection retriever.
        
        Args:
            primary_retriever: Retriever for primary documents
            course_retriever: Retriever for course documents
            use_reranking: Whether to use cross-encoder reranking
            max_documents: Maximum total documents to return
            max_course_documents: Maximum course documents to include
            cross_encoder: Optional cross-encoder for reranking
        """
        super().__init__()
        self._primary_retriever = primary_retriever
        self._course_retriever = course_retriever
        self._use_reranking = use_reranking
        self._max_documents = max_documents
        self._max_course_documents = max_course_documents
        self._cross_encoder = cross_encoder
        
    def _rerank_with_crossencoder(self, query: str, docs: list) -> list:
        """Re-rank documents using cross-encoder if available."""
        if not self._cross_encoder or not docs:
            return docs
            
        pairs = [(query, doc.page_content) for doc in docs]
        scores = self._cross_encoder.predict(pairs)
        ranked = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)
        return [doc for doc, score in ranked]
    
    def _get_relevant_documents(self, query: str, **kwargs) -> list:
        """Query both collections and combine results."""
        # Query both retrievers
        primary_docs = self._primary_retriever.get_relevant_documents(query, **kwargs)
        try:
            course_docs = self._course_retriever.get_relevant_documents(query, **kwargs)
        except Exception as e:
            # If course retriever fails, proceed with just primary docs
            logger.warning(f"Course retriever failed: {e}. Using primary docs only.")
            course_docs = []
            
        # Combine results while respecting limits
        limited_course_docs = course_docs[:self._max_course_documents]
        primary_docs_limit = self._max_documents - len(limited_course_docs)
        limited_primary_docs = primary_docs[:primary_docs_limit]
        
        # Combine and optionally rerank
        combined_docs = limited_primary_docs + limited_course_docs
        
        if self._use_reranking and self._cross_encoder:
            reranked_docs = self._rerank_with_crossencoder(query, combined_docs)
            return reranked_docs
        
        return combined_docs
        
    get_relevant_documents = _get_relevant_documents