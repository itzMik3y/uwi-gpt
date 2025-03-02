#!/usr/bin/env python
"""
ingestion.py

This script:
- Loads and cleans documents from a folder.
- Splits documents into chunks.
- Uses a JSON file for caching extracted PDF text.
- Uses joblib for caching processed document chunks.
- Builds or incrementally updates a persistent Qdrant vector store.
- Uses an incremental update strategy to add only new/changed documents.
"""

import os
import re
import concurrent.futures
import hashlib
import json
import logging
import time
from typing import List, Dict, Any
import platform
import joblib
import nltk
import pdfplumber

from transformers import AutoTokenizer
from langchain_community.document_loaders import TextLoader
from langchain_community.embeddings import SentenceTransformerEmbeddings
# Use langchain_qdrant instead of langchain_community.vectorstores
from langchain_qdrant import QdrantVectorStore, FastEmbedSparse, RetrievalMode
from langchain_core.documents import Document as LangchainDocument
from document import Document

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --- OS-specific Device Setup ---
try:
    import torch
except ImportError:
    torch = None
    logging.warning("PyTorch is not installed. Falling back to CPU.")
    
if platform.system() == "Darwin":
    if torch and torch.backends.mps.is_available():
        device = "mps"
        logging.info("Using MPS on macOS")
    else:
        device = "cpu"
        logging.info("MPS not available on macOS; using CPU")
elif platform.system() == "Windows":
    if torch and torch.cuda.is_available():
        device = "cuda"
        logging.info("Using CUDA on Windows")
    else:
        device = "cpu"
        logging.info("CUDA not available on Windows; using CPU")
else:
    if torch and torch.cuda.is_available():
        device = "cuda"
        logging.info("Using CUDA on Linux")
    else:
        device = "cpu"
        logging.info("Using CPU on Linux")

# Paths and configuration.
DOC_FOLDER = "./docs"
PERSIST_COLLECTION = "my_collection"  # Qdrant collection name
STATE_CACHE_PATH = "docs_state.json"
PDF_CACHE_PATH = "pdf_cache.json"      # JSON file for caching PDF extraction results
DOCS_CACHE_PATH = "docs_cache.joblib"    # Joblib cache for processed document chunks
QDRANT_URL = "http://localhost:6333"     # Qdrant server URL

tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-large-en-v1.5")

try:
    import fitz
except ModuleNotFoundError:
    fitz = None
    logging.warning("PyMuPDF (fitz) not found. Install it with 'pip install PyMuPDF' for fallback extraction.")

# Example structured data for degree programs.
degree_programs_data = [
    {
        "title": "B.Sc. Computer Science",
        "department": "Department of Computing",
        "faculty": "Faculty of Science and Technology",
        "description": "Four-year program covering core Computer Science topics..."
    },
    {
        "title": "B.Sc. Computer Systems Engineering",
        "department": "Department of Computing",
        "faculty": "Faculty of Science and Technology",
        "description": "Four-year program focusing on hardware, software, and system design..."
    },
]

def create_documents_from_data(data_list: List[Dict[str, Any]]) -> List[Document]:
    docs = []
    for item in data_list:
        docs.append(Document(
            page_content=item["description"],
            metadata={
                "title": item["title"],
                "department": item["department"],
                "faculty": item["faculty"]
            }
        ))
    return docs

# ----- PDF Caching and Extraction Helpers -----
def compute_checksum(filepath: str) -> str:
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()

def load_pdf_cache() -> Dict[str, str]:
    if os.path.exists(PDF_CACHE_PATH):
        try:
            with open(PDF_CACHE_PATH, "r") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Error loading PDF cache: {e}")
            return {}
    return {}

def save_pdf_cache(cache: Dict[str, str]):
    try:
        with open(PDF_CACHE_PATH, "w") as f:
            json.dump(cache, f)
    except Exception as e:
        logging.error(f"Error saving PDF cache: {e}")

