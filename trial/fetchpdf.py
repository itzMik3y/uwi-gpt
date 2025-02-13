import fitz  # PyMuPDF

import nltk

import os

# Check if punkt is already downloaded
nltk_data_path = os.path.expanduser("~/nltk_data/tokenizers/punkt")
if not os.path.exists(nltk_data_path):
    nltk.download("punkt_tab")

from nltk.tokenize import sent_tokenize

from sentence_transformers import SentenceTransformer


def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    text = "\n".join([page.get_text() for page in doc])
    return text

pdf_text = extract_text_from_pdf("fst_undergraduate_student_handbook_2022-2023.pdf")


def chunk_text(text, max_tokens=300):
    """Splits text into smaller chunks, ensuring they don't exceed max_tokens."""
    sentences = sent_tokenize(text)
    chunks = []
    current_chunk = []
    current_length = 0

    for sentence in sentences:
        token_count = len(sentence.split())
        if current_length + token_count > max_tokens:
            chunks.append(" ".join(current_chunk))
            current_chunk = []
            current_length = 0
        current_chunk.append(sentence)
        current_length += token_count
    
    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks

chunks = chunk_text(pdf_text)
print(f"Total Chunks: {len(chunks)}")


# Use a well-known embedding model
model = SentenceTransformer("BAAI/bge-base-en-v1.5")  

def get_embeddings(chunks):
    return [model.encode(chunk).tolist() for chunk in chunks]

embeddings = get_embeddings(chunks)
print(f"Generated {len(embeddings)} embeddings.")
