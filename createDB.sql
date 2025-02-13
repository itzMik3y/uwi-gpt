CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE content (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    author TEXT,
    publication_date DATE,
    content_type TEXT CHECK (content_type IN ('Book', 'Website', 'Article')),
    faculty TEXT,
    source_url TEXT,
    summary TEXT
);

CREATE TABLE keywords (
    id SERIAL PRIMARY KEY,
    content_id INT REFERENCES content(id) ON DELETE CASCADE,
    keyword TEXT NOT NULL
);


CREATE TABLE chunks (
    id SERIAL PRIMARY KEY,
    content_id INT REFERENCES content(id) ON DELETE CASCADE,
    chunk_order INT NOT NULL,  -- To maintain order of chunks
    chunk TEXT NOT NULL
);


CREATE TABLE embeddings (
    id SERIAL PRIMARY KEY,
    chunk_id INT REFERENCES chunks(id) ON DELETE CASCADE,
    embedding VECTOR(768)  -- Adjust based on DeepSeek’s embedding size
);

