-- Migration: Add device_id to form_entries table
-- This adds support for tracking which mobile device uploaded a form
-- Run this with: psql -U postgres -d smartform < scripts/migrations/add_device_id_to_form_entries.sql

-- Add the uploaded_by_device_id column
ALTER TABLE form_entries
ADD COLUMN IF NOT EXISTS uploaded_by_device_id VARCHAR(255);

-- Create index for faster queries by device_id
CREATE INDEX IF NOT EXISTS idx_form_entries_device_id
ON form_entries(uploaded_by_device_id) WHERE uploaded_by_device_id IS NOT NULL;

-- Add comment
COMMENT ON COLUMN form_entries.uploaded_by_device_id IS 'Mobile device ID for tracking uploads from mobile app';

-- Verify the change
\d form_entries;
