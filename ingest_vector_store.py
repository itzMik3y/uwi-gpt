# ingest_vector_store.py
import logging
from ingestion import initialize_documents_and_vector_store

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    docs, vector_store, embedding_model = initialize_documents_and_vector_store(
        doc_folder="./docs",
        persist_directory="./chroma_db_bilingual",
        docs_cache_path="docs_cache.joblib",
        state_cache_path="docs_state.json"
    )
    logging.info(f"Ingestion complete: Processed {len(docs)} document chunks and built the vector store.")
