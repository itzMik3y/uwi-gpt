import fitz  # pip install pymupdf
import spacy # pip install spacy
from sentence_transformers import SentenceTransformer #pip install sentence-transformers

import psycopg2
import numpy as np

# Load spaCy's small English model (make sure it's installed)
nlp = spacy.load("en_core_web_sm")

def extract_text_from_pdf(pdf_path):
    """Extracts text from a PDF file."""
    doc = fitz.open(pdf_path)
    text = "\n".join([page.get_text() for page in doc])
    return text

pdf_text = extract_text_from_pdf("fst_undergraduate_student_handbook_2022-2023.pdf")

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

chunks = chunk_text(pdf_text)
print(f"Total Chunks: {len(chunks)}")

# Load the embedding model
model = SentenceTransformer("BAAI/bge-base-en-v1.5")

def get_embeddings(chunks):
    """Generates embeddings for each text chunk."""
    return [model.encode(chunk).tolist() for chunk in chunks]

embeddings = get_embeddings(chunks)
print(f"Generated {len(embeddings)} embeddings.")


# def store_embeddings(chunks, embeddings):
#     conn = psycopg2.connect("dbname=uwi-gpt user=postgres password=Firekid109")
#     cur = conn.cursor()
    
#     for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
#         cur.execute("""
#             INSERT INTO embeddings (content_id, embedding)
#             VALUES (%s, %s);
#         """, (f"chunk_{i}", np.array(embedding)))
    
#     conn.commit()
#     cur.close()
#     conn.close()
#     print("Embeddings stored in PostgreSQL.")

# store_embeddings(chunks, embeddings)

def insert_chunks(content_id, chunks):
    conn = psycopg2.connect("dbname=uwi_gpt user=postgres password=Firekid109")
    cur = conn.cursor()

    for i, chunk in enumerate(chunks):
        cur.execute("INSERT INTO chunks (content_id, chunk_order, chunk) VALUES (%s, %s, %s) RETURNING id;", 
                    (content_id, i, chunk))
    
    conn.commit()
    cur.close()
    conn.close()
    
insert_chunks(1,chunks)
    
def insert_embeddings(chunk_ids, embeddings):
    
    conn = psycopg2.connect("dbname=uwi_gpt user=postgres password=Firekid109")
    cur = conn.cursor()

    for chunk_id, embedding in zip(chunk_ids, embeddings):
        cur.execute("""
            INSERT INTO embeddings (chunk_id, embedding) 
            VALUES (%s, %s);
        """, (chunk_id, np.array(embedding)))  

    conn.commit()
    cur.close()
    conn.close()
    
chunk_ids_list = [i for i in range(1, len(chunks) + 1)]
insert_embeddings(chunk_ids_list, embeddings)


def get_relevant_chunks(query):
    """Finds the most relevant chunks based on query similarity."""
    conn = psycopg2.connect("dbname=uwi_gpt user=postgres password=Firekid109")
    cur = conn.cursor()

    # Generate embedding for the query
    query_embedding = model.encode(query).tolist()

    # Find the most similar chunks using cosine similarity
    cur.execute("""
        SELECT ch.chunk, c.title, c.summary 
        FROM embeddings e
        JOIN chunks ch ON e.chunk_id = ch.id
        JOIN content c ON ch.content_id = c.id
        ORDER BY e.embedding <-> %s 
        LIMIT 5;
    """, (np.array(query_embedding),))

    results = cur.fetchall()
    conn.close()
    
    return results


query = "What are the first year courses for computer science"
relevant_chunks = get_relevant_chunks(query)
for chunk in relevant_chunks:
    print(chunk)