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
from typing import List, Tuple
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

def improved_document_chunker(
    documents: List[Document],
    min_chunk_size: int = 300,
    chunk_size: int = 1500,
    chunk_overlap: int = 150
) -> List[Document]:
    """
    Chunk markdown documents, preferring headings, paragraphs, lists, then sentence boundaries,
    and only overshooting if absolutely no separator is found.
    """
    logging.info(f"Starting improved document chunking for {len(documents)} docs.")

    # Prioritized separators
    separators = [
        "\n## ",
        "\n# ",
        "\n\n",    # paragraph break
        "\n- ",    # list
        "\n* ",
        "\n"       # single line break
    ]

    def merge_small_chunks_backward(texts, metas, min_size):
        i = len(texts) - 1
        while i > 0:
            if len(texts[i].strip()) < min_size:
                texts[i-1] += "\n\n" + texts[i]
                del texts[i], metas[i]
            i -= 1
        return texts, metas

    def custom_split(text: str) -> List[str]:
        parts, start, L = [], 0, len(text)
        sentence_boundary = re.compile(r'(?<=[\.?!])\s+')

        while start < L:
            end_limit = min(start + chunk_size, L)

            # 1) Try the markdown headings / paragraphs / lists etc.
            best_pos, best_len = -1, 0
            for sep in separators:
                p = text.rfind(sep, start, end_limit)
                if p > best_pos:
                    best_pos, best_len = p, len(sep)

            if best_pos >= 0:
                split_end = best_pos + best_len

            else:
                # 2) Try any sentence boundary
                window = text[start:end_limit]
                boundaries = [m.end() for m in sentence_boundary.finditer(window)]
                if boundaries:
                    # pick the last boundary in that chunk
                    split_end = start + boundaries[-1]
                else:
                    # 3) fallback: overshoot to next markdown sep (or end)
                    next_pos, next_len = None, 0
                    for sep in separators:
                        p = text.find(sep, end_limit)
                        if p != -1 and (next_pos is None or p < next_pos):
                            next_pos, next_len = p, len(sep)
                    split_end = (next_pos + next_len) if next_pos is not None else L

            parts.append(text[start:split_end])
            # always apply overlap
            start = max(split_end - chunk_overlap, split_end)

        return parts

    chunks: List[Document] = []
    for doc in documents:
        raw = (doc.page_content or "").strip()
        if not raw:
            continue

        # --- flatten code fences & merge tables ---
        raw = re.sub(r"```.*?```", lambda m: m.group(0).replace("\n", " "), raw, flags=re.DOTALL)
        lines, buf = raw.splitlines(), []
        merged = []
        for line in lines:
            if line.strip().startswith("|") and "|" in line:
                buf.append(line)
            else:
                if buf:
                    merged.append(" ".join(buf)); buf = []
                merged.append(line)
        if buf:
            merged.append(" ".join(buf))
        clean = "\n".join(merged)

        # split up
        parts = custom_split(clean)

        # attach metadata
        metas = []
        for i, _ in enumerate(parts):
            m = doc.metadata.copy()
            m["initial_chunk_index"] = i
            metas.append(m)

        # merge too-small
        merged_txts, merged_metas = merge_small_chunks_backward(parts, metas, min_chunk_size)

        # finalize
        total = len(merged_txts)
        for idx, (txt, meta) in enumerate(zip(merged_txts, merged_metas)):
            # trim stray bullets
            txt = re.sub(r"[\r\n]+\s*[-*]\s*$", "", txt).strip()
            meta["chunk_index"] = idx
            meta["chunk_count"] = total
            if txt:
                chunks.append(Document(page_content=txt, metadata=meta))

    logging.info(f"Chunking completed: {len(chunks)} chunks generated.")
    return chunks


