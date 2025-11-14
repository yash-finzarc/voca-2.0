-- Migration script to add 'name' column to existing system_prompts table
-- Run this in your Supabase SQL Editor if you already have the table created

-- Add name column if it doesn't exist
ALTER TABLE system_prompts ADD COLUMN IF NOT EXISTS name TEXT;

-- Update existing row with default name if name is NULL
UPDATE system_prompts 
SET name = 'Default' 
WHERE key = 'default' AND name IS NULL;

