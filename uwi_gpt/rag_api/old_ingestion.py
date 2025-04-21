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
# from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings
# Use langchain_qdrant instead of langchain_community.vectorstores
from langchain_qdrant import QdrantVectorStore, FastEmbedSparse, RetrievalMode
from langchain_core.documents import Document as LangchainDocument

from docling.document_converter import DocumentConverter
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_text_splitters import MarkdownTextSplitter
from langchain_text_splitters import SentenceTransformersTokenTextSplitter
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


import uuid
from typing import Optional
class Document:
    def __init__(self, page_content: str, metadata: dict, id: Optional[str] = None):
        self.page_content = page_content
        self.metadata = metadata
        self.id = id or str(uuid.uuid4())

    def __repr__(self):
        return f"Document(source={self.metadata.get('source_file', 'N/A')}, length={len(self.page_content)})"


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
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOC_FOLDER = os.path.join(BASE_DIR, "docs")
PERSIST_COLLECTION = "my_collection"
STATE_CACHE_PATH = os.path.join(BASE_DIR, "docs_state.json")
PDF_CACHE_PATH = os.path.join(BASE_DIR, "pdf_cache.json")
DOCS_CACHE_PATH = os.path.join(BASE_DIR, "docs_cache.joblib")
QDRANT_URL = "http://localhost:6333"
tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-m3", device=device)

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
            # Get absolute path for markdown cache
            base_dir = os.path.dirname(os.path.abspath(__file__))
            markdown_dir = os.path.join(base_dir, "markdown_cache")
            
            # Try to load from disk first (fastest method)
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

def save_markdown_to_disk(filepath, markdown_content, output_dir=None):
    """
    Save extracted markdown content to disk for faster reuse.
    """
    import os
    from pathlib import Path
    
    # Use absolute path for markdown cache
    if output_dir is None:
        # Get the absolute path to the directory containing this file
        base_dir = os.path.dirname(os.path.abspath(__file__))
        output_dir = os.path.join(base_dir, "markdown_cache")
    
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

def load_markdown_from_disk(filepath, markdown_dir=None):
    """
    Load markdown content from disk if available.
    """
    import os
    from pathlib import Path
    
    # Use absolute path for markdown cache
    if markdown_dir is None:
        # Get the absolute path to the directory containing this file
        base_dir = os.path.dirname(os.path.abspath(__file__))
        markdown_dir = os.path.join(base_dir, "markdown_cache")
    
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

