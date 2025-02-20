from sentence_transformers import CrossEncoder

# Load Reranker Model
reranker = CrossEncoder("BAAI/bge-reranker-base")

# Example Retrieved Results from FAISS
retrieved_docs = [
    "Computer Science at UWI includes AI, Software Engineering, and Networking.",
    "The Faculty of Science and Technology at UWI offers various degrees.",
    "UWI has three campuses in the Caribbean."
]

query = "What Computer Science courses does UWI offer?"

# Rerank using CrossEncoder
rerank_scores = reranker.predict([(query, doc) for doc in retrieved_docs])

# Sort by relevance score
reranked_results = sorted(zip(rerank_scores, retrieved_docs), reverse=True)

# Print Reranked Results
for score, doc in reranked_results:
    print(f"Score: {score:.4f} | {doc}")
    
    
randomlist = [chunk for score, chunk in reranked_results]
print(randomlist[0])