def format_term_label(term_code: str) -> str:
    """
    Convert term codes like "201510" to human-readable format like "2015/2016 Semester I".
    
    Args:
        term_code: Term code in format YYYYSS where SS is the semester code
        
    Returns:
        Formatted term string
    """
    if not term_code or not term_code.isdigit() or len(term_code) < 6:
        return term_code  # Return as-is if invalid format
    
    year = term_code[:4]
    suffix = term_code[4:6]
    next_year = str(int(year) + 1)
    
    if suffix == "10":
        name = "Semester I"
    elif suffix == "20":
        name = "Semester II"
    elif suffix == "40":
        name = "Summer School"
    else:
        name = f"Term {suffix}"  # Fallback for unknown codes
        
    return f"{year}/{next_year} {name}"

def create_documents_from_course_data(courses_data: List[Dict[str, Any]]) -> List[Document]:
    """
    Create Document objects from course data JSON.
    Each course is kept as a single document (not chunked) for better retrieval.
    """
    docs = []
    for course in courses_data:
        # Create a descriptive text combining all relevant information
        page_content = []
        
        # Add title and course number
        course_title = course.get("courseTitle", "Unknown Title")
        course_number = course.get("courseNumber", "")
        subject = course.get("subject", "")
        subject_description = course.get("subjectDescription", "")
        page_content.append(f"Course {subject}{course_number}: {course_title}")
        
        # Add subject description if available
        if subject_description:
            page_content.append(f"Subject: {subject_description}")
        
        # Add credits info
        credit_low = course.get("creditHourLow")
        credit_high = course.get("creditHourHigh")
        if credit_low is not None and credit_high is not None:
            page_content.append(f"Credits: {credit_low}-{credit_high}")
        
        # Add department and faculty (not college)
        department = course.get("department", "")
        faculty = course.get("college", "")  # Using college field but referring to it as faculty
        if department or faculty:
            parts = []
            if department:
                parts.append(f"Department: {department}")
            if faculty:
                parts.append(f"Faculty: {faculty}")  # Changed from College to Faculty
            page_content.append(", ".join(parts))
        
        # Add term information with semester decoding if available
        term_effective = course.get("termEffective", "")
        if term_effective:
            formatted_term = format_term_label(term_effective)
            page_content.append(f"Term Effective: {formatted_term}")
        
        # Add prerequisites if available
        if course.get("prerequisites") and len(course.get("prerequisites", [])) > 0:
            prereq_parts = ["Prerequisites:"]
            for prereq in course.get("prerequisites", []):
                prereq_subject = prereq.get('subject', '')
                prereq_number = prereq.get('number', '')
                prereq_grade = prereq.get('grade', 'C')
                
                # Format as CHIN2001 (Chinese 2001)
                prereq_code = f"{prereq_subject.split(' - ')[0]}{prereq_number}"
                prereq_name = ""
                if " - " in prereq.get('subject', ''):
                    # Extract the full name if format is "CHIN - Chinese"
                    subject_parts = prereq.get('subject', '').split(" - ")
                    if len(subject_parts) > 1:
                        prereq_name = f" ({subject_parts[1]} {prereq_number})"
                prereq_parts.append(f"- {prereq_code}{prereq_name} (Grade: {prereq_grade})")
            page_content.append("\n".join(prereq_parts))
        else:
            page_content.append("Prerequisites: None")
        
        # Add course description if available
        course_description = course.get("courseDescription")
        if course_description:
            page_content.append(f"Description: {course_description}")
        
        # Create the document with rich metadata
        formatted_term = format_term_label(term_effective) if term_effective else ""
        docs.append(Document(
            page_content="\n\n".join(page_content),
            metadata={
                "course_code": f"{subject}{course_number}",
                "course_title": course_title,
                "department": department,
                "faculty": faculty,  # Changed from college to faculty
                "subject_description": subject_description,
                "subject": subject,
                "subject_code": course.get("subjectCode", ""),
                "credit_hours": f"{credit_low}-{credit_high}",
                "credit_low": credit_low,
                "credit_high": credit_high,
                "doc_type": "course_description",
                "source_file": "course_data.json",  # Will be updated with actual filename
                "heading": f"Course {subject}{course_number}: {course_title}",
                "format": "json",
                "term_effective": term_effective,
                "term_formatted": formatted_term,  # Add the formatted term to metadata as well
                # Store concatenated subject+number for prerequisites
                "prerequisites": [f"{p.get('subject', '').split(' - ')[0]}{p.get('number', '')}" for p in course.get("prerequisites", [])],
                "has_prerequisites": len(course.get("prerequisites", [])) > 0
            }
        ))
    return docs
