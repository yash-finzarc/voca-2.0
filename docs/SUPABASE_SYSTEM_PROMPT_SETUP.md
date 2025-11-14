# Supabase System Prompt Setup Guide

This guide explains how to set up Supabase for storing and managing the system prompt in VOCA.

## Prerequisites

1. A Supabase account and project
2. Supabase URL and Service Role Key (or Anon Key with proper RLS policies)

## Setup Steps

### 1. Add Environment Variables

Add these to your `.env` file:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key-or-anon-key
```

**Note:** For backend operations, use the **Service Role Key** (found in Project Settings > API). This bypasses Row Level Security (RLS) and allows the backend to read/write directly.

### 2. Create the Database Table

Run the SQL migration script in your Supabase SQL Editor:

1. Go to your Supabase project dashboard
2. Navigate to **SQL Editor**
3. Copy and paste the contents of `supabase_migration.sql`
4. Click **Run** to execute

Alternatively, you can run this SQL directly:

```sql
CREATE TABLE IF NOT EXISTS system_prompts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  key TEXT UNIQUE NOT NULL DEFAULT 'default',
  name TEXT,
  prompt TEXT NOT NULL,
  is_default BOOLEAN DEFAULT false,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Add name column if table already exists
ALTER TABLE system_prompts ADD COLUMN IF NOT EXISTS name TEXT;

INSERT INTO system_prompts (key, name, prompt, is_default) 
VALUES (
  'default',
  'Default',
  'You are Voca, a helpful voice assistant. Respond concisely and naturally. If asked how you can help, say: ''I can assist you with the information that is available to me.'' Keep responses brief and conversational.',
  true
)
ON CONFLICT (key) DO NOTHING;
```

### 3. Install Dependencies

Make sure to install the Supabase Python client:

```bash
pip install -r requirements.txt
```

This will install `supabase>=2.0.0`.

### 4. Test the Integration

Once everything is set up:

1. Start your FastAPI server: `python main_api_server.py`
2. Test the GET endpoint: `GET http://localhost:8000/api/system-prompt`
3. Test the POST endpoint: `POST http://localhost:8000/api/system-prompt` with body:
   ```json
   {
     "prompt": "Your custom system prompt here"
   }
   ```
4. Test the reset endpoint: `POST http://localhost:8000/api/system-prompt/reset`

## How It Works

### Architecture

- **`supabase_client.py`**: Initializes and manages the Supabase client connection
- **`system_prompt.py`**: Handles all system prompt operations (get, update, reset)
- **`api.py`**: Exposes REST endpoints for the frontend
- **`orchestrator.py`**: Uses the dynamic prompt when generating LLM responses

### Caching

The system prompt is cached in memory for 60 seconds to reduce database calls. The cache is automatically refreshed when:
- The prompt is updated via API
- The cache TTL expires
- The cache is manually cleared

### Fallback Behavior

If Supabase is unavailable or not configured:
- The system will use the default hardcoded prompt
- All operations will gracefully degrade
- Error messages will be logged but won't crash the application

## API Endpoints

### GET `/api/system-prompt`

Returns the current system prompt.

**Response:**
```json
{
  "prompt": "You are Voca, a helpful voice assistant...",
  "name": "Default"  // or the custom name if set
}
```

### POST `/api/system-prompt`

Updates the system prompt and optionally the name.

**Request:**
```json
{
  "prompt": "Your new system prompt",
  "name": "Custom Prompt Name"  // Optional
}
```

**Response:**
```json
{
  "status": "success",
  "message": "System prompt updated successfully"
}
```

### POST `/api/system-prompt/reset`

Resets the system prompt to the default value.

**Response:**
```json
{
  "status": "success",
  "message": "System prompt reset to default successfully"
}
```

## Troubleshooting

### "Supabase credentials not configured"

- Check that `SUPABASE_URL` and `SUPABASE_KEY` are set in your `.env` file
- Restart the server after adding environment variables

### "Failed to fetch system prompt"

- Verify your Supabase URL and key are correct
- Check that the `system_prompts` table exists in your database
- Ensure the table has a row with `key = 'default'`

### "Failed to update system prompt"

- Check that your Supabase key has write permissions
- If using RLS, ensure policies allow updates
- Check Supabase logs for detailed error messages

### Table doesn't exist

- Run the migration SQL script in Supabase SQL Editor
- Or manually create the table using the SQL provided above

## Security Considerations

1. **Service Role Key**: The backend uses the Service Role Key which has full database access. Keep this key secure and never expose it in frontend code.

2. **Row Level Security (RLS)**: If you want to use RLS, you'll need to:
   - Use the Anon Key instead of Service Role Key
   - Create RLS policies that allow read/write operations
   - Adjust the policies based on your authentication setup

3. **Environment Variables**: Never commit `.env` files to version control.

## Next Steps

- The frontend UI at `/system-prompt` should now work with these endpoints
- Changes to the system prompt take effect immediately (with 60-second cache)
- All LLM calls will use the prompt stored in Supabase

