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


COURSE_COLLECTION = "course_collection"
COURSE_DATA_PATH = os.path.join(BASE_DIR, "course_data")  # Directory for course JSON files
COURSE_CACHE_PATH = os.path.join(BASE_DIR, "course_cache.joblib")
COURSE_STATE_CACHE_PATH = os.path.join(BASE_DIR, "course_state.json")

# Add the format_term_label and create_documents_from_course_data functions exactly as you provided

def load_course_data(course_data_dir: str) -> List[Dict[str, Any]]:
    """Load course data from JSON files in the specified directory."""
    courses = []
    if not os.path.exists(course_data_dir):
        os.makedirs(course_data_dir)
        logging.warning(f"Course data directory {course_data_dir} did not exist. Created it.")
        return courses
    
    for filename in os.listdir(course_data_dir):
        if filename.endswith('.json'):
            try:
                file_path = os.path.join(course_data_dir, filename)
                with open(file_path, 'r') as f:
                    data = json.load(f)
                    # Handle both direct list or object with courses field
                    if isinstance(data, list):
                        courses.extend(data)
                    elif isinstance(data, dict) and 'courses' in data:
                        courses.extend(data['courses'])
                    else:
                        logging.warning(f"Unexpected JSON structure in {filename}")
            except Exception as e:
                logging.error(f"Error loading course data from {filename}: {e}")
    
    logging.info(f"Loaded {len(courses)} course entries from {course_data_dir}")
    return courses


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