# --- JSON Caching Functions ---

def save_json_docs_to_cache(data, cache_dir=None, cache_name="course_data_cache.json"):
    """Save processed course data to disk cache."""
    if cache_dir is None:
        cache_dir = os.path.join(BASE_DIR, "json_cache")
    
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, cache_name)
    
    try:
        # Convert Document objects to serializable dicts
        serializable_data = []
        for doc in data:
            serializable_data.append({
                "page_content": doc.page_content,
                "metadata": doc.metadata,
                "id": doc.id
            })
        
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(serializable_data, f, indent=2)
        
        logging.info(f"Saved {len(data)} course documents to cache at {cache_path}")
        return cache_path
    except Exception as e:
        logging.error(f"Error saving course data cache: {e}")
        return None

def load_json_docs_from_cache(cache_dir=None, cache_name="course_data_cache.json"):
    """Load processed course documents from disk cache."""
    if cache_dir is None:
        cache_dir = os.path.join(BASE_DIR, "json_cache")
    
    cache_path = os.path.join(cache_dir, cache_name)
    
    if not os.path.exists(cache_path):
        return None
    
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            serialized_docs = json.load(f)
        
        # Convert back to Document objects
        docs = []
        for item in serialized_docs:
            docs.append(Document(
                page_content=item["page_content"],
                metadata=item["metadata"],
                id=item.get("id")
            ))
        
        logging.info(f"Loaded {len(docs)} course documents from cache at {cache_path}")
        return docs
    except Exception as e:
        logging.error(f"Error loading course data cache: {e}")
        return None

def process_json_files(doc_folder: str) -> List[Document]:
    """Process JSON files with special handling for course data."""
    json_files = [os.path.join(doc_folder, fn) for fn in os.listdir(doc_folder)
                 if fn.lower().endswith('.json')]
    
    if not json_files:
        logging.info("No JSON files found in documents folder")
        return []
    
    logging.info(f"Found {len(json_files)} JSON files to process")
    all_json_docs = []
    
    # Process each JSON file separately
    for json_file in json_files:
        filename = os.path.basename(json_file)
        cache_name = os.path.splitext(filename)[0] + "_cache.json"
        
        # Check if file has been modified since last cached
        cache_outdated = True
        cache_dir = os.path.join(BASE_DIR, "json_cache")
        cache_path = os.path.join(cache_dir, cache_name)
        
        if os.path.exists(cache_path):
            json_mtime = os.path.getmtime(json_file)
            cache_mtime = os.path.getmtime(cache_path)
            if json_mtime <= cache_mtime:
                cache_outdated = False
        
        if not cache_outdated:
            # Load from cache if not outdated
            cached_docs = load_json_docs_from_cache(cache_dir=cache_dir, cache_name=cache_name)
            if cached_docs:
                logging.info(f"Using cached data for {filename}")
                all_json_docs.extend(cached_docs)
                continue
        
        # Process the file
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
            
            # Handle different JSON structures
            if not isinstance(json_data, list):
                if isinstance(json_data, dict):
                    # It might be a single object or have a wrapper
                    if "courses" in json_data and isinstance(json_data["courses"], list):
                        json_data = json_data["courses"]
                    else:
                        json_data = [json_data]  # Convert single object to list
                else:
                    logging.warning(f"Unsupported JSON structure in {filename}, skipping")
                    continue
            
            # Detect if it's course data by checking fields
            is_course_data = False
            if len(json_data) > 0 and isinstance(json_data[0], dict):
                course_keys = ["courseNumber", "subject", "courseTitle"]
                if all(key in json_data[0] for key in course_keys):
                    is_course_data = True
            
            if is_course_data:
                docs = create_documents_from_course_data(json_data)
                # Update source_file to actual filename
                for doc in docs:
                    doc.metadata["source_file"] = filename
            else:
                # Generic JSON handling
                logging.info(f"Processing generic JSON data from {filename}")
                docs = []
                for i, item in enumerate(json_data):
                    if isinstance(item, dict):
                        # Create a simple text representation
                        content = json.dumps(item, indent=2)
                        docs.append(Document(
                            page_content=content,
                            metadata={"source_file": filename, "index": i, "format": "json"}
                        ))
            
            if docs:
                # Cache the results
                save_json_docs_to_cache(docs, cache_dir=cache_dir, cache_name=cache_name)
                all_json_docs.extend(docs)
                logging.info(f"Processed {len(docs)} items from {filename}")
            
        except Exception as e:
            logging.error(f"Error processing JSON file {filename}: {e}")
    
    logging.info(f"Total of {len(all_json_docs)} documents created from JSON files")
    return all_json_docs