def load_pdf_with_tables(filepath: str) -> str:
    texts = []
    table_settings = {
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines",
        "intersection_tolerance": 5,
    }
    try:
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                table_texts = []
                tables = page.extract_tables(table_settings=table_settings)
                if tables:
                    for table in tables:
                        if not any(cell and cell.strip() for row in table for cell in row):
                            continue
                        header = [str(cell).strip() if cell else "" for cell in table[0]]
                        rows = table[1:]
                        md_table = "| " + " | ".join(header) + " |\n"
                        md_table += "| " + " | ".join(["---"] * len(header)) + " |\n"
                        for row in rows:
                            row = [str(cell).strip() if cell else "" for cell in row]
                            md_table += "| " + " | ".join(row) + " |\n"
                        table_texts.append(md_table)
                combined = page_text.strip()
                if table_texts:
                    combined = (combined + "\n" if combined else "") + "\n".join(table_texts)
                if combined:
                    texts.append(combined)
        full_text = "\n\n".join(texts)
        if not full_text.strip() and fitz is not None:
            logging.info(f"pdfplumber extracted no text for {filepath}. Using PyMuPDF fallback.")
            doc = fitz.open(filepath)
            full_text = "\n\n".join(page.get_text("text") for page in doc)
        return full_text
    except Exception as e:
        logging.error(f"Error reading PDF {filepath}: {e}")
        return ""

def process_file(file_path: str, filename: str, cache: Dict[str, str]) -> List[Document]:
    docs = []
    if filename.lower().endswith('.pdf'):
        checksum = compute_checksum(file_path)
        if checksum in cache:
            text = cache[checksum]
            logging.info(f"Loaded cached text for {filename}")
        else:
            text = load_pdf_with_tables(file_path)
            cache[checksum] = text
            logging.info(f"Cached text for {filename}")
        if not text.strip():
            logging.warning(f"Skipping {filename} as no text was extracted.")
            return []
        docs.append(Document(page_content=text, metadata={"source_file": filename}))
    elif filename.lower().endswith('.txt'):
        loader = TextLoader(file_path)
        docs = loader.load()
    return docs

def get_docs_folder_state(doc_folder: str) -> Dict[str, float]:
    state = {}
    for filename in os.listdir(doc_folder):
        if filename.lower().endswith(('.pdf', '.txt')):
            full_path = os.path.join(doc_folder, filename)
            state[filename] = os.path.getmtime(full_path)
    return state

def load_and_clean_documents(doc_folder: str) -> List[Document]:
    start_time = time.perf_counter()
    heading_regex = re.compile(r"^(?:[A-Z0-9 .-]+)$")
    documents = []
    pdf_cache = load_pdf_cache()
    file_list = [fn for fn in os.listdir(doc_folder) if fn.lower().endswith(('.pdf', '.txt'))]
    chunk_size = 3
    for i in range(0, len(file_list), chunk_size):
        batch = file_list[i:i + chunk_size]
        with concurrent.futures.ProcessPoolExecutor() as executor:
            futures = {
                executor.submit(process_file, os.path.join(doc_folder, filename), filename, pdf_cache): filename
                for filename in batch
            }
            for future in concurrent.futures.as_completed(futures):
                filename = futures[future]
                try:
                    docs = future.result()
                except Exception as exc:
                    logging.error(f"Error processing {filename}: {exc}")
                    continue
                for doc in docs:
                    cleaned = re.sub(r'[ \t]{2,}', ' ', doc.page_content).strip()
                    if not cleaned:
                        continue
                    doc.page_content = cleaned
                    possible_heading = cleaned.split('\n', 1)[0].strip()
                    doc.metadata["heading"] = possible_heading if heading_regex.match(possible_heading) else "N/A"
                    if "source_file" not in doc.metadata:
                        doc.metadata["source_file"] = filename
                    documents.append(doc)
    save_pdf_cache(pdf_cache)
    end_time = time.perf_counter()
    logging.info(f"Document loading and cleaning took {end_time - start_time:.2f} seconds")
    return documents