def improved_document_chunker(documents: List[Document], min_chunk_size=300, chunk_size=1500, chunk_overlap=150) -> List[Document]:
    """
    An improved document chunker that uses MarkdownTextSplitter and
    merges small chunks with the *preceding* chunk to prevent very short chunks,
    ensuring all content is preserved.

    Args:
        documents: List of Document objects to split (expected to have Markdown content).
        min_chunk_size: Minimum size threshold for identifying small chunks (characters).
                        Chunks smaller than this will be merged with the previous one if possible.
        chunk_size: Target maximum size of each chunk in characters for the initial split.
        chunk_overlap: Number of characters to overlap between chunks during the initial split.

    Returns:
        List of chunked Document objects with preserved metadata.
    """
    logging.info(f"Starting improved document chunking for {len(documents)} documents using MarkdownTextSplitter and backward merging.")

    # Initialize the Markdown splitter
    text_splitter = MarkdownTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap
    )

    # --- REFINED MERGE FUNCTION ---
    def merge_small_chunks_backward(texts: List[str], metadatas: List[dict], min_size: int) -> tuple[List[str], List[dict]]:
        """
        Merges chunks smaller than min_size with the *preceding* chunk.
        Iterates backward to handle multiple small chunks correctly.
        """
        if not texts:
            return [], []

        merged_texts = list(texts)
        merged_metadatas = [m.copy() for m in metadatas] # Ensure we work with copies

        i = len(merged_texts) - 1
        while i > 0: # Start from the second-to-last chunk and go backward
            current_text = merged_texts[i]
            if len(current_text.strip()) < min_size:
                # If the current chunk is too small, merge it with the previous one
                logging.debug(f"Merging small chunk (index {i}, size {len(current_text.strip())}) backward.")

                # Prepend the small chunk's content to the previous chunk's content
                # Use a double newline as a separator
                merged_texts[i-1] = merged_texts[i-1] + "\n\n" + current_text

                # --- Metadata Merging Strategy ---
                # Simple strategy: Keep the metadata of the preceding chunk (i-1)
                # Optionally, you could try to combine titles or other fields if needed.
                # For now, we just discard the metadata of the small chunk being merged.
                # Example combining titles (if desired):
                # prev_meta = merged_metadatas[i-1]
                # current_meta = merged_metadatas[i]
                # if "chunk_title" in current_meta and "chunk_title" not in prev_meta:
                #     prev_meta["chunk_title"] = current_meta["chunk_title"]
                # elif "chunk_title" in prev_meta and "chunk_title" in current_meta and prev_meta["chunk_title"] != current_meta["chunk_title"]:
                #     prev_meta["chunk_title"] = f"{prev_meta['chunk_title']} | {current_meta['chunk_title']}"
                # merged_metadatas[i-1] = prev_meta # Update the previous metadata

                # Remove the merged chunk (text and metadata)
                del merged_texts[i]
                del merged_metadatas[i]

                # Important: Since we deleted element at index i, the next element to check
                # is now also at index i (if i < len(merged_texts)).
                # However, our loop condition `i > 0` and decrementing `i` handles this correctly.
                # We don't need to adjust `i` further here after deletion when iterating backward.

            i -= 1 # Move to the previous chunk

        # After backward merging, check if the *first* chunk is now too small.
        # It cannot be merged backward, so log a warning if it's smaller than min_size.
        if merged_texts and len(merged_texts[0].strip()) < min_size:
             logging.warning(f"The first chunk remains smaller than min_chunk_size ({len(merged_texts[0].strip())} chars) after backward merging.")

        return merged_texts, merged_metadatas
    # --- END REFINED MERGE FUNCTION ---

    result_chunks = []
    total_chunks_processed = 0

    for doc_index, doc in enumerate(documents):
        if not doc.page_content or not doc.page_content.strip():
            logging.warning(f"Skipping empty document: {doc.metadata.get('source_file', f'doc_index_{doc_index}')}")
            continue

        doc_metadata = doc.metadata.copy()

        # Extract document title/heading (same logic as before)
        content_lines = doc.page_content.strip().split('\n')
        doc_title = None
        for line in content_lines[:5]:
            match = re.match(r'^#{{1,6}}\s+(.+)$', line)
            if match:
                doc_title = match.group(1).strip()
                break
        if not doc_title and content_lines:
            doc_title = content_lines[0].strip()
            if len(doc_title) > 100:
                 doc_title = doc_title[:97] + "..."
        if doc_title:
            doc_metadata["doc_title"] = doc_title

        # Split the document content using MarkdownTextSplitter
        split_texts = text_splitter.split_text(doc.page_content)

        if not split_texts:
             logging.warning(f"MarkdownTextSplitter produced no chunks for document: {doc.metadata.get('source_file', f'doc_index_{doc_index}')}")
             continue

        # Prepare initial metadata for each chunk
        initial_metadatas = []
        for i, text_chunk in enumerate(split_texts):
            chunk_metadata = doc_metadata.copy()
            # Store initial index for reference, though it will be overwritten later
            chunk_metadata["initial_chunk_index"] = i

            # Extract chunk title/heading (same logic as before)
            chunk_lines = text_chunk.strip().split('\n')
            chunk_title = None
            for line in chunk_lines[:3]:
                match = re.match(r'^#{{1,6}}\s+(.+)$', line)
                if match:
                    chunk_title = match.group(1).strip()
                    break
            if chunk_title:
                chunk_metadata["chunk_title"] = chunk_title

            initial_metadatas.append(chunk_metadata)

        # Merge small chunks using the backward merging function
        merged_texts, merged_metadatas = merge_small_chunks_backward(split_texts, initial_metadatas, min_chunk_size)

        # Create final Document objects for the merged chunks
        num_chunks_in_doc = len(merged_texts)
        for i, (text, metadata) in enumerate(zip(merged_texts, merged_metadatas)):
            # Update chunk indices and count based on the final list after merging
            metadata["chunk_index"] = i
            metadata["chunk_count"] = num_chunks_in_doc

            # Remove the temporary initial index if it exists
            metadata.pop("initial_chunk_index", None)

            # Log if a chunk is still small (should only be the first one potentially)
            if len(text.strip()) < min_chunk_size:
                 # This logging might be redundant given the warning inside merge_small_chunks_backward
                 pass # logging.info(f"Including first chunk smaller than min_size ({len(text.strip())}) from {metadata.get('source_file', 'unknown')}")

            result_chunks.append(Document(
                page_content=text.strip(),
                metadata=metadata
            ))
        total_chunks_processed += num_chunks_in_doc

    logging.info(f"Chunking completed: generated {len(result_chunks)} total chunks from {len(documents)} documents.")
    return result_chunks


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
    dense_embeddings = HuggingFaceEmbeddings(
        model_name="BAAI/bge-m3",
        model_kwargs={"trust_remote_code": True, "device": device},
        encode_kwargs={'normalize_embeddings':True}
    )
    
    # Initialize sparse embeddings
    sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25", providers=["CUDAExecutionProvider"], threads=4)
    
    # Load cached documents
    if not os.path.exists(docs_cache_path):
        raise FileNotFoundError(f"Document cache not found: {docs_cache_path}. Please run ingestion first.")
    
    docs = joblib.load(docs_cache_path)
    logging.info(f"Loaded {len(docs)} cached document chunks.")
    
    # Use gRPC for better performance
    import re
    host_match = re.match(r'https?://([^:/]+)(?::\d+)?', qdrant_url)
    grpc_host = host_match.group(1) if host_match else "localhost"
    grpc_port = 6334  # Default gRPC port for Qdrant
    
    # First try with gRPC
    try:
        # THE FIX: Specify the vector_name as "default"
        vector_store = QdrantVectorStore.from_existing_collection(
            embedding=dense_embeddings,
            sparse_embedding=sparse_embeddings,
            collection_name=collection_name,
            host=grpc_host,
            port=grpc_port,
            prefer_grpc=True,
            retrieval_mode=RetrievalMode.HYBRID,
            vector_name="default"  # Add this parameter
        )
        logging.info(f"Successfully loaded collection '{collection_name}' with hybrid search support via gRPC.")
        return docs, vector_store, dense_embeddings, sparse_embeddings
    except Exception as e:
        grpc_error = str(e)
        logging.warning(f"Error connecting with gRPC: {grpc_error}. Trying HTTP...")
        
        # Fall back to HTTP
        try:
            # THE FIX: Also specify vector_name here
            vector_store = QdrantVectorStore.from_existing_collection(
                embedding=dense_embeddings,
                sparse_embedding=sparse_embeddings,
                collection_name=collection_name,
                url=qdrant_url,
                retrieval_mode=RetrievalMode.HYBRID,
                vector_name="default"  # Add this parameter
            )
            logging.info(f"Successfully loaded collection '{collection_name}' with hybrid search support via HTTP.")
            return docs, vector_store, dense_embeddings, sparse_embeddings
        except Exception as e2:
            http_error = str(e2)
            
            # If force_recreate is True, recreate the collection
            if force_recreate:
                logging.warning(f"Error connecting to collection '{collection_name}'. Recreating collection...")
                
                # Convert to LangChain documents format
                from langchain_core.documents import Document as LangchainDocument
                langchain_docs = []
                for doc in docs:
                    langchain_docs.append(LangchainDocument(
                        page_content=doc.page_content,
                        metadata=doc.metadata
                    ))
                
                # First try to recreate with gRPC
                try:
                    # THE FIX: Also specify vector_name when creating
                    vector_store = QdrantVectorStore.from_documents(
                        langchain_docs,
                        embedding=dense_embeddings,
                        sparse_embedding=sparse_embeddings,
                        host=grpc_host,
                        port=grpc_port,
                        prefer_grpc=True,
                        collection_name=collection_name,
                        force_recreate=True,
                        retrieval_mode=RetrievalMode.HYBRID,
                        batch_size=VECTOR_BATCH_SIZE,
                        vector_name="default"  # Add this parameter
                    )
                    logging.info(f"Successfully recreated collection '{collection_name}' with hybrid search support via gRPC.")
                    return docs, vector_store, dense_embeddings, sparse_embeddings
                except Exception as e3:
                    logging.warning(f"Error recreating with gRPC: {e3}. Trying HTTP...")
                    
                    # Fall back to HTTP if gRPC fails
                    # THE FIX: Also specify vector_name here
                    vector_store = QdrantVectorStore.from_documents(
                        langchain_docs,
                        embedding=dense_embeddings,
                        sparse_embedding=sparse_embeddings,
                        url=qdrant_url,
                        collection_name=collection_name,
                        force_recreate=True,
                        retrieval_mode=RetrievalMode.HYBRID,
                        batch_size=VECTOR_BATCH_SIZE,
                        vector_name="default"  # Add this parameter
                    )
                    logging.info(f"Successfully recreated collection '{collection_name}' with hybrid search support via HTTP.")
                    return docs, vector_store, dense_embeddings, sparse_embeddings
            else:
                # If it's a different error, propagate it
                logging.error(f"Error loading Qdrant collection: {http_error}")
                raise

