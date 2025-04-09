# uwi-gpt
docker run -d -p 6333:6333 -p 6334:6334 qdrant/qdrant
run the ingestion script
python -m uvicorn api:app --host 0.0.0.0 --port 8000