def improved_document_chunking(
    documents: List[Document], 
    target_chunk_size: int = 512, 
    chunk_overlap: int = 50,
    respect_section_boundaries: bool = True,
    preserve_metadata: bool = True
) -> List[Document]:
    """
    Advanced document chunking with multiple improvements.
    
    Args:
        documents: List of Document objects to chunk
        target_chunk_size: Target number of tokens per chunk
        chunk_overlap: Number of tokens to overlap between chunks
        respect_section_boundaries: Whether to respect section headers as chunk boundaries
        preserve_metadata: Whether to preserve and enhance metadata
        
    Returns:
        List of chunked Document objects
    """
    start_time = time.perf_counter()
    
    # Ensure NLTK resources are available
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        nltk.download('punkt')
    
    # Improved section header detection
    header_patterns = [
        # Numbered sections like "1.2.3 Section Name"
        r'^\s*\d+(?:\.\d+)*\s+[A-Z][A-Za-z\s]+\s*$',
        # Capitalized headings
        r'^\s*[A-Z][A-Z\s]{2,}[A-Z]\s*$',
        # Title case headings like "Section Title Here"
        r'^\s*(?:[A-Z][a-z]+\s+){2,}[A-Z][a-z]+\s*$'
    ]
    header_regex = re.compile('|'.join(f'({pattern})' for pattern in header_patterns))
    
    # Additional paragraph boundary patterns
    paragraph_breaks = [
        r'\n\s*\n',      # Double line breaks
        r'\n\t',         # Tabbed new line
        r'\n\s{4,}',     # Indented text (4+ spaces)
    ]
    paragraph_regex = re.compile('|'.join(paragraph_breaks))
    
    new_docs = []
    
    for doc in documents:
        # Extract any headings from metadata if available
        current_heading = doc.metadata.get('heading', None)
        
        # Split text into paragraphs first for better semantic grouping
        paragraphs = paragraph_regex.split(doc.page_content)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
        
        current_chunk = []
        current_chunk_text = ""
        current_token_count = 0
        
        for paragraph in paragraphs:
            # Check if this paragraph is a header
            if respect_section_boundaries and header_regex.match(paragraph):
                # Complete previous chunk if it exists
                if current_chunk:
                    new_doc = Document(
                        page_content=" ".join(current_chunk),
                        metadata=doc.metadata.copy()
                    )
                    if current_heading:
                        new_doc.metadata['heading'] = current_heading
                    new_docs.append(new_doc)
                    
                # Update the current heading
                current_heading = paragraph
                current_chunk = []
                current_chunk_text = ""
                current_token_count = 0
                continue
            
            # Get sentences from paragraph
            sentences = nltk.sent_tokenize(paragraph)
            
            for sentence in sentences:
                # Ensure we're using the same tokenizer consistently
                tokens = tokenizer.tokenize(sentence)
                sentence_token_count = len(tokens)
                
                # If this sentence alone exceeds chunk size, split it further
                if sentence_token_count > target_chunk_size:
                    if current_chunk:
                        new_doc = Document(
                            page_content=" ".join(current_chunk),
                            metadata=doc.metadata.copy()
                        )
                        if current_heading:
                            new_doc.metadata['heading'] = current_heading
                        new_docs.append(new_doc)
                        current_chunk = []
                        current_chunk_text = ""
                        current_token_count = 0
                    
                    # Process long sentence in smaller pieces
                    words = sentence.split()
                    current_piece = []
                    current_piece_count = 0
                    
                    for word in words:
                        word_tokens = tokenizer.tokenize(word)
                        if current_piece_count + len(word_tokens) > target_chunk_size and current_piece:
                            new_doc = Document(
                                page_content=" ".join(current_piece),
                                metadata=doc.metadata.copy()
                            )
                            if current_heading:
                                new_doc.metadata['heading'] = current_heading
                            new_docs.append(new_doc)
                            current_piece = [word]
                            current_piece_count = len(word_tokens)
                        else:
                            current_piece.append(word)
                            current_piece_count += len(word_tokens)
                    
                    if current_piece:
                        current_chunk = current_piece
                        current_token_count = current_piece_count
                        current_chunk_text = " ".join(current_piece)
                
                # Regular case - add sentence to current chunk if it fits
                elif current_token_count + sentence_token_count > target_chunk_size:
                    # Finish current chunk
                    new_doc = Document(
                        page_content=current_chunk_text,
                        metadata=doc.metadata.copy()
                    )
                    if current_heading:
                        new_doc.metadata['heading'] = current_heading
                    new_docs.append(new_doc)
                    
                    # Handle overlap by including some sentences from previous chunk
                    if chunk_overlap > 0 and len(current_chunk) > 1:
                        # Find overlap sentences that don't exceed the overlap token count
                        overlap_sentences = []
                        overlap_token_count = 0
                        
                        for prev_sentence in reversed(current_chunk):
                            prev_tokens = tokenizer.tokenize(prev_sentence)
                            if overlap_token_count + len(prev_tokens) <= chunk_overlap:
                                overlap_sentences.insert(0, prev_sentence)
                                overlap_token_count += len(prev_tokens)
                            else:
                                break
                        
                        current_chunk = overlap_sentences + [sentence]
                        current_token_count = overlap_token_count + sentence_token_count
                        current_chunk_text = " ".join(current_chunk)
                    else:
                        current_chunk = [sentence]
                        current_token_count = sentence_token_count
                        current_chunk_text = sentence
                else:
                    current_chunk.append(sentence)
                    current_token_count += sentence_token_count
                    if current_chunk_text:
                        current_chunk_text += " " + sentence
                    else:
                        current_chunk_text = sentence
        
        # Add the last chunk if it exists
        if current_chunk:
            new_doc = Document(
                page_content=current_chunk_text,
                metadata=doc.metadata.copy()
            )
            if current_heading:
                new_doc.metadata['heading'] = current_heading
            new_docs.append(new_doc)
    
    end_time = time.perf_counter()
    logging.info(f"Improved chunking completed in {end_time - start_time:.2f} seconds. Created {len(new_docs)} chunks.")
    
    return new_docs