# Modify this function to include .json files
def get_docs_folder_state(doc_folder: str) -> Dict[str, float]:
    state = {}
    for filename in os.listdir(doc_folder):
        if filename.lower().endswith(('.pdf', '.txt', '.json')):  # Added .json
            full_path = os.path.join(doc_folder, filename)
            state[filename] = os.path.getmtime(full_path)
    return state

# Modify load_and_clean_documents to include JSON processing
def load_and_clean_documents(doc_folder: str) -> List[Document]:
    """Load and clean documents including JSON files."""
    start_time = time.perf_counter()
    heading_regex = re.compile(r"^(?:[A-Z0-9 .-]+)$")
    documents = []
    pdf_cache = load_pdf_cache()
    
    # Get list of PDF and text files
    pdf_files = [os.path.join(doc_folder, fn) for fn in os.listdir(doc_folder) 
                if fn.lower().endswith('.pdf')]
    txt_files = [os.path.join(doc_folder, fn) for fn in os.listdir(doc_folder) 
                if fn.lower().endswith('.txt')]
    
    # Process PDF and TXT files as before
    # [Your existing PDF and TXT processing code stays here]
    
    # ADD THIS: Process JSON files
    json_docs = process_json_files(doc_folder)
    documents.extend(json_docs)
    
    # [Rest of your existing function stays unchanged]
    
    end_time = time.perf_counter()
    logging.info(f"Document loading and cleaning took {end_time - start_time:.2f} seconds. Loaded {len(documents)} documents.")
    return documents

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
COURSE_COLLECTION_NAME = "courses_collection"
def initialize_documents_and_vector_stores( # Renamed for clarity
    doc_folder: str = "./docs",
    general_collection_name: str = "my_collection",
    course_collection_name: str = COURSE_COLLECTION_NAME, # Use the new constant
    docs_cache_path: str = "docs_cache.joblib",
    state_cache_path: str = "docs_state.json",
    url: str = QDRANT_URL, # Use the defined URL
    force_recreate: bool = False
):
    init_start = time.perf_counter()
    VECTOR_BATCH_SIZE = 250

    dense_embeddings = HuggingFaceEmbeddings(
        model_name="BAAI/bge-m3",
        model_kwargs={"trust_remote_code": True, "device": device},
        encode_kwargs={'normalize_embeddings': True}
    )
    sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")

    current_state = get_docs_folder_state(doc_folder)
    previous_state = {}
    if os.path.exists(state_cache_path):
        try:
            with open(state_cache_path, "r") as f:
                previous_state = json.load(f)
        except Exception as e:
            logging.error(f"Error loading state cache: {e}")
    
    reprocess = (current_state != previous_state) or force_recreate

    # --- Qdrant Client Initialization (simplified for brevity, use your existing robust version) ---
    from qdrant_client import QdrantClient
    import re
    host_match = re.match(r'https?://([^:/]+)(?::\d+)?', url)
    grpc_host = host_match.group(1) if host_match else "localhost"
    grpc_port = 6334

    try:
        client = QdrantClient(host=grpc_host, port=grpc_port, prefer_grpc=True, timeout=5.0)
        using_grpc = True
        logging.info("Successfully connected to Qdrant using gRPC")
    except Exception as e_grpc:
        logging.warning(f"Qdrant gRPC connection failed: {e_grpc}. Falling back to HTTP.")
        client = QdrantClient(url=url, timeout=5.0) # Ensure timeout for HTTP too
        using_grpc = False
        logging.info("Successfully connected to Qdrant using HTTP")

    def collection_exists(client, collection_name_to_check):
        try:
            collections = client.get_collections().collections
            return any(c.name == collection_name_to_check for c in collections)
        except Exception as e:
            logging.error(f"Error checking if collection {collection_name_to_check} exists: {e}")
            return False # Assume not exists if error

    general_collection_exists = collection_exists(client, general_collection_name)
    course_collection_exists = collection_exists(client, course_collection_name)

    # --- Determine if full document processing is needed ---
    all_processed_docs: List[Document] # Custom Document objects
    if reprocess or not os.path.exists(docs_cache_path) or not general_collection_exists or not course_collection_exists:
        logging.info("Reprocessing documents or collection(s) missing/forcing recreate.")
        raw_documents = load_and_clean_documents(doc_folder) # This loads all, including JSON courses
        logging.info(f"Loaded {len(raw_documents)} raw documents.")
        
        metadata_docs = create_documents_from_data(degree_programs_data) # Degree programs
        raw_documents.extend(metadata_docs)

        # Separate course documents from other documents (USING YOUR CUSTOM Document class)
        course_custom_docs = [doc for doc in raw_documents if doc.metadata.get("doc_type") == "course_description"]
        other_custom_docs = [doc for doc in raw_documents if doc.metadata.get("doc_type") != "course_description"]

        logging.info(f"Found {len(course_custom_docs)} course documents.")
        logging.info(f"Found {len(other_custom_docs)} other documents to be chunked.")

        # Chunk non-course documents
        chunked_other_docs = improved_document_chunker(
            other_custom_docs,
            min_chunk_size=500,
            chunk_size=1000,
            chunk_overlap=200
        )
        
        # Combine chunked general documents. Course documents remain unchunked.
        all_processed_docs = chunked_other_docs + course_custom_docs # List of custom Document objects
        logging.info(f"Total processed document units: {len(all_processed_docs)}")
        joblib.dump(all_processed_docs, docs_cache_path)
    else:
        logging.info("Loading documents from joblib cache.")
        all_processed_docs = joblib.load(docs_cache_path)

    # --- Convert to LangChain Documents and Prepare for Vector Stores ---
    # We need to split them based on doc_type *before* creating LangChain documents for different stores
    
    final_general_lc_docs: List[LangchainDocument] = []
    final_course_lc_docs: List[LangchainDocument] = []

    for doc_custom in all_processed_docs: # Iterate through custom Document objects
        lc_doc = LangchainDocument(page_content=doc_custom.page_content, metadata=doc_custom.metadata)
        if doc_custom.metadata.get("doc_type") == "course_description":
            final_course_lc_docs.append(lc_doc)
        else:
            final_general_lc_docs.append(lc_doc)
            
    logging.info(f"Prepared {len(final_general_lc_docs)} LangChain docs for general collection.")
    logging.info(f"Prepared {len(final_course_lc_docs)} LangChain docs for course collection.")

    # --- Initialize/Update General Document Vector Store ---
    general_vector_store = None
    if not general_collection_exists or reprocess: # Or if relevant part of docs changed
        logging.info(f"Building new general vector store '{general_collection_name}'...")
        if using_grpc:
            general_vector_store = QdrantVectorStore.from_documents(
                final_general_lc_docs, dense_embeddings, sparse_embedding=sparse_embeddings,
                host=grpc_host, port=grpc_port, prefer_grpc=True,
                collection_name=general_collection_name, force_recreate=True, # force_recreate might need finer control
                retrieval_mode=RetrievalMode.HYBRID, batch_size=VECTOR_BATCH_SIZE, vector_name="default"
            )
        else:
            general_vector_store = QdrantVectorStore.from_documents(
                final_general_lc_docs, dense_embeddings, sparse_embedding=sparse_embeddings,
                url=url, collection_name=general_collection_name, force_recreate=True,
                retrieval_mode=RetrievalMode.HYBRID, batch_size=VECTOR_BATCH_SIZE, vector_name="default"
            )
        logging.info(f"General vector store '{general_collection_name}' created/updated.")
    else:
        logging.info(f"Loading existing general vector store '{general_collection_name}'...")
        if using_grpc:
            general_vector_store = QdrantVectorStore.from_existing_collection(
                dense_embeddings, sparse_embedding=sparse_embeddings,
                host=grpc_host, port=grpc_port, prefer_grpc=True,
                collection_name=general_collection_name, retrieval_mode=RetrievalMode.HYBRID, vector_name="default"
            )
        else:
            general_vector_store = QdrantVectorStore.from_existing_collection(
                dense_embeddings, sparse_embedding=sparse_embeddings, url=url,
                collection_name=general_collection_name, retrieval_mode=RetrievalMode.HYBRID, vector_name="default"
            )
        logging.info(f"General vector store '{general_collection_name}' loaded.")

    # --- Initialize/Update Course Document Vector Store ---
    course_vector_store = None
    if not course_collection_exists or reprocess: # Or if course docs changed
        logging.info(f"Building new course vector store '{course_collection_name}'...")
        if using_grpc:
            course_vector_store = QdrantVectorStore.from_documents(
                final_course_lc_docs, dense_embeddings, sparse_embedding=sparse_embeddings,
                host=grpc_host, port=grpc_port, prefer_grpc=True,
                collection_name=course_collection_name, force_recreate=True,
                retrieval_mode=RetrievalMode.HYBRID, batch_size=VECTOR_BATCH_SIZE, vector_name="default"
            )
        else:
            course_vector_store = QdrantVectorStore.from_documents(
                final_course_lc_docs, dense_embeddings, sparse_embedding=sparse_embeddings,
                url=url, collection_name=course_collection_name, force_recreate=True,
                retrieval_mode=RetrievalMode.HYBRID, batch_size=VECTOR_BATCH_SIZE, vector_name="default"
            )
        logging.info(f"Course vector store '{course_collection_name}' created/updated.")
    else:
        logging.info(f"Loading existing course vector store '{course_collection_name}'...")
        if using_grpc:
            course_vector_store = QdrantVectorStore.from_existing_collection(
                dense_embeddings, sparse_embedding=sparse_embeddings,
                host=grpc_host, port=grpc_port, prefer_grpc=True,
                collection_name=course_collection_name, retrieval_mode=RetrievalMode.HYBRID, vector_name="default"
            )
        else:
            course_vector_store = QdrantVectorStore.from_existing_collection(
                dense_embeddings, sparse_embedding=sparse_embeddings, url=url,
                collection_name=course_collection_name, retrieval_mode=RetrievalMode.HYBRID, vector_name="default"
            )
        logging.info(f"Course vector store '{course_collection_name}' loaded.")
        
    try:
        with open(state_cache_path, "w") as f:
            json.dump(current_state, f)
    except Exception as e:
        logging.error(f"Error saving state cache: {e}")

    init_end = time.perf_counter()
    logging.info(f"Initialization of vector stores took {init_end - init_start:.2f} seconds")
    
    # Return all processed custom Document objects, and both vector stores
    return all_processed_docs, general_vector_store, course_vector_store, dense_embeddings, sparse_embeddings



