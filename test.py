from sentence_transformers import CrossEncoder, SentenceTransformer, util

# Load a pre-trained model
# model = SentenceTransformer("BAAI/bge-base-en-v1.5")
# model = SentenceTransformer('all-MiniLM-L6-v2')
model = CrossEncoder("BAAI/bge-reranker-base")



# Define a search query
query = "Best places to visit in Paris"

# Example search results (could be from a search engine)
documents = [
    "Top tourist attractions in Paris",
    "Best restaurants to try in Paris",
    "Eiffel Tower: A must-visit landmark",
    "History of Paris and its architecture",
]

# Encode query and documents into vectors
query_embedding = model.encode(query, convert_to_tensor=True)
document_embeddings = model.encode(documents, convert_to_tensor=True)

# Compute cosine similarity
scores = util.cos_sim(query_embedding, document_embeddings)[0]

# Pair scores with documents and sort by score (descending)
reranked_results = sorted(zip(scores.tolist(), documents), reverse=True, key=lambda x: x[0])

# Print reranked results
print("Reranked Search Results:")
for score, doc in reranked_results:
    print(f"Score: {score:.4f} | {doc}")
