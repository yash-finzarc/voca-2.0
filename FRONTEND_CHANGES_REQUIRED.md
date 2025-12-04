# Frontend Changes Required - Backend UUID Generation

## Summary

The backend now **automatically generates UUIDs** for new system prompts. The frontend should **NOT** generate UUIDs anymore. Instead, the frontend should:

1. **Create prompts** without providing a UUID (backend generates it)
2. **Receive the UUID** from the backend response
3. **Use that UUID** for updates and activations

---

## Backend Changes Made

✅ Backend now has a new `create_prompt()` function that:
- Generates UUID automatically using `uuid.uuid4()`
- Returns `(success: bool, prompt_id: Optional[str])`
- The UUID is included in the API response as `prompt_id`

✅ API endpoint `/api/system-prompt` (POST/PUT/PATCH):
- If `id` is **NOT provided**: Creates new prompt with auto-generated UUID
- If `id` **IS provided**: Updates existing prompt (or creates with that specific UUID)
- Response now includes `prompt_id` field with the UUID

---

## Frontend Changes Required

### 1. **Remove UUID Generation from Frontend**

**Remove this code:**
```typescript
// ❌ REMOVE THIS
const newPromptId = crypto.randomUUID();
```

**From files like:**
- `app/system-prompt/page.tsx` (or wherever you create prompts)
- Any service files that generate UUIDs

---

### 2. **Update Create Prompt Function**

**Before (with frontend UUID generation):**
```typescript
const handleCreatePrompt = async () => {
  const newPromptId = crypto.randomUUID(); // ❌ Remove this
  
  const response = await systemPromptService.create({
    id: newPromptId, // ❌ Remove this
    prompt: promptText,
    name: promptName,
  });
  
  // Use newPromptId for state management
  setSelectedPromptId(newPromptId);
};
```

**After (backend generates UUID):**
```typescript
const handleCreatePrompt = async () => {
  const response = await systemPromptService.create({
    // ✅ Don't send 'id' field - backend will generate it
    prompt: promptText,
    name: promptName,
  });
  
  // ✅ Get UUID from response
  if (response.prompt_id) {
    setSelectedPromptId(response.prompt_id);
    // Reload prompts to show the new one
    await loadPrompts();
  }
};
```

---

### 3. **Update API Service Types**

**Update the response type to include `prompt_id`:**

```typescript
// In your API service file (e.g., api-services.ts or types file)

interface StatusResponse {
  status: string;
  message: string;
  prompt_id?: string; // ✅ Add this field
}

// Update your create function:
async create(data: {
  // id?: string; // ❌ Remove this - don't send id
  prompt: string;
  name?: string;
  welcome_message?: string;
}): Promise<StatusResponse> {
  const response = await apiClient.post('/api/system-prompt', data);
  return response.data; // This will now include prompt_id
}
```

---

### 4. **Update State Management**

**When creating a new prompt:**
- **Don't** generate UUID in frontend
- **Do** wait for backend response
- **Do** use `response.prompt_id` to update your state
- **Do** reload the prompts list after creation

**Example:**
```typescript
const handleCreatePrompt = async () => {
  try {
    setLoading(true);
    
    const response = await systemPromptService.create({
      prompt: promptText,
      name: promptName,
      welcome_message: welcomeMessage,
    });
    
    if (response.status === 'success' && response.prompt_id) {
      // ✅ Use the UUID from backend
      setSelectedPromptId(response.prompt_id);
      
      // ✅ Reload prompts to show the new one
      await loadPrompts();
      
      // ✅ Show success message
      toast.success('Prompt created successfully');
    }
  } catch (error) {
    console.error('[Create Prompt] Error:', error);
    toast.error('Failed to create prompt');
  } finally {
    setLoading(false);
  }
};
```

---

### 5. **Update Update Function**

**The update function should still work the same way** - you provide the UUID of the existing prompt:

