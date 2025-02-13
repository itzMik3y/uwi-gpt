from flask import Flask, jsonify
import psycopg2
import subprocess


import requests
from sentence_transformers import SentenceTransformer #pip install sentence-transformers

app = Flask(__name__)

DB_CONFIG = {
    "dbname": "uwi_gpt",
    "user": "postgres",
    "password": "Firekid109",
    "host": "localhost",
    "port": "5432"
}



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

def send_to_deepseek(query, context):
    """Sends a chunk of data to DeepSeek AI via terminal ollama."""
    
    prompt = f"""
    ### SYSTEM INSTRUCTIONS:
    You are an AI chatbot designed to provide accurate and helpful responses to queries about The University of the West Indies (UWI) Mona. Your responses should be factual, concise, and directly related to the context provided.

    If the context does not contain relevant information, suggest alternative ways for the user to obtain their answer (e.g., directing them to the official UWI website, student services, or administrative offices).

    ---

    ### CONTEXT (FROM DATABASE):
    {context[0]}
    {context[1]}

    ---

    ### USER QUERY:
    {query}

    ---

    ### RESPONSE GUIDELINES:
    1. **Use Only Relevant Context** – Answer based on the provided context. If the answer is unclear, acknowledge that and suggest an alternative resource.
    2. **Be Concise** – Keep responses clear and to the point while ensuring completeness.
    3. **Maintain a Helpful & Friendly Tone** – Act like an intelligent assistant for students, faculty, and visitors.
    4. **Provide Additional Resources (if applicable)** – If a response requires external resources, reference the correct department or website.
    5. **No Guesswork** – If the context does not contain sufficient information, state that you cannot provide an answer and suggest an alternative source.

    ---

    **Now, generate a response based on the given CONTEXT and USER QUERY.**
    """

    
    try:
        # Execute the Ollama command with the query
        process = subprocess.run(
            ["ollama", "run", "deepseek-r1:7b", prompt],
            capture_output=True,
            text=True,
            check=True
        )

        # Extract model output
        response_text = process.stdout.strip()

        return {"response": response_text}

    except subprocess.CalledProcessError as e:
        return {"error": "Failed to process request", "details": str(e)}

@app.route('/')
def home():
    return "Home Page"

@app.route('/get-data', methods=['GET'])
def get_data():
    """API endpoint to return data."""
    query = "What are the level 1 courses for computer science"
    data = get_relevant_chunks(query, model)
    result = send_to_deepseek(query, data)
    return result
    

    
if __name__ == '__main__':
    app.run(debug=True)
