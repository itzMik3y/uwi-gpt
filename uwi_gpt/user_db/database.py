from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

from dotenv import load_dotenv
import os

load_dotenv()  # Loads .env from the root of the project

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+asyncpg://user_api:secret@localhost:5444/user_db"
)

# DATABASE_URL = "postgresql+asyncpg://user_api:secret@localhost:5432/user_db"

engine = create_async_engine(DATABASE_URL, echo=True)  # creates async engine object
# The create_async_engine() function is used to create an asynchronous engine object.
# This engine object is used to connect to the database and execute SQL statements.
# The echo=True option enables SQLAlchemy's logging, which can be helpful for debugging.
AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)  # creates session object
# The echo=True option enables SQLAlchemy's logging, which can be helpful for debugging.
# The expire_on_commit=False option prevents the session from expiring objects after commit, which is useful for async sessions.
# This allows you to keep using the objects after committing them to the database.
Base = declarative_base()  # Base class for declarative models
# The declarative_base() function is used to create a base class for declarative models.
# This base class is used to define the structure of the database tables and their relationships.
# It provides a way to define the tables and their columns using Python classes and attributes.


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


# The get_db() function is an asynchronous generator that provides a session object for database operations.
# It uses the AsyncSessionLocal object to create a new session and yields it for use in database operations.
