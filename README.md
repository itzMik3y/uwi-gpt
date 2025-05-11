# uwi-gpt

run the ingestion script
python -m  main
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

to update requirements
pip freeze > requirements.txt

extensions search screen


# deletes everything from the db

-- Disable referential integrity temporarily (PostgreSQL-specific)
SET session_replication_role = replica;

DELETE FROM bookings;
DELETE FROM availability_slots;
DELETE FROM user_tokens;
DELETE FROM course_grades;
DELETE FROM enrolled_courses;
DELETE FROM terms;
DELETE FROM courses;
DELETE FROM admins;
DELETE FROM users;

-- Re-enable referential integrity
SET session_replication_role = DEFAULT;


# autofills db from script
python -m user_db.populate

# to merge different changes to migrations
alembic heads
alembic merge -m "merge branches" <revision_1> <revision_2>
alembic upgrade head
