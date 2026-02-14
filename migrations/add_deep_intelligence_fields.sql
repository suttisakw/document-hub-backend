-- Migration: Add Deep Intelligence fields to documents table
-- Date: 2026-02-13
-- Description: Adds fields for full_text, embedding, extracted_tables, extraction_report, 
--              confidence_report, validation_report, review_reason, ai_summary, and ai_insight

-- Add full_text column for storing complete OCR text
ALTER TABLE documents ADD COLUMN IF NOT EXISTS full_text TEXT;

-- Add embedding column for vector search (JSON array of floats)
ALTER TABLE documents ADD COLUMN IF NOT EXISTS embedding JSON;

-- Add extracted_tables column for storing table data
ALTER TABLE documents ADD COLUMN IF NOT EXISTS extracted_tables JSON;

-- Add extraction_report column for detailed extraction metadata
ALTER TABLE documents ADD COLUMN IF NOT EXISTS extraction_report JSON;

-- Add confidence_report column for confidence metrics
ALTER TABLE documents ADD COLUMN IF NOT EXISTS confidence_report JSON;

-- Add validation_report column for validation results
ALTER TABLE documents ADD COLUMN IF NOT EXISTS validation_report JSON;

-- Add review_reason column for manual review triggers
ALTER TABLE documents ADD COLUMN IF NOT EXISTS review_reason TEXT;

-- Add ai_summary column for AI-generated summaries
ALTER TABLE documents ADD COLUMN IF NOT EXISTS ai_summary TEXT;

-- Add ai_insight column for AI-generated insights (risk, anomalies, etc.)
ALTER TABLE documents ADD COLUMN IF NOT EXISTS ai_insight JSON;

-- Create index on full_text for faster text searches (optional but recommended)
-- CREATE INDEX IF NOT EXISTS idx_documents_full_text ON documents USING gin(to_tsvector('english', full_text));

COMMENT ON COLUMN documents.full_text IS 'Complete OCR extracted text from all pages';
COMMENT ON COLUMN documents.embedding IS 'Vector embedding for semantic search';
COMMENT ON COLUMN documents.extracted_tables IS 'Structured table data extracted from document';
COMMENT ON COLUMN documents.extraction_report IS 'Detailed metadata about extraction process';
COMMENT ON COLUMN documents.confidence_report IS 'Confidence scores and metrics';
COMMENT ON COLUMN documents.validation_report IS 'Validation results and errors';
COMMENT ON COLUMN documents.review_reason IS 'Reason why document requires manual review';
COMMENT ON COLUMN documents.ai_summary IS 'AI-generated summary of document content';
COMMENT ON COLUMN documents.ai_insight IS 'AI-generated insights including risk level and anomalies';
