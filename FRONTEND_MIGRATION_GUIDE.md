# Frontend Migration Guide: Switch to Supabase Direct

## Problem

The backend endpoint `/api/system-prompt` now returns `prompt_id=None` because it's deprecated. The frontend needs to use Supabase directly.

## Solution: Update Frontend to Use Supabase

### Step 1: Update Supabase Client Setup

Make sure your Supabase client uses HTTPS:

```typescript
// lib/supabase.ts or utils/supabase.ts
import { createClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
  .replace(/^http:\/\//, 'https://') // Force HTTPS to fix CORS

const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

export const supabase = createClient(supabaseUrl, supabaseAnonKey)
```

### Step 2: Update `handleCreatePrompt` Function

Replace the backend API call with a direct Supabase call:

```typescript
// Before (using backend API):
const handleCreatePrompt = async () => {
  const response = await apiClient.post('/api/system-prompt', {
    prompt: promptText,
    name: promptName,
    welcome_message: welcomeMessage
  })
  
  if (!response.prompt_id) {
    throw new Error('Backend did not return id in response')
  }
  
  const newPromptId = response.prompt_id
  // ... rest of the code
}

// After (using Supabase directly):
const handleCreatePrompt = async () => {
  try {
    // Generate UUID in frontend (or let Supabase generate it)
    const newPromptId = crypto.randomUUID()
    
    const { data, error } = await supabase
      .from('system_prompts')
      .insert({
        id: newPromptId, // Optional: you can omit this and let Supabase generate it
        prompt: promptText.trim(),
        name: promptName?.trim() || null,
        welcome_message: welcomeMessage?.trim() || null,
        is_default: true,
        is_active: true,
        updated_at: new Date().toISOString()
      })
      .select()
      .single()
    
    if (error) {
      throw new Error(`Failed to create prompt: ${error.message}`)
    }
    
    // Use data.id (or newPromptId if you generated it)
    const createdPromptId = data.id || newPromptId
    
    // Update your state
    setSelectedPromptId(createdPromptId)
    setPrompts([...prompts, data])
    
    // Show success message
    console.log('Prompt created successfully:', createdPromptId)
    
  } catch (error) {
    console.error('Error creating prompt:', error)
    throw error
  }
}
```

### Step 3: Update `handleSave` Function (Update Existing Prompt)

```typescript
// Before (using backend API):
const handleSave = async () => {
  const response = await apiClient.put('/api/system-prompt', {
    id: selectedPromptId,
    prompt: promptText,
    name: promptName,
    welcome_message: welcomeMessage
  })
  // ... rest of the code
}

// After (using Supabase directly):
const handleSave = async () => {
  if (!selectedPromptId) {
    throw new Error('No prompt selected')
  }
  
  try {
    const { data, error } = await supabase
      .from('system_prompts')
      .update({
        prompt: promptText.trim(),
        name: promptName?.trim() || null,
        welcome_message: welcomeMessage?.trim() || null,
        updated_at: new Date().toISOString()
      })
      .eq('id', selectedPromptId)
      .select()
      .single()
    
    if (error) {
      throw new Error(`Failed to update prompt: ${error.message}`)
    }
    
    // Update your state
    setPrompts(prompts.map(p => p.id === selectedPromptId ? data : p))
    
    console.log('Prompt updated successfully')
    
  } catch (error) {
    console.error('Error updating prompt:', error)
    throw error
  }
}
```

### Step 4: Update `handlePromptActivation` Function

```typescript
// Before (using backend API):
const handlePromptActivation = async (promptId: string) => {
  await apiClient.post('/api/system-prompt/activate', {
    prompt_id: promptId
  })
  // ... rest of the code
}

// After (using Supabase directly):
const handlePromptActivation = async (promptId: string) => {
  try {
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
    
    if (error) {
      throw new Error(`Failed to activate prompt: ${error.message}`)
    }
    
    // Update your state
    setPrompts(prompts.map(p => ({
      ...p,
      is_active: p.id === promptId
    })))
    
    console.log('Prompt activated successfully')
    
  } catch (error) {
    console.error('Error activating prompt:', error)
    throw error
  }
}
```

### Step 5: Update `loadPrompts` Function

```typescript
// Before (using backend API):
const loadPrompts = async () => {
  const data = await apiClient.get('/api/system-prompt/list')
  setPrompts(data)
}

// After (using Supabase directly):
const loadPrompts = async () => {
  try {
    const { data, error } = await supabase
      .from('system_prompts')
      .select('*')
      .order('updated_at', { ascending: false })
    
    if (error) {
      throw new Error(`Failed to load prompts: ${error.message}`)
    }
    
    setPrompts(data || [])
    
  } catch (error) {
    console.error('Error loading prompts:', error)
    // Fallback to backend API if Supabase fails
    try {
      const response = await fetch('http://172.105.50.83:8000/api/system-prompt/list')
      const backendData = await response.json()
      setPrompts(backendData)
    } catch (fallbackError) {
      console.error('Both Supabase and backend API failed:', fallbackError)
    }
  }
}
```

## Quick Fix (Temporary)

If you need a quick fix while migrating, you can temporarily restore the backend endpoint functionality. But this is **not recommended** as it goes against the new architecture.

## Environment Variables

Make sure you have these in your `.env.local`:

```bash
NEXT_PUBLIC_SUPABASE_URL=https://mrgcpmfyzknxefluvxmj.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_anon_key_here
```

## Testing

After making these changes:

1. **Test creating a prompt** - Should create in Supabase and return an ID
2. **Test updating a prompt** - Should update in Supabase
3. **Test activating a prompt** - Should activate one and deactivate others
4. **Test loading prompts** - Should load all prompts from Supabase

## Troubleshooting

- **CORS errors**: Make sure Supabase URL uses `https://`
- **RLS policy errors**: Check Supabase RLS policies allow your operations
- **Missing ID**: Make sure you're using `data.id` from the Supabase response

