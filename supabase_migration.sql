-- Migration script for system_prompts table in Supabase
-- Run this in your Supabase SQL Editor
-- NOTE: This matches the table structure you created

-- Create the system_prompts table (if not already created)
CREATE TABLE IF NOT EXISTS system_prompts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  key TEXT UNIQUE NOT NULL DEFAULT 'default',
  name TEXT,
  prompt TEXT NOT NULL,
  is_default BOOLEAN DEFAULT false,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Add name column if table already exists (for existing installations)
ALTER TABLE system_prompts ADD COLUMN IF NOT EXISTS name TEXT;

-- Insert default prompt if it doesn't exist
INSERT INTO system_prompts (key, name, prompt, is_default) 
VALUES (
  'default',
  'Default',
  'You are Voca, a helpful voice assistant. Respond concisely and naturally. If asked how you can help, say: ''I can assist you with the information that is available to me.'' Keep responses brief and conversational.',
  true
)
ON CONFLICT (key) DO NOTHING;

-- Create an index on key for faster lookups
CREATE UNIQUE INDEX IF NOT EXISTS system_prompts_key_idx ON system_prompts(key);

-- Grant necessary permissions (adjust based on your RLS policies)
-- If using Row Level Security, you may need to create policies
-- For now, we'll assume service role key has full access