def incremental_update(doc_folder: str, state_cache_path: str) -> List[Document]:
    current_state = get_docs_folder_state(doc_folder)
    if os.path.exists(state_cache_path):
        with open(state_cache_path, "r") as f:
            previous_state = json.load(f)
    else:
        previous_state = {}
    new_files = [fname for fname, mtime in current_state.items()
                 if fname not in previous_state or mtime > previous_state.get(fname, 0)]
    logging.info(f"Found {len(new_files)} new/modified files.")
    new_docs = []
    pdf_cache = load_pdf_cache()
    for filename in new_files:
        full_path = os.path.join(doc_folder, filename)
        docs_from_file = process_file(full_path, filename, pdf_cache)
        new_docs.extend(docs_from_file)
    if new_docs:
        new_docs = improved_document_chunking(
                        new_docs,
                        target_chunk_size=512,
                        chunk_overlap=50,
                        respect_section_boundaries=True,
                        preserve_metadata=True
                    )

    with open(state_cache_path, "w") as f:
        json.dump(current_state, f)
    save_pdf_cache(pdf_cache)
    return new_docs

# Function to convert custom Document to LangChain Document
def convert_to_langchain_docs(docs):
    """Convert custom Document objects to LangChain Document objects."""
    langchain_docs = []
    for doc in docs:
        langchain_docs.append(LangchainDocument(
            page_content=doc.page_content,
            metadata=doc.metadata
        ))
    return langchain_docs

