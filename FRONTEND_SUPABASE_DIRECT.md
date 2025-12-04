# Frontend Direct Supabase Integration Guide

## Overview

The backend is now **read-only** for system prompts. The frontend (Next.js) should manage all system prompt operations directly via Supabase to avoid HTTP barriers and simplify the architecture.

## Backend Endpoints (Read-Only)

### ✅ Still Available (Read Operations)

1. **GET `/api/system-prompt`** - Get current active prompt
   - Returns: `{ prompt, name, welcome_message }`
   - Used by backend to fetch prompts for conversations

2. **GET `/api/system-prompt/list`** - List all prompts
   - Returns: Array of all prompts with metadata
   - Used by frontend/backend to see available prompts

### ❌ Deprecated (Write Operations)

These endpoints now return an info message directing you to use Supabase directly:
- `POST/PUT/PATCH /api/system-prompt` - Create/Update prompts
- `POST/PUT/PATCH /api/system-prompt/activate` - Activate prompts
- `PUT/PATCH/POST /api/system-prompt/welcome-message` - Update welcome messages
- `POST /api/system-prompt/reset` - Reset prompts

## Frontend Implementation (Next.js)

### Setup Supabase Client

**IMPORTANT: Always use HTTPS for Supabase URLs!**

```typescript
import { createClient } from '@supabase/supabase-js'

// Make sure your Supabase URL uses HTTPS (not HTTP)
// If your env variable has http://, convert it to https://
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
  .replace(/^http:\/\//, 'https://') // Force HTTPS

const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

export const supabase = createClient(supabaseUrl, supabaseAnonKey)
```

**Common Issue: CORS Error with HTTP URLs**
- If you see "Redirect is not allowed for a preflight request", your Supabase URL is using `http://` instead of `https://`
- Supabase always redirects HTTP to HTTPS, which breaks CORS preflight requests
- Solution: Always use `https://` in your Supabase URL

### Create a New Prompt

```typescript
async function createPrompt(prompt: string, name?: string, welcomeMessage?: string) {
  const { data, error } = await supabase
    .from('system_prompts')
    .insert({
      prompt: prompt.trim(),
      name: name?.trim() || null,
      welcome_message: welcomeMessage?.trim() || null,
      is_default: true,
      is_active: true,
      updated_at: new Date().toISOString()
    })
    .select()
    .single()
  
  if (error) throw error
  return data
}
```

### Update an Existing Prompt

```typescript
async function updatePrompt(
  promptId: string,
  prompt: string,
  name?: string,
  welcomeMessage?: string
) {
  const { data, error } = await supabase
    .from('system_prompts')
    .update({
      prompt: prompt.trim(),
      name: name?.trim() || null,
      welcome_message: welcomeMessage?.trim() || null,
      updated_at: new Date().toISOString()
    })
    .eq('id', promptId)
    .select()
    .single()
  
  if (error) throw error
  return data
}
```

### Activate a Prompt (Deactivate All Others)

```typescript
async function activatePrompt(promptId: string) {
  // First, deactivate all prompts
  await supabase
    .from('system_prompts')
    .update({ is_active: false })
    .neq('id', promptId)
  
  // Then activate the selected prompt
  const { data, error } = await supabase
    .from('system_prompts')
    .update({ 
      is_active: true,
      updated_at: new Date().toISOString()
    })
    .eq('id', promptId)
    .select()
    .single()
  
  if (error) throw error
  return data
}
```

### Delete a Prompt

```typescript
async function deletePrompt(promptId: string) {
  const { error } = await supabase
    .from('system_prompts')
    .delete()
    .eq('id', promptId)
  
  if (error) throw error
}
```

### List All Prompts

```typescript
async function listPrompts() {
  const { data, error } = await supabase
    .from('system_prompts')
    .select('*')
    .order('updated_at', { ascending: false })
  
  if (error) throw error
  return data
}
```

### Get Active Prompt