def initialize_course_vector_store(
    course_data_dir: str = COURSE_DATA_PATH,
    collection_name: str = COURSE_COLLECTION,
    course_cache_path: str = COURSE_CACHE_PATH,
    state_cache_path: str = COURSE_STATE_CACHE_PATH,
    url: str = "http://localhost:6333"
):
    """Initialize or update the course vector store."""
    init_start = time.perf_counter()
    
    # Initialize embedding models
    dense_embeddings = HuggingFaceEmbeddings(
        model_name="BAAI/bge-m3",
        model_kwargs={"trust_remote_code": True, "device": device},
        encode_kwargs={'normalize_embeddings':True}
    )
    sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")
    
    # Create course data directory if it doesn't exist
    if not os.path.exists(course_data_dir):
        os.makedirs(course_data_dir)
        logging.info(f"Created course data directory: {course_data_dir}")
    
    # Check if files have changed
    current_state = {}
    for filename in os.listdir(course_data_dir):
        if filename.endswith('.json'):
            full_path = os.path.join(course_data_dir, filename)
            current_state[filename] = os.path.getmtime(full_path)
    
    # Load previous state
    previous_state = {}
    if os.path.exists(state_cache_path):
        try:
            with open(state_cache_path, "r") as f:
                previous_state = json.load(f)
        except Exception as e:
            logging.error(f"Error loading course state cache: {e}")
    
    # Determine if reprocessing is needed
    reprocess = (current_state != previous_state)
    
    # Extract host information for connections
    import re
    host_match = re.match(r'https?://([^:/]+)(?::\d+)?', url)
    grpc_host = host_match.group(1) if host_match else "localhost"
    grpc_port = 6334
    
    # Load course data regardless - we'll need it if we're creating a new collection
    logging.info("Loading and processing course data...")
    course_data = load_course_data(course_data_dir)
    
    if not course_data:
        logging.warning("No course data found. Skipping course vector store creation.")
        return None, None
    
    course_docs = create_documents_from_course_data(course_data)
    logging.info(f"Created {len(course_docs)} course documents.")
    
    # Convert to LangChain documents
    langchain_course_docs = []
    for doc in course_docs:
        langchain_course_docs.append(LangchainDocument(
            page_content=doc.page_content,
            metadata=doc.metadata
        ))
    
    # APPROACH 1: Try with a different collection name
    # If the original collection can't be deleted, use a new one with timestamp
    if reprocess:
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        new_collection_name = f"{collection_name}_{timestamp}"
        logging.info(f"Using new collection name: {new_collection_name} to avoid deletion issues")
        
        # Create vector store with the new name
        VECTOR_BATCH_SIZE = 250
        try:
            # Try with gRPC first
            logging.info(f"Creating collection '{new_collection_name}' with gRPC...")
            vector_store = QdrantVectorStore.from_documents(
                langchain_course_docs,
                embedding=dense_embeddings,
                sparse_embedding=sparse_embeddings,
                host=grpc_host,
                port=grpc_port,
                prefer_grpc=True,
                collection_name=new_collection_name,
                force_recreate=True,
                retrieval_mode=RetrievalMode.HYBRID,
                batch_size=VECTOR_BATCH_SIZE,
                vector_name="default"
            )
            # Save the documents cache
            joblib.dump(course_docs, course_cache_path)
            # Save the current state
            with open(state_cache_path, "w") as f:
                json.dump(current_state, f)
            
            init_end = time.perf_counter()
            logging.info(f"Course vector store initialization took {init_end - init_start:.2f} seconds")
            return course_docs, vector_store
        except Exception as e:
            logging.warning(f"Error creating collection with gRPC: {e}")
            
            # Fall back to HTTP
            try:
                logging.info(f"Creating collection '{new_collection_name}' with HTTP...")
                vector_store = QdrantVectorStore.from_documents(
                    langchain_course_docs,
                    embedding=dense_embeddings,
                    sparse_embedding=sparse_embeddings,
                    url=url,
                    collection_name=new_collection_name,
                    force_recreate=True,
                    retrieval_mode=RetrievalMode.HYBRID,
                    batch_size=VECTOR_BATCH_SIZE,
                    vector_name="default"
                )
                # Save the documents cache
                joblib.dump(course_docs, course_cache_path)
                # Save the current state
                with open(state_cache_path, "w") as f:
                    json.dump(current_state, f)
                
                init_end = time.perf_counter()
                logging.info(f"Course vector store initialization took {init_end - init_start:.2f} seconds")
                return course_docs, vector_store
            except Exception as e2:
                logging.error(f"Error creating collection with HTTP: {e2}")
                # Continue to approach 2 if this fails
    
    # APPROACH 2: Try to load the existing collection if we're not reprocessing
    # or if approach 1 failed
    try:
        # Check if collection exists
        from qdrant_client import QdrantClient
        client = QdrantClient(url=url)
        collections = client.get_collections().collections
        collection_exists = any(collection.name == collection_name for collection in collections)
        
        if collection_exists:
            logging.info(f"Trying to load existing collection '{collection_name}'...")
            
            # Try with gRPC first
            try:
                vector_store = QdrantVectorStore.from_existing_collection(
                    embedding=dense_embeddings,
                    sparse_embedding=sparse_embeddings,
                    collection_name=collection_name,
                    host=grpc_host,
                    port=grpc_port,
                    prefer_grpc=True,
                    retrieval_mode=RetrievalMode.HYBRID,
                    vector_name="default"
                )
                
                # If we got here, we successfully loaded the collection
                logging.info(f"Successfully loaded existing collection '{collection_name}'")
                
                # Save the documents cache if needed
                joblib.dump(course_docs, course_cache_path)
                # Save the current state if needed
                if reprocess:
                    with open(state_cache_path, "w") as f:
                        json.dump(current_state, f)
                
                init_end = time.perf_counter()
                logging.info(f"Course vector store initialization took {init_end - init_start:.2f} seconds")
                return course_docs, vector_store
            except Exception as e:
                logging.warning(f"Error loading collection with gRPC: {e}, trying HTTP...")
                
                # Fall back to HTTP
                try:
                    vector_store = QdrantVectorStore.from_existing_collection(
                        embedding=dense_embeddings,
                        sparse_embedding=sparse_embeddings,
                        collection_name=collection_name,
                        url=url,
                        retrieval_mode=RetrievalMode.HYBRID,
                        vector_name="default"
                    )
                    
                    # If we got here, we successfully loaded the collection
                    logging.info(f"Successfully loaded existing collection '{collection_name}'")
                    
                    # Save the documents cache if needed
                    joblib.dump(course_docs, course_cache_path)
                    # Save the current state if needed
                    if reprocess:
                        with open(state_cache_path, "w") as f:
                            json.dump(current_state, f)
                    
                    init_end = time.perf_counter()
                    logging.info(f"Course vector store initialization took {init_end - init_start:.2f} seconds")
                    return course_docs, vector_store
                except Exception as e2:
                    logging.error(f"Error loading collection with HTTP: {e2}")
                    # If we can't load it, continue to approach 3
        
    except Exception as e:
        logging.error(f"Error checking or loading collections: {e}")
    
    # APPROACH 3: Try direct REST API calls to delete the collection
    # This is a last resort if all other approaches failed
    try:
        import requests
        
        # Try to delete via REST API directly
        logging.info(f"Attempting to delete collection '{collection_name}' via direct REST API...")
        delete_url = f"{url}/collections/{collection_name}"
        response = requests.delete(delete_url)
        
        if response.status_code == 200 or response.status_code == 404:
            logging.info(f"Successfully deleted or collection not found: {response.status_code}")
            
            # Now try to create it again
            try:
                logging.info(f"Creating collection '{collection_name}' after REST API deletion...")
                vector_store = QdrantVectorStore.from_documents(
                    langchain_course_docs,
                    embedding=dense_embeddings,
                    sparse_embedding=sparse_embeddings,
                    url=url,
                    collection_name=collection_name,
                    force_recreate=False,  # We've already deleted it
                    retrieval_mode=RetrievalMode.HYBRID,
                    batch_size=250,
                    vector_name="default"
                )
                
                # Save the documents cache
                joblib.dump(course_docs, course_cache_path)
                # Save the current state
                with open(state_cache_path, "w") as f:
                    json.dump(current_state, f)
                
                init_end = time.perf_counter()
                logging.info(f"Course vector store initialization took {init_end - init_start:.2f} seconds")
                return course_docs, vector_store
            except Exception as e:
                logging.error(f"Error creating collection after REST API deletion: {e}")
        else:
            logging.error(f"Failed to delete collection via REST API: {response.status_code}, {response.text}")
    
    except Exception as e:
        logging.error(f"Error with direct REST API approach: {e}")
    
    # If all approaches fail, raise an exception
    logging.error(f"All approaches to create/load course vector store failed")
    raise Exception("Failed to initialize course vector store after multiple attempts")


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
    
    # Initialize or load course data vector store
    COURSE_DATA_DIR = os.path.join(BASE_DIR, "course_data")
    COURSE_COLLECTION = "course_collection"
    COURSE_CACHE_PATH = os.path.join(BASE_DIR, "course_cache.joblib")
    COURSE_STATE_CACHE_PATH = os.path.join(BASE_DIR, "course_state.json")
    
    course_docs, course_vector_store = initialize_course_vector_store(
        course_data_dir=COURSE_DATA_DIR,
        collection_name=COURSE_COLLECTION,
        course_cache_path=COURSE_CACHE_PATH,
        state_cache_path=COURSE_STATE_CACHE_PATH,
        url=QDRANT_URL,
    )
    
    # Test document vector store
    print("\n=== Document Vector Store Test ===")
    doc_query = "What are the computer science degree programs?"
    doc_results = vector_store.similarity_search_with_score(doc_query, k=3)
    
    for doc, score in doc_results:
        print(f"Score: {score:.4f}")
        print(f"Content: {doc.page_content[:150]}...")
        print(f"Metadata: {doc.metadata}")
        print("-" * 50)
    
    # Test course vector store if available
    if course_vector_store:
        print("\n=== Course Vector Store Test ===")
        course_query = "BIOC3251 prerequisites"
        course_results = course_vector_store.similarity_search_with_score(course_query, k=3)
        
        for doc, score in course_results:
            print(f"Score: {score:.4f}")
            print(f"Content: {doc.page_content[:150]}...")
            print(f"Metadata: {doc.metadata}")
            print("-" * 50)
        
        # Test dual retriever
        print("\n=== Dual Retriever Test ===")
        from retrievers import DualCollectionRetriever
        from sentence_transformers import CrossEncoder
        
        # Create retrievers for testing
        doc_retriever = vector_store.as_retriever(search_kwargs={"k": 5})
        course_retriever = course_vector_store.as_retriever(search_kwargs={"k": 5})
        
        # Create cross-encoder for reranking
        try:
            cross_encoder = CrossEncoder("BAAI/bge-reranker-v2-m3")
        except Exception as e:
            print(f"Could not load cross-encoder: {e}")
            cross_encoder = None
        
        # Create dual retriever
        dual_retriever = DualCollectionRetriever(
            primary_retriever=doc_retriever,
            course_retriever=course_retriever,
            use_reranking=cross_encoder is not None,
            max_documents=10,
            max_course_documents=3,
            cross_encoder=cross_encoder
        )
        
        # Test with a query that might match both collections
        dual_query = "Computer Science course requirements"
        dual_results = dual_retriever.get_relevant_documents(dual_query)
        
        print(f"Dual retriever returned {len(dual_results)} documents:")
        for i, doc in enumerate(dual_results):
            doc_source = "course_data.json" in str(doc.metadata.get("source_file", ""))
            source_type = "COURSE" if doc_source else "DOCUMENT"
            print(f"{i+1}. [{source_type}] {doc.metadata.get('heading', 'No heading')}")
            print(f"   Content: {doc.page_content[:100]}...")
            print()
    else:
        print("\nCourse vector store not available. Skipping course tests.")

    print("\nIngestion and search testing completed successfully.")