```typescript
const handleSave = async () => {
  if (!selectedPromptId) {
    // This means we're creating a new prompt
    await handleCreatePrompt();
    return;
  }
  
  // Update existing prompt - still use the UUID
  await systemPromptService.update(selectedPromptId, {
    prompt: promptText,
    name: promptName,
    welcome_message: welcomeMessage,
  });
};
```

---

### 6. **Update Activate Function**

**The activate function should still work the same way** - you provide the UUID:

```typescript
const handlePromptActivation = async (promptId: string) => {
  await systemPromptService.activate(promptId);
  await loadPrompts(); // Reload to refresh is_active status
};
```

---

## Summary of Changes

| Action | Before | After |
|--------|--------|-------|
| **Create Prompt** | Frontend generates UUID with `crypto.randomUUID()` | Backend generates UUID, frontend receives it in response |
| **Request Body** | `{ id: "...", prompt: "...", name: "..." }` | `{ prompt: "...", name: "..." }` (no `id` field) |
| **Response** | `{ status: "success", message: "..." }` | `{ status: "success", message: "...", prompt_id: "..." }` |
| **Update Prompt** | Same (provide UUID) | Same (provide UUID) |
| **Activate Prompt** | Same (provide UUID) | Same (provide UUID) |

---

## Testing Checklist

After making these changes, test:

1. ✅ **Create a new prompt** - Should work without frontend UUID generation
2. ✅ **Check response** - Should include `prompt_id` field
3. ✅ **Update prompt** - Should work with the UUID from response
4. ✅ **Activate prompt** - Should work with the UUID from response
5. ✅ **List prompts** - Should show all prompts with their UUIDs
6. ✅ **Select prompt** - Should work with UUIDs from the list

---

## Files to Update in Frontend

Based on your previous messages, you likely need to update:

1. **`app/system-prompt/page.tsx`**
   - Remove `crypto.randomUUID()` calls
   - Update `handleCreatePrompt()` to not send `id`
   - Update to use `response.prompt_id` from backend

2. **`lib/api-services.ts`** (or similar)
   - Update `create()` method to not require/send `id`
   - Update response type to include `prompt_id`

3. **Any TypeScript interfaces/types**
   - Add `prompt_id?: string` to response types
   - Remove `id` requirement from create request types

---

## Example Complete Flow

```typescript
// 1. User clicks "Create Prompt"
const handleCreatePrompt = async () => {
  // ✅ No UUID generation here
  const response = await systemPromptService.create({
    prompt: "You are a helpful assistant...",
    name: "My New Prompt",
  });
  
  // ✅ Backend returns: { status: "success", prompt_id: "abc-123-..." }
  if (response.prompt_id) {
    setSelectedPromptId(response.prompt_id);
    await loadPrompts(); // Shows new prompt in list
  }
};

// 2. User edits and saves
const handleSave = async () => {
  if (selectedPromptId) {
    // ✅ Use the UUID from backend
    await systemPromptService.update(selectedPromptId, {
      prompt: updatedPrompt,
      name: updatedName,
    });
  }
};

// 3. User activates a prompt
const handleActivate = async (promptId: string) => {
  // ✅ Use UUID from the prompt list
  await systemPromptService.activate(promptId);
  await loadPrompts(); // Refresh to show is_active status
};
```

---

## Benefits of This Approach

1. ✅ **No UUID mismatch** - Backend is the source of truth
2. ✅ **Simpler frontend** - No need to generate UUIDs
3. ✅ **Better error handling** - Backend can validate UUID format
4. ✅ **Consistent IDs** - All UUIDs come from the same source
5. ✅ **Easier debugging** - UUIDs are generated in one place

---

## Need Help?

If you encounter any issues:
1. Check browser console for errors
2. Check network tab to see the request/response
3. Verify the backend is returning `prompt_id` in the response
4. Make sure you're not sending `id` field when creating new prompts