```typescript
async function getActivePrompt() {
  const { data, error } = await supabase
    .from('system_prompts')
    .select('*')
    .eq('is_active', true)
    .eq('is_default', true)
    .order('updated_at', { ascending: false })
    .limit(1)
    .single()
  
  if (error) throw error
  return data
}
```

## Database Schema

The `system_prompts` table structure:

```sql
CREATE TABLE system_prompts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT,
  prompt TEXT NOT NULL,
  is_default BOOLEAN DEFAULT false,
  is_active BOOLEAN DEFAULT true,
  welcome_message TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

## CORS Configuration

### Fix CORS Errors

If you're getting CORS errors like "Redirect is not allowed for a preflight request":

1. **Use HTTPS URL**: Make sure your Supabase URL uses `https://` (not `http://`)
   ```typescript
   // ❌ WRONG - Will cause CORS errors
   const supabaseUrl = "http://mrgcpmfyzknxefluvxmj.supabase.co"
   
   // ✅ CORRECT - Use HTTPS
   const supabaseUrl = "https://mrgcpmfyzknxefluvxmj.supabase.co"
   ```

2. **Configure CORS in Supabase Dashboard**:
   - Go to Supabase Dashboard → Settings → API
   - Under "CORS Configuration", add your frontend origin:
     - For local development: `http://localhost:3000`
     - For production: Your production domain (e.g., `https://voca-frontend-self.vercel.app`)
   - Click "Save"

3. **Alternative: Use Backend API for Reading** (if CORS still fails):
   - The backend `GET /api/system-prompt/list` endpoint still works
   - Use it as a fallback for reading prompts
   - Only use Supabase directly for create/update/delete operations

## RLS Policies Required

Make sure you have RLS policies that allow your frontend to:
- **SELECT**: Read all prompts
- **INSERT**: Create new prompts
- **UPDATE**: Update existing prompts
- **DELETE**: Delete prompts (optional)

Example policy:

```sql
-- Allow all operations for authenticated users
CREATE POLICY "Allow all operations on system_prompts"
ON public.system_prompts
AS PERMISSIVE
FOR ALL
TO authenticated
USING (true)
WITH CHECK (true);

-- Or for public access (if using anon key):
CREATE POLICY "Allow all operations on system_prompts"
ON public.system_prompts
AS PERMISSIVE
FOR ALL
TO public
USING (true)
WITH CHECK (true);
```

## Troubleshooting CORS Issues

### Error: "Redirect is not allowed for a preflight request"

**Cause**: Your Supabase URL is using `http://` instead of `https://`

**Fix**:
```typescript
// In your Supabase client setup
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
  .replace(/^http:\/\//, 'https://') // Convert HTTP to HTTPS
```

### Error: "Access to fetch blocked by CORS policy"

**Cause**: Supabase CORS settings don't allow your origin

**Fix**:
1. Go to Supabase Dashboard → Settings → API
2. Add your origin to CORS configuration:
   - `http://localhost:3000` (for development)
   - Your production domain (for production)
3. Save and retry

### Fallback: Use Backend API for Reading

If CORS issues persist, you can use the backend API for reading prompts:

```typescript
// Fallback to backend API for reading
async function listPrompts() {
  try {
    // Try Supabase first
    const { data, error } = await supabase
      .from('system_prompts')
      .select('*')
      .order('updated_at', { ascending: false })
    
    if (!error) return data
  } catch (corsError) {
    // Fallback to backend API
    const response = await fetch('http://172.105.50.83:8000/api/system-prompt/list')
    const data = await response.json()
    return data
  }
}
```

## Benefits

1. ✅ **No HTTP barriers** - Direct database access from frontend (when CORS is configured)
2. ✅ **Simpler architecture** - Frontend manages its own data
3. ✅ **Better performance** - Direct Supabase connection
4. ✅ **Real-time updates** - Can use Supabase real-time subscriptions
5. ✅ **Backend stays focused** - Only reads prompts for conversations

## Migration Steps

1. Update frontend to use Supabase client directly
2. Remove API calls to deprecated endpoints
3. Test create/update/delete operations
4. Verify backend still reads prompts correctly (it uses `get_prompt()` which reads from Supabase)

