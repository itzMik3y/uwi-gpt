# uwi-gpt
docker run -d -p 6333:6333 -p 6334:6334 qdrant/qdrant
run the ingestion script
python -m uvicorn api:app --host 0.0.0.0 --port 8000
# While the venv is active:
pip uninstall torch torchvision torchaudio -y
# While the venv is active (replace with your exact required versions/CUDA suffix):
pip install torch==2.5.1+cu121 torchvision==0.20.1+cu121 torchaudio==2.5.1+cu121 --index-url https://download.pytorch.org/whl/cu121
docker-compose up -d



## uwi-gpt PostgreSQL DB
# if first time setup or alemibc folder not present, then:
alembic init alembic

# only if there is a change in the model:
alembic revision --autogenerate -m "<version message for change in models>" 

# to commit the model changes to the PostreSQL on docker:
alembic upgrade head