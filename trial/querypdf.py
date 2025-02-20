from sentence_transformers import SentenceTransformer #pip install sentence-transformers

import psycopg2 #pip install psycopg2

# Load the embedding model
model = SentenceTransformer("BAAI/bge-base-en-v1.5")

def get_relevant_chunks(query, model):
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
        ORDER BY e.embedding <-> %s::vector 
        LIMIT 5;
    """, (query_embedding,))

    results = cur.fetchall()
    conn.close()
    
    return results

# Example Usage
print("querying postgres vector DB")
query = "What are the level 1 courses for computer science"
relevant_chunks = get_relevant_chunks(query, model)
for chunk in relevant_chunks:
    print(chunk)