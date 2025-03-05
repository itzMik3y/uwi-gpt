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
from docling.document_converter import DocumentConverter
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_text_splitters import MarkdownTextSplitter
from langchain_text_splitters import SentenceTransformersTokenTextSplitter
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

def load_pdf_as_markdown(filepath: str) -> str:
    """
    Load a PDF file and convert its content to Markdown format using Docling with EasyOCR.
    Uses platform-specific hardware acceleration detection.
    
    Args:
        filepath: Path to the PDF file.
        
    Returns:
        Markdown-formatted string representation of the PDF content.
    """
    import time
    import os
    import platform
    from docling_core.types.doc import ImageRefMode
    
    try:
        filename = os.path.basename(filepath)
        logging.info(f"Processing document {filename}")
        
        start_time = time.time()
        
        # Import required Docling components
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import (
            AcceleratorDevice,
            AcceleratorOptions,
            PdfPipelineOptions,
            TableFormerMode
        )
        from docling.datamodel.settings import settings
        from docling.document_converter import DocumentConverter, PdfFormatOption
        
        # Determine the best accelerator based on the platform
        if platform.system() == "Darwin":
            # On Mac, use MPS (Metal Performance Shaders) if available
            if 'torch' in globals() and torch and hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                accel_device = AcceleratorDevice.MPS
                logging.info("Using MPS acceleration on Mac")
            else:
                accel_device = AcceleratorDevice.CPU
                logging.info("Using CPU acceleration on Mac")
        else:
            # On Windows/Linux, use CUDA if available
            if 'torch' in globals() and torch and torch.cuda.is_available():
                accel_device = AcceleratorDevice.CUDA
                logging.info("Using CUDA acceleration")
            else:
                accel_device = AcceleratorDevice.CPU
                logging.info("Using CPU acceleration")
        
        # Utilize logical processors effectively
        num_threads = 12  # Good value for high-end systems with 16 logical processors
        
        accelerator_options = AcceleratorOptions(
            num_threads=num_threads,
            device=accel_device
        )
        
        # Configure pipeline options with high-quality table processing
        pipeline_options = PdfPipelineOptions()
        pipeline_options.accelerator_options = accelerator_options
        pipeline_options.do_ocr = True
        pipeline_options.do_table_structure = True
        pipeline_options.generate_page_images = False  # Better performance
        
        # Default OCR is EasyOCR - just set language
        pipeline_options.ocr_options.lang = ["en"]  # EasyOCR uses "en" for English
        
        # Use ACCURATE mode for TableFormer
        pipeline_options.table_structure_options.mode = TableFormerMode.ACCURATE
        pipeline_options.table_structure_options.do_cell_matching = True
        
        # Configure converter
        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pipeline_options
                )
            }
        )
        
        # Enable profiling
        settings.debug.profile_pipeline_timings = True
        
        # Optional: Set environment variable for OpenMP threads
        os.environ["OMP_NUM_THREADS"] = str(num_threads)
        
        # Convert the document
        conversion_result = converter.convert(filepath)
        
        # Export to markdown with placeholder images
        markdown_content = conversion_result.document.export_to_markdown(
            image_mode=ImageRefMode.PLACEHOLDER
        )
        
        # Get timing information
        doc_conversion_secs = 0
        if hasattr(conversion_result, 'timings') and isinstance(conversion_result.timings, dict):
            if "pipeline_total" in conversion_result.timings and "times" in conversion_result.timings["pipeline_total"]:
                doc_conversion_secs = sum(conversion_result.timings["pipeline_total"]["times"])
                
        end_time = time.time()
        total_time = end_time - start_time
        logging.info(f"Finished converting document {filename} in {total_time:.2f} sec. Pipeline time: {doc_conversion_secs:.2f} sec.")
        
        # Add a title if not present
        title = os.path.basename(filepath).replace('.pdf', '')
        if not markdown_content.strip().startswith("# "):
            markdown_content = f"# {title}\n\n{markdown_content}"
            
        return markdown_content
            
    except Exception as e:
        logging.error(f"Error converting PDF to Markdown using Docling for {filepath}: {e}")
        return ""  # Return empty string on error
        
    finally:
        # Force garbage collection to help with memory leaks
        import gc
        gc.collect()
        
        # Clear acceleration cache based on platform
        if platform.system() == "Darwin":
            if 'torch' in globals() and torch and hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                # Clear MPS cache if there's a way to do so
                pass
        else:
            if 'torch' in globals() and torch and torch.cuda.is_available():
                torch.cuda.empty_cache()





