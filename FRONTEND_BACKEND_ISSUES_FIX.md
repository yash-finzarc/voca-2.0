# Frontend and Backend Issues - Fix Guide

## Issue 1: Backend Returns Existing UUID Instead of Creating New Prompt

**Problem:**
- Frontend sends create request without UUID
- Backend returns `prompt_id: 'e77e33be-fb81-4361-82fd-76c1069b14ea'` (existing prompt's UUID)
- No new prompt is actually created in database

**Root Cause:**
The backend `create_prompt()` function might be:
1. Failing silently due to RLS policies
2. Returning the wrong UUID from response
3. Not actually inserting (Supabase returning existing row)

**Backend Fix Needed:**

Check the backend logs for:
- `"Attempting to insert prompt into Supabase..."`
- `"Supabase response: ..."`
- `"Verified prompt ... exists in database"`

If you see errors about RLS or permissions, add the RLS policy:

```sql
CREATE POLICY "Allow all operations on system_prompts"
ON public.system_prompts
AS PERMISSIVE
FOR ALL
TO public
USING (true)
WITH CHECK (true);
```

**Also verify:** The Supabase insert should return a NEW UUID, not an existing one. Check if the insert is actually happening.

---

## Issue 2: Frontend Infinite Re-render Loop

**Problem:**
- `renderPromptOptions` is being called repeatedly
- Console is spammed with the same log messages
- Component re-renders in an infinite loop

**Root Cause:**
This is typically caused by:
1. State updates triggering re-renders that update state again
2. useEffect dependencies causing infinite loops
3. Event handlers being recreated on every render

**Frontend Fixes Needed:**

### Fix 1: Check useEffect Dependencies

Look for `useEffect` hooks that call `loadPrompts()` or update state:

```typescript
// ❌ BAD - This will cause infinite loop
useEffect(() => {
  loadPrompts();
  setSomeState(newValue); // This triggers re-render, which triggers useEffect again
}, [prompts, someState]); // If these are in dependencies

// ✅ GOOD - Only run once on mount
useEffect(() => {
  loadPrompts();
}, []); // Empty dependency array

// ✅ GOOD - Only run when specific value changes
useEffect(() => {
  loadPrompts();
}, [selectedPromptId]); // Only when selectedPromptId changes
```

### Fix 2: Memoize Callbacks

Wrap callbacks in `useCallback` to prevent re-creation:

```typescript
// ❌ BAD - Function recreated on every render
const handlePromptChange = (id: string) => {
  setSelectedPromptId(id);
  loadPrompts(); // This might trigger re-render
};

// ✅ GOOD - Memoized callback
const handlePromptChange = useCallback((id: string) => {
  setSelectedPromptId(id);
  // Don't call loadPrompts() here if it causes re-render
}, []); // Empty deps if it doesn't depend on other state
```

### Fix 3: Check renderPromptOptions Function

The `renderPromptOptions` function might be:
- Called during render and updating state
- Triggering re-renders that call it again

**Fix:**
```typescript
// Make sure renderPromptOptions doesn't update state during render
const renderPromptOptions = useMemo(() => {
  // Don't call setState here!
  return prompts.map(prompt => (
    <option key={prompt.id} value={prompt.id}>
      {prompt.name}
    </option>
  ));
}, [prompts]); // Only recalculate when prompts change
```

### Fix 4: Remove Console Logs from Render

Console logs in render functions can cause performance issues:

```typescript
// ❌ BAD - Logs on every render
const renderPromptOptions = () => {
  console.log('[renderPromptOptions] Current prompts state:', prompts);
  // ... rest of function
};

// ✅ GOOD - Only log when needed (development only)
const renderPromptOptions = () => {
  if (process.env.NODE_ENV === 'development') {
    console.log('[renderPromptOptions] Rendering', prompts.length, 'prompts');
  }
  // ... rest of function
};
```

### Fix 5: Check State Updates After loadPrompts

Make sure `loadPrompts()` doesn't trigger state updates that cause re-renders:

```typescript
// ❌ BAD - This might cause loop
const loadPrompts = async () => {
  const response = await systemPromptService.list();
  setPrompts(response);
  // If this triggers a re-render that calls loadPrompts again, it's a loop
};

// ✅ GOOD - Add guard to prevent multiple calls
const [loading, setLoading] = useState(false);

const loadPrompts = async () => {
  if (loading) return; // Prevent concurrent calls
  setLoading(true);
  try {
    const response = await systemPromptService.list();
    setPrompts(response);
  } finally {
    setLoading(false);
  }
};
```

---

## Quick Debugging Steps

1. **Check Backend Logs:**
   - Look for the insert attempt
   - Check if a new UUID is generated
   - Verify the prompt is actually inserted

2. **Check Frontend Console:**
   - Look for the first call to `renderPromptOptions`
   - Find what triggers the re-render
   - Check React DevTools for component update reasons

3. **Add Guards:**
   ```typescript
   // Add this to prevent infinite loops
   const renderCount = useRef(0);
   useEffect(() => {
     renderCount.current++;
     if (renderCount.current > 10) {
       console.error('Too many re-renders! Check dependencies');
     }
   });
   ```

4. **Temporarily Remove Logs:**
   - Comment out all `console.log` in `renderPromptOptions`
   - See if the loop stops (it might be the logging causing issues)

---

## Expected Behavior

**After fixes:**
1. Creating a prompt should return a NEW UUID
2. The prompt list should show the new prompt
3. `renderPromptOptions` should only be called when prompts actually change
4. No infinite loops in console

