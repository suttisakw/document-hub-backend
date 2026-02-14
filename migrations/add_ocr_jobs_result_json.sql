-- Migration: Add missing columns to ocr_jobs table
-- Date: 2026-02-13
-- Description: Adds all missing fields to ocr_jobs table

-- Add missing columns
ALTER TABLE ocr_jobs ADD COLUMN IF NOT EXISTS interface_id UUID;
ALTER TABLE ocr_jobs ADD COLUMN IF NOT EXISTS transaction_id UUID;
ALTER TABLE ocr_jobs ADD COLUMN IF NOT EXISTS request_id INTEGER;
ALTER TABLE ocr_jobs ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0;
ALTER TABLE ocr_jobs ADD COLUMN IF NOT EXISTS current_step VARCHAR(50) DEFAULT 'orchestrate';
ALTER TABLE ocr_jobs ADD COLUMN IF NOT EXISTS result_data JSON;
ALTER TABLE ocr_jobs ADD COLUMN IF NOT EXISTS result_json JSON;

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_ocr_jobs_interface_id ON ocr_jobs(interface_id);
CREATE INDEX IF NOT EXISTS idx_ocr_jobs_transaction_id ON ocr_jobs(transaction_id);
CREATE INDEX IF NOT EXISTS idx_ocr_jobs_request_id ON ocr_jobs(request_id);
CREATE INDEX IF NOT EXISTS idx_ocr_jobs_current_step ON ocr_jobs(current_step);