def initialize_documents_and_vector_store(doc_folder: str = "./docs",
                                          collection_name: str = "my_collection",
                                          docs_cache_path: str = "docs_cache.joblib",
                                          state_cache_path: str = "docs_state.json",
                                          url: str = "http://localhost:6333"):
    init_start = time.perf_counter()
    
    # 1. Initialize the dense embedding model with OS-specific device settings
    dense_embeddings = SentenceTransformerEmbeddings(
        model_name="BAAI/bge-large-en-v1.5",
        model_kwargs={"trust_remote_code": True, "device": device}
    )
    
    # 2. Initialize the sparse embedding model
    sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")
    
    # 3. Compute current state of docs folder
    current_state = get_docs_folder_state(doc_folder)
    
    # 4. Load previous state if available
    previous_state = {}
    if os.path.exists(state_cache_path):
        try:
            with open(state_cache_path, "r") as f:
                previous_state = json.load(f)
        except Exception as e:
            logging.error(f"Error loading state cache: {e}")
    
    # 5. Determine if reprocessing is needed
    reprocess = (current_state != previous_state)
    
    # Check if the Qdrant collection exists
    from qdrant_client import QdrantClient
    client = QdrantClient(url=url)
    try:
        collections = client.get_collections().collections
        collection_exists = any(collection.name == collection_name for collection in collections)
    except Exception as e:
        logging.error(f"Error connecting to Qdrant: {e}")
        collection_exists = False
    
    if collection_exists and not reprocess:
        logging.info("Persistent vector store found. Loading from Qdrant...")
        
        try:
            # Try to load with hybrid search capability
            vector_store = QdrantVectorStore.from_existing_collection(
                embedding=dense_embeddings,
                sparse_embedding=sparse_embeddings,
                collection_name=collection_name,
                url=url,
                retrieval_mode=RetrievalMode.HYBRID
            )
            logging.info("Successfully loaded Qdrant collection with hybrid search support.")
        except Exception as e:
            if "does not contain sparse vectors" in str(e):
                logging.warning(f"Collection exists but doesn't support hybrid search: {e}")
                logging.info("Will recreate the collection with hybrid search support.")
                collection_exists = False  # Force recreation
            else:
                raise  # If it's a different error, propagate it
        
        if collection_exists:  # If we successfully loaded the collection
            if os.path.exists(docs_cache_path):
                docs = joblib.load(docs_cache_path)
                logging.info(f"Loaded {len(docs)} cached document chunks.")
            else:
                logging.warning("No document cache found. Rebuilding documents from source...")
                documents = load_and_clean_documents(doc_folder)
                logging.info(f"Loaded {len(documents)} documents.")
                metadata_docs = create_documents_from_data(degree_programs_data)
                documents.extend(metadata_docs)
                docs = improved_document_chunking(
                            documents,
                            target_chunk_size=512,
                            chunk_overlap=50,
                            respect_section_boundaries=True,
                            preserve_metadata=True
                        )
                logging.info(f"Created {len(docs)} document chunks after splitting.")
                joblib.dump(docs, docs_cache_path)
    
    # If collection doesn't exist, needs to be recreated for hybrid search, or documents have changed
    if not collection_exists or reprocess:
        logging.info("Loading and cleaning documents...")
        documents = load_and_clean_documents(doc_folder)
        logging.info(f"Loaded {len(documents)} documents.")
        metadata_docs = create_documents_from_data(degree_programs_data)
        documents.extend(metadata_docs)
        docs = improved_document_chunking(
                    documents,
                    target_chunk_size=512,
                    chunk_overlap=50,
                    respect_section_boundaries=True,
                    preserve_metadata=True
                )
        logging.info(f"Created {len(docs)} document chunks after splitting.")
        
        # Convert to LangChain documents format
        langchain_docs = convert_to_langchain_docs(docs)
        
        logging.info("Building new vector store using QdrantVectorStore with hybrid search capability...")
        vector_store = QdrantVectorStore.from_documents(
            langchain_docs,
            embedding=dense_embeddings,
            sparse_embedding=sparse_embeddings,
            url=url,
            collection_name=collection_name,
            force_recreate=True,
            retrieval_mode=RetrievalMode.HYBRID
        )
        joblib.dump(docs, docs_cache_path)
    
    try:
        with open(state_cache_path, "w") as f:
            json.dump(current_state, f)
    except Exception as e:
        logging.error(f"Error saving state cache: {e}")
    
    init_end = time.perf_counter()
    logging.info(f"Initialization took {init_end - init_start:.2f} seconds")
    return docs, vector_store, dense_embeddings, sparse_embeddings

def load_existing_qdrant_store(
    collection_name: str = "my_collection",
    docs_cache_path: str = "docs_cache.joblib",
    qdrant_url: str = "http://localhost:6333",
    force_recreate: bool = False
):
    """
    Loads the existing Qdrant vector store and cached documents.
    If the collection doesn't support hybrid search, it will recreate it if force_recreate is True.
    
    Args:
        collection_name: Name of the Qdrant collection
        docs_cache_path: Path to the cached documents
        qdrant_url: URL of the Qdrant server
        force_recreate: Whether to recreate the collection if it doesn't support hybrid search
        
    Returns:
        Tuple of (docs, vector_store, dense_embeddings, sparse_embeddings)
    """
    logging.info(f"Attempting to load Qdrant collection '{collection_name}'...")
    
    # Initialize embeddings
    dense_embeddings = SentenceTransformerEmbeddings(
        model_name="BAAI/bge-large-en-v1.5",
        model_kwargs={"trust_remote_code": True, "device": device}
    )
    
    # Initialize sparse embeddings
    sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")
    
    # Load cached documents
    if not os.path.exists(docs_cache_path):
        raise FileNotFoundError(f"Document cache not found: {docs_cache_path}. Please run ingestion first.")
    
    docs = joblib.load(docs_cache_path)
    logging.info(f"Loaded {len(docs)} cached document chunks.")
    
    # Check if the collection exists and supports hybrid search
    try:
        vector_store = QdrantVectorStore.from_existing_collection(
            embedding=dense_embeddings,
            sparse_embedding=sparse_embeddings,
            collection_name=collection_name,
            url=qdrant_url,
            retrieval_mode=RetrievalMode.HYBRID
        )
        logging.info(f"Successfully loaded collection '{collection_name}' with hybrid search support.")
        return docs, vector_store, dense_embeddings, sparse_embeddings
    except Exception as e:
        error_message = str(e)
        if "does not contain sparse vectors" in error_message and force_recreate:
            logging.warning(f"Collection '{collection_name}' doesn't support hybrid search. Recreating collection...")
            
            # Convert to LangChain documents format
            from langchain_core.documents import Document as LangchainDocument
            langchain_docs = []
            for doc in docs:
                langchain_docs.append(LangchainDocument(
                    page_content=doc.page_content,
                    metadata=doc.metadata
                ))
            
            # Create a new collection with hybrid search support
            vector_store = QdrantVectorStore.from_documents(
                langchain_docs,
                embedding=dense_embeddings,
                sparse_embedding=sparse_embeddings,
                url=qdrant_url,
                collection_name=collection_name,
                force_recreate=True,
                retrieval_mode=RetrievalMode.HYBRID
            )
            logging.info(f"Successfully recreated collection '{collection_name}' with hybrid search support.")
            return docs, vector_store, dense_embeddings, sparse_embeddings
        else:
            # If force_recreate is False or it's a different error, just raise it
            logging.error(f"Error loading Qdrant collection: {error_message}")
            raise
