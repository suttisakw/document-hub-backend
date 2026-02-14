-- ============================================================================
-- Complete Database Schema Migration
-- Date: 2026-02-13
-- Description: Adds all missing columns to sync database with SQLModel definitions
-- ============================================================================

-- ============================================================================
-- DOCUMENTS TABLE
-- ============================================================================
ALTER TABLE documents ADD COLUMN IF NOT EXISTS full_text TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS embedding JSON;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS extracted_tables JSON;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS extraction_report JSON;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS confidence_report JSON;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS validation_report JSON;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS review_reason TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS ai_summary TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS ai_insight JSON;

-- ============================================================================
-- OCR_JOBS TABLE
-- ============================================================================
ALTER TABLE ocr_jobs ADD COLUMN IF NOT EXISTS interface_id UUID;
ALTER TABLE ocr_jobs ADD COLUMN IF NOT EXISTS transaction_id UUID;
ALTER TABLE ocr_jobs ADD COLUMN IF NOT EXISTS request_id INTEGER;
ALTER TABLE ocr_jobs ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0;
ALTER TABLE ocr_jobs ADD COLUMN IF NOT EXISTS current_step VARCHAR(50) DEFAULT 'orchestrate';
ALTER TABLE ocr_jobs ADD COLUMN IF NOT EXISTS result_data JSON;
ALTER TABLE ocr_jobs ADD COLUMN IF NOT EXISTS result_json JSON;

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================

-- OCR Jobs indexes
CREATE INDEX IF NOT EXISTS idx_ocr_jobs_interface_id ON ocr_jobs(interface_id);
CREATE INDEX IF NOT EXISTS idx_ocr_jobs_transaction_id ON ocr_jobs(transaction_id);
CREATE INDEX IF NOT EXISTS idx_ocr_jobs_request_id ON ocr_jobs(request_id);
CREATE INDEX IF NOT EXISTS idx_ocr_jobs_current_step ON ocr_jobs(current_step);

-- Optional: Full-text search index on documents (uncomment if needed)
-- CREATE INDEX IF NOT EXISTS idx_documents_full_text ON documents USING gin(to_tsvector('english', full_text));

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================
-- Run these after migration to verify columns exist:
-- SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'documents' ORDER BY ordinal_position;
-- SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'ocr_jobs' ORDER BY ordinal_position;
