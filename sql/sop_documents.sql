-- RAG storage for procurement policy / SOP documents (Part 2).
-- Run in the Supabase SQL editor. Safe to re-run.
--
-- vector(1536) matches the embedding model text-embedding-3-small. Changing
-- the model to one with a different size means changing 1536 here, recreating
-- the table, and re-uploading every PDF.
--
-- The similarity search function is separate: sql/match_sop_documents.sql.

-- pgvector: adds the vector column type and distance operators (<=> etc.).
CREATE EXTENSION IF NOT EXISTS vector;

-- One row per chunk of an uploaded document.
CREATE TABLE IF NOT EXISTS sop_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,              -- source file name, e.g. 'procurement-policy.pdf'
    chunk_index INTEGER NOT NULL,     -- position of the chunk within the document
    page_start INTEGER,               -- PDF page the chunk starts on (1-based)
    page_end INTEGER,                 -- PDF page the chunk ends on
    content TEXT NOT NULL,            -- the chunk's text, returned to the agent
    embedding vector(1536) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (title, chunk_index)       -- a document can't have two chunk #3s
);

-- Approximate nearest-neighbour index for cosine distance (the <=> operator),
-- so searches don't compare the question against every row.
CREATE INDEX IF NOT EXISTS sop_documents_embedding_idx
    ON sop_documents USING hnsw (embedding vector_cosine_ops);