# Make the same changes to initialize_documents_and_vector_store
def initialize_documents_and_vector_store(doc_folder: str = "./docs",
                                         collection_name: str = "my_collection",
                                         docs_cache_path: str = "docs_cache.joblib",
                                         state_cache_path: str = "docs_state.json",
                                         url: str = "http://localhost:6333"):
    """
    Initialize or update document store with optimized batching and vector operations.
    """
    init_start = time.perf_counter()
    
    # Larger batch size for faster vector insertion
    VECTOR_BATCH_SIZE = 250
    
    # 1. Initialize the dense embedding model with OS-specific device settings
    dense_embeddings = HuggingFaceEmbeddings(
        model_name="BAAI/bge-m3",
        model_kwargs={"trust_remote_code": True, "device": device},
        encode_kwargs={'normalize_embeddings':True}
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
    
    # Use gRPC for better performance
    from qdrant_client import QdrantClient
    
    # Extract host from URL
    import re
    host_match = re.match(r'https?://([^:/]+)(?::\d+)?', url)
    grpc_host = host_match.group(1) if host_match else "localhost"
    grpc_port = 6334  # Default gRPC port for Qdrant
    
    # Create client with gRPC preference
    try:
        client = QdrantClient(
            host=grpc_host,
            port=grpc_port,
            prefer_grpc=True,
            timeout=5.0
        )
        collections = client.get_collections().collections
        collection_exists = any(collection.name == collection_name for collection in collections)
        using_grpc = True
        logging.info("Successfully connected to Qdrant using gRPC")
    except Exception as e:
        logging.error(f"Error connecting to Qdrant via gRPC: {e}")
        logging.warning(f"Falling back to HTTP connection")
        client = QdrantClient(url=url)
        try:
            collections = client.get_collections().collections
            collection_exists = any(collection.name == collection_name for collection in collections)
            using_grpc = False
        except Exception as e2:
            logging.error(f"Error connecting to Qdrant via HTTP: {e2}")
            collection_exists = False
            using_grpc = False
    
    if collection_exists and not reprocess:
        logging.info("Persistent vector store found. Loading from Qdrant...")
        
        try:
            # THE FIX: Add vector_name="default" parameter
            if using_grpc:
                vector_store = QdrantVectorStore.from_existing_collection(
                    embedding=dense_embeddings,
                    sparse_embedding=sparse_embeddings,
                    collection_name=collection_name,
                    host=grpc_host,
                    port=grpc_port,
                    prefer_grpc=True,
                    retrieval_mode=RetrievalMode.HYBRID,
                    vector_name="default"  # Add this parameter
                )
                logging.info("Successfully loaded Qdrant collection with hybrid search support via gRPC.")
            else:
                vector_store = QdrantVectorStore.from_existing_collection(
                    embedding=dense_embeddings,
                    sparse_embedding=sparse_embeddings,
                    collection_name=collection_name,
                    url=url,
                    retrieval_mode=RetrievalMode.HYBRID,
                    vector_name="default"  # Add this parameter
                )
                logging.info("Successfully loaded Qdrant collection with hybrid search support via HTTP.")
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
                
                # Use our new unified chunker
                docs =  improved_document_chunker(
                            documents,
                            min_chunk_size=500,  # Prevents tiny chunks
                            chunk_size=1000,
                            chunk_overlap=200
                        )
                joblib.dump(docs, docs_cache_path)
    
    # If collection doesn't exist, needs to be recreated for hybrid search, or documents have changed
    if not collection_exists or reprocess:
        logging.info("Loading and cleaning documents...")
        documents = load_and_clean_documents(doc_folder)
        logging.info(f"Loaded {len(documents)} documents.")
        metadata_docs = create_documents_from_data(degree_programs_data)
        documents.extend(metadata_docs)
        
        # Use our new unified chunker
        docs =  improved_document_chunker(
                    documents,
                    min_chunk_size=500,  # Prevents tiny chunks
                    chunk_size=1000,
                    chunk_overlap=200
                )
        # Convert to LangChain documents format
        langchain_docs = convert_to_langchain_docs(docs)
        
        # Create new vector store using the preferred connection method
        logging.info(f"Building new vector store using QdrantVectorStore with hybrid search capability and batch size {VECTOR_BATCH_SIZE}...")
        try:
            # THE FIX: Add vector_name="default" parameter 
            if using_grpc:
                vector_store = QdrantVectorStore.from_documents(
                    langchain_docs,
                    embedding=dense_embeddings,
                    sparse_embedding=sparse_embeddings,
                    host=grpc_host,
                    port=grpc_port,
                    prefer_grpc=True,
                    collection_name=collection_name,
                    force_recreate=True,
                    retrieval_mode=RetrievalMode.HYBRID,
                    batch_size=VECTOR_BATCH_SIZE,
                    vector_name="default"  # Add this parameter
                )
                logging.info("Successfully created vector store via gRPC.")
            else:
                vector_store = QdrantVectorStore.from_documents(
                    langchain_docs,
                    embedding=dense_embeddings,
                    sparse_embedding=sparse_embeddings,
                    url=url,
                    collection_name=collection_name,
                    force_recreate=True,
                    retrieval_mode=RetrievalMode.HYBRID,
                    batch_size=VECTOR_BATCH_SIZE,
                    vector_name="default"  # Add this parameter
                )
                logging.info("Successfully created vector store via HTTP.")
        except Exception as e:
            logging.error(f"Error creating vector store: {e}")
            # If gRPC failed, try HTTP as a fallback
            if using_grpc:
                logging.warning("Falling back to HTTP for vector store creation")
                vector_store = QdrantVectorStore.from_documents(
                    langchain_docs,
                    embedding=dense_embeddings,
                    sparse_embedding=sparse_embeddings,
                    url=url,
                    collection_name=collection_name,
                    force_recreate=True,
                    retrieval_mode=RetrievalMode.HYBRID,
                    batch_size=VECTOR_BATCH_SIZE,
                    vector_name="default"  # Add this parameter
                )
                logging.info("Successfully created vector store via HTTP fallback.")
            else:
                raise

        joblib.dump(docs, docs_cache_path)
    
    try:
        with open(state_cache_path, "w") as f:
            json.dump(current_state, f)
    except Exception as e:
        logging.error(f"Error saving state cache: {e}")
    
    init_end = time.perf_counter()
    logging.info(f"Initialization took {init_end - init_start:.2f} seconds")
    return docs, vector_store, dense_embeddings, sparse_embeddings

if __name__ == "__main__":
    # Install required dependencies if not already installed
    try:
        import langchain_qdrant
    except ImportError:
        import subprocess
        print("Installing required dependencies...")
        subprocess.check_call(["pip", "install", "langchain-qdrant", "fastembeddings"])
        print("Dependencies installed successfully.")
    
    try:
        import grpc
    except ImportError:
        import subprocess
        print("Installing gRPC dependencies...")
        subprocess.check_call(["pip", "install", "grpcio", "grpcio-tools"])
        print("gRPC dependencies installed successfully.")
    
    # Check if Qdrant is available with gRPC
    from qdrant_client import QdrantClient
    try:
        client = QdrantClient(host="localhost", port=6334, prefer_grpc=True, timeout=5.0)
        client.get_collections()
        print("Successfully connected to Qdrant using gRPC!")
    except Exception as e:
        print(f"Could not connect to Qdrant using gRPC: {e}")
        print("Will try HTTP instead. For better performance, ensure Qdrant server has gRPC enabled (port 6334).")
    
    # Initialize or load documents and vector store
    docs, vector_store, dense_embeddings, sparse_embeddings = initialize_documents_and_vector_store(
        doc_folder=DOC_FOLDER,
        collection_name=PERSIST_COLLECTION,
        url=QDRANT_URL,
    )
    
    # Run a quick test search to verify everything is working
    query = "What are the computer science degree programs?"
    results = vector_store.similarity_search_with_score(query, k=3)
    
    print("\n=== Sample Search Results ===")
    for doc, score in results:
        print(f"Score: {score:.4f}")
        print(f"Content: {doc.page_content[:150]}...")
        print(f"Metadata: {doc.metadata}")
        print("-" * 50)

    print("\nIngestion and search testing completed successfully.")