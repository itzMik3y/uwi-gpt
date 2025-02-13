import fitz  # pip install pymupdf
import spacy # pip install spacy
from sentence_transformers import SentenceTransformer #pip install sentence-transformers

import psycopg2 #pip install psycopg2
import numpy as np #pip install numpy

print(f"Loading spacy library...")
# Load spaCy's small English model (make sure it's installed)
nlp = spacy.load("en_core_web_sm")
print(f"Loaded spacy library...")


def extract_text_from_pdf(pdf_path):
    """Extracts text from a PDF file."""
    doc = fitz.open(pdf_path)
    text = "\n".join([page.get_text() for page in doc])
    return text

print(f"Extracting text from PDF...")
pdf_text = extract_text_from_pdf("fst_undergraduate_student_handbook_2022-2023.pdf")
print("Extracted text from PDF...")

def chunk_text(text, max_tokens=300):
    """Splits text into smaller chunks using spaCy sentence tokenization."""
    doc = nlp(text)
    sentences = [sent.text.strip() for sent in doc.sents]

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

print("splits text into smaller tokens...")
chunks = chunk_text(pdf_text)
print("splitted text into smaller tokens...")

print(f"Total Chunks: {len(chunks)}")

# Load the embedding model
model = SentenceTransformer("BAAI/bge-base-en-v1.5")

def get_embeddings(chunks):
    """Generates embeddings for each text chunk."""
    return [model.encode(chunk).tolist() for chunk in chunks]

print("generating embeddings...")
embeddings = get_embeddings(chunks)
print("generated embeddings...")

print(f"Generated {len(embeddings)} embeddings.")


def insert_content(title, author, publication_date, content_type, faculty, source_url, summary):
    """Inserts content into the content table and returns the inserted content_id."""
    conn = psycopg2.connect("dbname=uwi_gpt user=postgres password=Firekid109")
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO content (title, author, publication_date, content_type, faculty, source_url, summary) 
        VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id;
    """, (title, author, publication_date, content_type, faculty, source_url, summary))

    content_id = cur.fetchone()[0]  # Get the inserted content ID
    conn.commit()
    cur.close()
    conn.close()
    
    return content_id  # Return the new content ID


print("Inserting Content into postgres DB...")
content_id = insert_content(
    title="fst_undergraduate_student_handbook_2022-2023",
    author=None,
    publication_date=None,
    content_type="Book",
    faculty=None,
    source_url=None,
    summary=None,
)

print(f"Inserted content ID: {content_id}...")


def insert_chunks(content_id, chunks):
    """Inserts chunks and returns their generated IDs."""
    conn = psycopg2.connect("dbname=uwi_gpt user=postgres password=Firekid109")
    cur = conn.cursor()
    
    chunk_ids = []
    for i, chunk in enumerate(chunks):
        cur.execute(
            "INSERT INTO chunks (content_id, chunk_order, chunk) VALUES (%s, %s, %s) RETURNING id;", 
            (content_id, i, chunk)
        )
        chunk_ids.append(cur.fetchone()[0])  # Get the inserted ID

    conn.commit()
    cur.close()
    conn.close()

    return chunk_ids  # Return the list of chunk IDs

print("inserting chunks into postgres...")
chunk_ids = insert_chunks(content_id, chunks)
print("inserted chunks into postgres...")

def insert_embeddings(chunk_ids, embeddings):
    """Inserts embeddings for each chunk."""
    conn = psycopg2.connect("dbname=uwi_gpt user=postgres password=Firekid109")
    cur = conn.cursor()

    for chunk_id, embedding in zip(chunk_ids, embeddings):
        cur.execute(
            "INSERT INTO embeddings (chunk_id, embedding) VALUES (%s, %s::vector);",
            (chunk_id, np.array(embedding).tolist())  # Convert numpy array to list
        )

    conn.commit()
    cur.close()
    conn.close()
 
print("inserting embeddings into postgres...")   
insert_embeddings(chunk_ids, embeddings)
print("inserted embeddings into postgres")