# Function to perform hybrid search
def hybrid_search(query: str, vector_store, top_k: int = 4):
    """
    Perform hybrid search (combining dense and sparse vectors) using QdrantVectorStore.
    
    Args:
        query: The search query string
        vector_store: The initialized QdrantVectorStore with hybrid capability
        top_k: Number of results to return
        
    Returns:
        List of retrieved documents
    """
    # Make sure the vector store is using hybrid search mode
    if hasattr(vector_store, 'retrieval_mode'):
        vector_store.retrieval_mode = RetrievalMode.HYBRID
    
    # Create a retriever with the specified k
    retriever = vector_store.as_retriever(search_kwargs={"k": top_k})
    
    # Get relevant documents
    results = retriever.get_relevant_documents(query)
    return results

# Function to compare different search modes
def test_search_modes(query: str, vector_store, top_k: int = 4):
    """
    Test different search modes (dense, sparse, hybrid) and compare results.
    
    Args:
        query: The search query string
        vector_store: The initialized QdrantVectorStore
        top_k: Number of results to return
        
    Returns:
        Dict containing results from each search mode
    """
    results = {}
    
    # Test dense search
    vector_store.retrieval_mode = RetrievalMode.DENSE
    dense_retriever = vector_store.as_retriever(search_kwargs={"k": top_k})
    results['dense'] = dense_retriever.get_relevant_documents(query)
    
    # Test sparse search
    vector_store.retrieval_mode = RetrievalMode.SPARSE
    sparse_retriever = vector_store.as_retriever(search_kwargs={"k": top_k})
    results['sparse'] = sparse_retriever.get_relevant_documents(query)
    
    # Test hybrid search
    vector_store.retrieval_mode = RetrievalMode.HYBRID
    hybrid_retriever = vector_store.as_retriever(search_kwargs={"k": top_k})
    results['hybrid'] = hybrid_retriever.get_relevant_documents(query)
    
    return results

if __name__ == "__main__":
    # Install required dependencies if not already installed
    try:
        import langchain_qdrant
    except ImportError:
        import subprocess
        print("Installing required dependencies...")
        subprocess.check_call(["pip", "install", "langchain-qdrant", "fastembeddings"])
        print("Dependencies installed successfully.")
        
    # Initialize or load documents and vector store
    docs, vector_store, dense_embeddings, sparse_embeddings = initialize_documents_and_vector_store(
        doc_folder=DOC_FOLDER,
        collection_name=PERSIST_COLLECTION,
        url=QDRANT_URL
    )
    
    # # Example search query
    # query = "computer science curriculum"
    
    # # Test different search modes
    # print("\n=== Testing Different Search Modes ===")
    # search_results = test_search_modes(query, vector_store)
    
    # # Print results from each mode
    # for mode, results in search_results.items():
    #     print(f"\n--- {mode.upper()} SEARCH RESULTS ---")
    #     for i, doc in enumerate(results):
    #         print(f"Result {i+1}:")
    #         print(f"Content: {doc.page_content[:150]}...")
    #         print(f"Metadata: {doc.metadata}")
    #         print("-" * 50)
    
    # # Print hybrid search results
    # print("\n=== Hybrid Search Results ===")
    # hybrid_results = hybrid_search(query, vector_store, top_k=5)
    # for i, doc in enumerate(hybrid_results):
    #     print(f"Result {i+1}:")
    #     print(f"Content: {doc.page_content[:150]}...")
    #     print(f"Metadata: {doc.metadata}")
    #     print("-" * 50)
    
    print("\nIngestion and search testing completed successfully.")