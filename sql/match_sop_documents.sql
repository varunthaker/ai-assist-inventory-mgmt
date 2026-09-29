-- Run in the Supabase SQL editor after sql/sop_documents.sql. Safe to re-run.
-- Used by backend/app/rag/search.py.
--
-- Similarity search, called from Python via supabase.rpc("match_sop_documents").
-- The REST API cannot ORDER BY vector distance itself, hence a function.
-- similarity = 1 - cosine distance: 1.0 identical meaning, ~0 unrelated.

CREATE OR REPLACE FUNCTION match_sop_documents(
    query_embedding vector(1536),
    match_count INTEGER DEFAULT 3,
    min_similarity FLOAT DEFAULT 0
)
RETURNS TABLE (
    title TEXT,
    chunk_index INTEGER,
    page_start INTEGER,
    page_end INTEGER,
    content TEXT,
    similarity FLOAT
)
LANGUAGE sql STABLE
AS $$
    SELECT title, chunk_index, page_start, page_end, content,
           1 - (embedding <=> query_embedding) AS similarity
    FROM sop_documents
    WHERE 1 - (embedding <=> query_embedding) >= min_similarity
    ORDER BY embedding <=> query_embedding
    LIMIT match_count;
$$;