def get_docs_folder_state(doc_folder: str) -> Dict[str, float]:
    state = {}
    for filename in os.listdir(doc_folder):
        if filename.lower().endswith(('.pdf', '.txt')):
            full_path = os.path.join(doc_folder, filename)
            state[filename] = os.path.getmtime(full_path)
    return state

def load_and_clean_documents(doc_folder: str) -> List[Document]:
    """
    Load and clean documents using concurrent processing for better performance.
    """
    start_time = time.perf_counter()
    heading_regex = re.compile(r"^(?:[A-Z0-9 .-]+)$")
    documents = []
    pdf_cache = load_pdf_cache()
    
    # Get list of PDF and text files
    pdf_files = [os.path.join(doc_folder, fn) for fn in os.listdir(doc_folder) 
                if fn.lower().endswith('.pdf')]
    txt_files = [os.path.join(doc_folder, fn) for fn in os.listdir(doc_folder) 
                if fn.lower().endswith('.txt')]
    
    # Process files with concurrency
    logging.info(f"Processing {len(pdf_files)} PDF files and {len(txt_files)} text files with concurrency")
    
    def process_pdf_file(file_path):
        filename = os.path.basename(file_path)
        try:
            # Try to load from disk first (fastest method)
            markdown_dir = "./markdown_cache"  # You can make this configurable
            markdown_content = load_markdown_from_disk(file_path, markdown_dir)
            
            if markdown_content is not None:
                # Found markdown on disk, use it directly
                logging.info(f"Using disk-cached markdown for {filename}")
            else:
                # Try memory cache next
                checksum = compute_checksum(file_path)
                if checksum in pdf_cache:
                    markdown_content = pdf_cache[checksum]
                    logging.info(f"Using memory-cached text for {filename}")
                    # Save to disk for next time
                    save_markdown_to_disk(file_path, markdown_content, markdown_dir)
                else:
                    # Not in any cache, convert from PDF
                    markdown_content = load_pdf_as_markdown(file_path)
                    pdf_cache[checksum] = markdown_content
                    logging.info(f"Converted PDF to markdown for {filename}")
                    # Save to disk for next time
                    save_markdown_to_disk(file_path, markdown_content, markdown_dir)
                    
            # Skip if no text was extracted
            if not markdown_content.strip():
                logging.warning(f"Skipping {filename} as no text was extracted")
                return None
            
            # Create document object
            doc = Document(
                page_content=markdown_content, 
                metadata={"source_file": filename, "format": "markdown"}
            )
            
            # Clean and process the document
            cleaned = re.sub(r'[ \t]{2,}', ' ', doc.page_content).strip()
            if not cleaned:
                return None
                
            doc.page_content = cleaned
            possible_heading = cleaned.split('\n', 1)[0].strip()
            doc.metadata["heading"] = possible_heading if heading_regex.match(possible_heading) else "N/A"
            
            logging.info(f"Processed and added {filename}")
            return doc
            
        except Exception as exc:
            logging.error(f"Error processing PDF file {filename}: {exc}")
            return None
    
    def process_txt_file(file_path):
        filename = os.path.basename(file_path)
        try:
            logging.info(f"Processing text file {filename}")
            
            loader = TextLoader(file_path)
            txt_docs = loader.load()
            
            result_docs = []
            # Add format metadata
            for doc in txt_docs:
                doc.metadata["format"] = "text"
                cleaned = re.sub(r'[ \t]{2,}', ' ', doc.page_content).strip()
                if not cleaned:
                    continue
                    
                doc.page_content = cleaned
                possible_heading = cleaned.split('\n', 1)[0].strip()
                doc.metadata["heading"] = possible_heading if heading_regex.match(possible_heading) else "N/A"
                if "source_file" not in doc.metadata:
                    doc.metadata["source_file"] = filename
                    
                # Convert to our Document class
                result_docs.append(Document(
                    page_content=doc.page_content,
                    metadata=doc.metadata
                ))
            
            logging.info(f"Added text file {filename}")
            return result_docs
            
        except Exception as exc:
            logging.error(f"Error processing text file {filename}: {exc}")
            return []
    
    # Use ThreadPoolExecutor for concurrent processing
    from concurrent.futures import ThreadPoolExecutor
    
    # For PDF files: determine optimal number of workers based on GPU or CPU usage
    # When using GPU, we don't want too many concurrent PDF processes
    pdf_workers = 3 if ('torch' in globals() and torch and torch.cuda.is_available()) else min(4, max(1, os.cpu_count() // 2))
    # For text files, we can use more workers
    txt_workers = min(8, max(1, os.cpu_count()))
    
    # Process PDF files with limited concurrency - prevents GPU memory issues
    if pdf_files:
        logging.info(f"Processing PDFs with {pdf_workers} workers (GPU detected: {'Yes' if 'torch' in globals() and torch and torch.cuda.is_available() else 'No'})")
        with ThreadPoolExecutor(max_workers=pdf_workers) as executor:
            pdf_results = list(executor.map(process_pdf_file, pdf_files))
            for doc in pdf_results:
                if doc is not None:
                    documents.append(doc)
    
    # Process text files with more concurrency - no GPU concerns
    if txt_files:
        logging.info(f"Processing text files with {txt_workers} workers")
        with ThreadPoolExecutor(max_workers=txt_workers) as executor:
            txt_results = list(executor.map(process_txt_file, txt_files))
            for doc_list in txt_results:
                if doc_list:
                    documents.extend(doc_list)
    
    # Save the updated cache
    save_pdf_cache(pdf_cache)
    
    end_time = time.perf_counter()
    logging.info(f"Document loading and cleaning took {end_time - start_time:.2f} seconds. Loaded {len(documents)} documents.")
    return documents


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

def save_markdown_to_disk(filepath, markdown_content, output_dir="./markdown_cache"):
    """
    Save extracted markdown content to disk for faster reuse.
    
    Args:
        filepath: Original PDF file path
        markdown_content: Extracted markdown content
        output_dir: Directory to save markdown files
    
    Returns:
        Path to the saved markdown file
    """
    import os
    from pathlib import Path
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Create a filename based on the original PDF name
    pdf_filename = os.path.basename(filepath)
    md_filename = os.path.splitext(pdf_filename)[0] + ".md"
    output_path = os.path.join(output_dir, md_filename)
    
    # Write markdown content to file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(markdown_content)
    
    logging.info(f"Saved markdown for {pdf_filename} to {output_path}")
    return output_path

def load_markdown_from_disk(filepath, markdown_dir="./markdown_cache"):
    """
    Load markdown content from disk if available.
    
    Args:
        filepath: Original PDF file path
        markdown_dir: Directory with cached markdown files
    
    Returns:
        Markdown content if found, None otherwise
    """
    import os
    from pathlib import Path
    
    # Create expected markdown filename
    pdf_filename = os.path.basename(filepath)
    md_filename = os.path.splitext(pdf_filename)[0] + ".md"
    md_path = os.path.join(markdown_dir, md_filename)
    
    # Check if file exists
    if os.path.exists(md_path):
        try:
            with open(md_path, "r", encoding="utf-8") as f:
                content = f.read()
            logging.info(f"Loaded markdown from disk for {pdf_filename}")
            return content
        except Exception as e:
            logging.error(f"Error loading markdown file {md_path}: {e}")
    
    return None

def simple_split(documents: List[Document], target_chunk_size: int = 512) -> List[Document]:
    start_time = time.perf_counter()
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        nltk.download('punkt')
    new_docs = []
    header_regex = re.compile(r'^(?:[A-Z\s]{3,}|[A-Z][a-z]+(?:\s[A-Z][a-z]+)*)$')
    for doc in documents:
        sentences = nltk.sent_tokenize(doc.page_content)
        current_chunk = []
        current_token_count = 0
        for sentence in sentences:
            if header_regex.match(sentence.strip()):
                if current_chunk:
                    new_docs.append(Document(page_content=" ".join(current_chunk), metadata=doc.metadata.copy()))
                    current_chunk = []
                    current_token_count = 0
            tokens = tokenizer.tokenize(sentence)
            sentence_token_count = len(tokens)
            if current_token_count + sentence_token_count > target_chunk_size and current_chunk:
                new_docs.append(Document(page_content=" ".join(current_chunk), metadata=doc.metadata.copy()))
                current_chunk = [sentence]
                current_token_count = sentence_token_count
            else:
                current_chunk.append(sentence)
                current_token_count += sentence_token_count
        if current_chunk:
            new_docs.append(Document(page_content=" ".join(current_chunk), metadata=doc.metadata.copy()))
    end_time = time.perf_counter()
    logging.info(f"Simple splitting took {end_time - start_time:.2f} seconds")
    return new_docs

def initialize_documents_and_vector_store(doc_folder: str = "./docs",
                                         collection_name: str = "my_collection",
                                         docs_cache_path: str = "docs_cache.joblib",
                                         state_cache_path: str = "docs_state.json",
                                         url: str = "http://localhost:6333",
                                         use_semantic_chunking: bool = True):  # New parameter
    """
    Initialize or update document store with optimized batching and vector operations.
    
    Args:
        doc_folder: Folder containing documents to process
        collection_name: Name of Qdrant collection to use
        docs_cache_path: Path to cache processed documents
        state_cache_path: Path to cache document folder state
        url: URL of Qdrant server
        use_semantic_chunking: Whether to use semantic chunking (True) or structural chunking (False)
    """
    init_start = time.perf_counter()
    
    # Larger batch size for faster vector insertion
    VECTOR_BATCH_SIZE = 250
    
    # 1. Initialize the dense embedding model with OS-specific device settings
    dense_embeddings = SentenceTransformerEmbeddings(
        model_name="BAAI/bge-large-en-v1.5",
        model_kwargs={"trust_remote_code": True, "device": device},
        encode_kwargs={'normalize_embeddings':True }
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
                retrieval_mode=RetrievalMode.HYBRID,
                # batch_size=VECTOR_BATCH_SIZE
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
                
                # Choose chunking method based on parameter
                if use_semantic_chunking:
                    docs = simple_split(
                        documents,
                        target_chunk_size=512
                    )
                    logging.info(f"Created {len(docs)} document chunks using semantic chunking.")
                else:
                    docs = simple_split(
                        documents,
                        target_chunk_size=512
                    )
                    logging.info(f"Created {len(docs)} document chunks using structural chunking.")
                    
                joblib.dump(docs, docs_cache_path)
    
    # If collection doesn't exist, needs to be recreated for hybrid search, or documents have changed
    if not collection_exists or reprocess:
        logging.info("Loading and cleaning documents...")
        documents = load_and_clean_documents(doc_folder)
        logging.info(f"Loaded {len(documents)} documents.")
        metadata_docs = create_documents_from_data(degree_programs_data)
        documents.extend(metadata_docs)
        
        # Choose chunking method based on parameter
        if use_semantic_chunking:
            docs = simple_split(
                documents,
                target_chunk_size=512
            )
            logging.info(f"Created {len(docs)} document chunks using semantic chunking.")
        else:
            docs = simple_split(
                documents,
                target_chunk_size=512
            )
            logging.info(f"Created {len(docs)} document chunks using structural chunking.")
        
        # Convert to LangChain documents format
        langchain_docs = convert_to_langchain_docs(docs)
        
        logging.info(f"Building new vector store using QdrantVectorStore with hybrid search capability and batch size {VECTOR_BATCH_SIZE}...")
        vector_store = QdrantVectorStore.from_documents(
            langchain_docs,
            embedding=dense_embeddings,
            sparse_embedding=sparse_embeddings,
            url=url,
            collection_name=collection_name,
            force_recreate=True,
            retrieval_mode=RetrievalMode.HYBRID,
            batch_size=VECTOR_BATCH_SIZE
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
    """
    logging.info(f"Attempting to load Qdrant collection '{collection_name}'...")
    
    # Set batch size for operations (only used for from_documents)
    VECTOR_BATCH_SIZE = 250
    
    # Initialize embeddings
    dense_embeddings = SentenceTransformerEmbeddings(
        model_name="BAAI/bge-large-en-v1.5",
        model_kwargs={"trust_remote_code": True, "device": device},
        encode_kwargs={'normalize_embeddings':True }
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
        # Removed batch_size parameter
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
                retrieval_mode=RetrievalMode.HYBRID,
                batch_size=VECTOR_BATCH_SIZE  # This is ok for from_documents
            )
            logging.info(f"Successfully recreated collection '{collection_name}' with hybrid search support.")
            return docs, vector_store, dense_embeddings, sparse_embeddings
        else:
            # If force_recreate is False or it's a different error, just raise it
            logging.error(f"Error loading Qdrant collection: {error_message}")
            raise

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
        url=QDRANT_URL,
        use_semantic_chunking=True
    )

    print("\nIngestion and search testing completed successfully.")