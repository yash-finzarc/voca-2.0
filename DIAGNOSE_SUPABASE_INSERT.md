# Diagnosing Supabase Insert Issue

## Problem
System prompt shows "successfully added" but doesn't appear in Supabase database.

## Most Likely Cause: RLS (Row Level Security) Policies

If RLS is enabled on `system_prompts` table but no policies allow INSERT, the insert will fail silently or return success but not actually save the data.

## Quick Fix

Run this SQL in Supabase SQL Editor:

```sql
-- Check if RLS is enabled
SELECT tablename, rowsecurity 
FROM pg_tables 
WHERE schemaname = 'public' AND tablename = 'system_prompts';

-- If RLS is enabled, create a policy to allow all operations
ALTER TABLE public.system_prompts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all operations on system_prompts"
ON public.system_prompts
AS PERMISSIVE
FOR ALL
TO public
USING (true)
WITH CHECK (true);
```

## Check Your Supabase Key

The backend uses `SUPABASE_KEY` environment variable. Check if you're using:

1. **Service Role Key** (bypasses RLS) - Should start with `eyJ...` and be very long
2. **Anon Key** (respects RLS) - Also starts with `eyJ...` but shorter

**If using Anon Key**, you MUST have RLS policies that allow INSERT.

**If using Service Role Key**, RLS policies don't matter (but it's still good to have them).

## Test the Insert Manually

Run this in Supabase SQL Editor to test if inserts work:

```sql
-- Test insert
INSERT INTO system_prompts (prompt, is_default, is_active, name)
VALUES ('Test prompt', true, true, 'Test')
RETURNING id, prompt, name, is_default, is_active;

-- Check if it was inserted
SELECT * FROM system_prompts ORDER BY created_at DESC LIMIT 5;
```

If this works but the API doesn't, it's an RLS policy issue.

## Check Backend Logs

The improved error handling will now log:
- Full Supabase response
- Response status codes
- Any errors from Supabase
- Verification attempts

Look for these log messages:
- `"Attempting to insert prompt into Supabase..."`
- `"Supabase response: ..."`
- `"Verified prompt ... exists in database"` or `"Prompt ... was not found after creation"`

## Next Steps

1. **Add the RLS policy** (SQL above)
2. **Check backend logs** for detailed error messages
3. **Verify Supabase key** is service role key if you want to bypass RLS
4. **Test manual insert** in SQL Editor