PERSIST_COLLECTION = "my_main_collection"  # For general documents
COURSE_COLLECTION_NAME = "courses_collection" # For course-specific documents

if __name__ == "__main__":
    # Install required dependencies if not already installed
    try:
        import langchain_qdrant
    except ImportError:
        import subprocess
        print("Installing required dependencies...")
        subprocess.check_call(["pip", "install", "langchain-qdrant", "fastembed"]) # Corrected to fastembed
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
        # Ensure QDRANT_URL is defined, e.g., QDRANT_URL = "http://localhost:6333"
        # Extract host for gRPC check
        import re
        host_match = re.match(r'https?://([^:/]+)(?::\d+)?', QDRANT_URL)
        grpc_host = host_match.group(1) if host_match else "localhost"
        
        client = QdrantClient(host=grpc_host, port=6334, prefer_grpc=True, timeout=5.0)
        client.get_collections()
        print("Successfully connected to Qdrant using gRPC!")
    except Exception as e:
        print(f"Could not connect to Qdrant using gRPC: {e}")
        print("Will try HTTP instead. For better performance, ensure Qdrant server has gRPC enabled (port 6334).")
    
    # Initialize or load documents and BOTH vector stores
    # The function should now be the one that handles two collections
    # Make sure the paths in DOC_FOLDER, etc., are correctly defined in your script
    
    # Assuming initialize_documents_and_vector_stores is the updated function:
    all_processed_docs, general_vector_store, course_vector_store, dense_embeddings, sparse_embeddings = initialize_documents_and_vector_stores(
        doc_folder=DOC_FOLDER,
        general_collection_name=PERSIST_COLLECTION, # Your main collection name
        course_collection_name=COURSE_COLLECTION_NAME,   # Your new course collection name
        docs_cache_path=DOCS_CACHE_PATH, # Ensure this is defined
        state_cache_path=STATE_CACHE_PATH, # Ensure this is defined
        url=QDRANT_URL
    )
    
    print(f"\n--- Initialization Summary ---")
    print(f"Total processed custom Document objects: {len(all_processed_docs)}")
    if general_vector_store:
        print(f"General Vector Store (collection: '{general_vector_store.collection_name}') Initialized/Loaded.")
    else:
        print(f"General Vector Store FAILED to initialize.")
        
    if course_vector_store:
        print(f"Course Vector Store (collection: '{course_vector_store.collection_name}') Initialized/Loaded.")
    else:
        print(f"Course Vector Store FAILED to initialize.")
    print(f"Dense Embeddings: {'Initialized' if dense_embeddings else 'Not Initialized'}")
    print(f"Sparse Embeddings: {'Initialized' if sparse_embeddings else 'Not Initialized'}")
    print("-" * 30)

    # Run a quick test search on the general vector store
    if general_vector_store:
        print("\n=== Sample Search Results (General Documents) ===")
        query_general = "What are the computer science degree programs?"
        try:
            results_general = general_vector_store.similarity_search_with_score(query_general, k=2)
            if results_general:
                for doc, score in results_general:
                    print(f"Score: {score:.4f}")
                    print(f"Content: {doc.page_content[:150]}...")
                    print(f"Metadata: {doc.metadata}")
                    print("-" * 50)
            else:
                print("No results found for the general query.")
        except Exception as e:
            print(f"Error during general search test: {e}")
    else:
        print("\nSkipping general documents search test as general_vector_store is not available.")

    # Run a quick test search on the course vector store
    if course_vector_store:
        print("\n=== Sample Search Results (Course Documents) ===")
        query_course = "prerequisites for COMP1127" # Example course query
        try:
            results_course = course_vector_store.similarity_search_with_score(query_course, k=2)
            if results_course:
                for doc, score in results_course:
                    print(f"Score: {score:.4f}")
                    print(f"Content: {doc.page_content[:250]}...") # Show a bit more for course details
                    print(f"Metadata: {doc.metadata}")
                    print("-" * 50)
            else:
                print("No results found for the course query.")
        except Exception as e:
            print(f"Error during course search test: {e}")
    else:
        print("\nSkipping course documents search test as course_vector_store is not available.")

    print("\nIngestion and search testing completed.")