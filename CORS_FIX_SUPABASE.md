# Quick Fix for Supabase CORS Error

## The Problem

You're seeing this error:
```
Access to fetch at 'http://mrgcpmfyzknxefluvxmj.supabase.co/rest/v1/...' 
from origin 'http://localhost:3000' has been blocked by CORS policy: 
Response to preflight request doesn't pass access control check: 
Redirect is not allowed for a preflight request.
```

## Root Cause

Your Supabase URL is using **HTTP** instead of **HTTPS**. Supabase automatically redirects HTTP to HTTPS, but browsers block redirects during CORS preflight requests.

## Quick Fix

### Option 1: Fix the URL in Your Code (Recommended)

Update your Supabase client initialization to force HTTPS:

```typescript
// In your Supabase client file (e.g., lib/supabase.ts or utils/supabase.ts)
import { createClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
  .replace(/^http:\/\//, 'https://') // Force HTTPS

const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

export const supabase = createClient(supabaseUrl, supabaseAnonKey)
```

### Option 2: Fix the Environment Variable

Update your `.env.local` or `.env` file:

```bash
# ❌ WRONG
NEXT_PUBLIC_SUPABASE_URL=http://mrgcpmfyzknxefluvxmj.supabase.co

# ✅ CORRECT
NEXT_PUBLIC_SUPABASE_URL=https://mrgcpmfyzknxefluvxmj.supabase.co
```

### Option 3: Configure CORS in Supabase Dashboard

1. Go to [Supabase Dashboard](https://supabase.com/dashboard)
2. Select your project
3. Go to **Settings** → **API**
4. Scroll to **CORS Configuration**
5. Add your frontend origin:
   - `http://localhost:3000` (for development)
   - Your production domain (e.g., `https://voca-frontend-self.vercel.app`)
6. Click **Save**

### Option 4: Use Backend API as Fallback

If CORS issues persist, use the backend API for reading (it still works):

```typescript
// Use backend API for reading prompts
async function listPrompts() {
  const response = await fetch('http://172.105.50.83:8000/api/system-prompt/list')
  const data = await response.json()
  return data
}

// Use Supabase directly for create/update/delete
async function createPrompt(prompt: string) {
  const { data, error } = await supabase
    .from('system_prompts')
    .insert({ prompt, is_default: true, is_active: true })
    .select()
    .single()
  
  if (error) throw error
  return data
}
```

## Verify the Fix

After applying the fix:

1. **Check the URL**: Open browser DevTools → Network tab
2. **Look for requests to Supabase**: They should use `https://` not `http://`
3. **Check CORS headers**: Response should include `Access-Control-Allow-Origin` header

## Still Having Issues?

If you're still getting CORS errors after fixing the URL:

1. **Clear browser cache** and hard refresh (Ctrl+Shift+R or Cmd+Shift+R)
2. **Check Supabase CORS settings** in the dashboard
3. **Verify RLS policies** allow your operations
4. **Use backend API** as a temporary workaround for reading operations

