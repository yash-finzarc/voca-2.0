# Frontend Fix: System Prompt Dropdown Not Loading

## Problem
- **405 Method Not Allowed** error when trying to load system prompts
- Dropdown menu not showing system prompt names from database
- Cannot select system prompts from `system_prompts` table

## Solution

I've added a new endpoint to list all system prompts: **`GET /api/system-prompt/list`**

## New Endpoint

### `GET /api/system-prompt/list`

Returns a list of all system prompts (default and organization-specific) with their names.

**Response:**
```json
[
  {
    "id": "uuid-here",
    "key": "default",
    "name": "Default",
    "prompt": "You are Voca...",
    "is_default": true,
    "organization_id": null,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
  },
  {
    "id": "uuid-here",
    "name": "Heal Card Prompt",
    "prompt": "You are Heal Card's AI...",
    "is_default": false,
    "organization_id": "org-uuid",
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
  }
]
```

**Query Parameters:**
- `organization_id` (optional) - Filter by organization
- `include_default` (optional, default: true) - Include default prompts

## Frontend Implementation

### Option 1: Load All Prompts for Dropdown

```typescript
// Load prompts for dropdown
const loadPrompts = async () => {
  try {
    const response = await fetch('/api/system-prompt/list', {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const prompts = await response.json();
    
    // Use prompts array for dropdown
    setPromptOptions(prompts);
    
    // Example: Map to dropdown options
    const dropdownOptions = prompts.map((p: any) => ({
      value: p.id || p.key || 'default',
      label: p.name || 'Unnamed Prompt',
      prompt: p.prompt,
      isDefault: p.is_default,
    }));
    
    return dropdownOptions;
  } catch (error) {
    console.error('Failed to load prompts:', error);
    return [];
  }
};
```

### Option 2: Load Prompts for Specific Organization

```typescript
const loadOrganizationPrompts = async (orgId?: string) => {
  const url = new URL('/api/system-prompt/list', window.location.origin);
  if (orgId) {
    url.searchParams.set('organization_id', orgId);
  }

  const response = await fetch(url.toString(), {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
  });

  const prompts = await response.json();
  return prompts;
};
```

### Option 3: React Hook Example

```typescript
import { useState, useEffect } from 'react';

function SystemPromptDropdown() {
  const [prompts, setPrompts] = useState([]);
  const [selectedPrompt, setSelectedPrompt] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchPrompts = async () => {
      try {
        const response = await fetch('/api/system-prompt/list');
        const data = await response.json();
        setPrompts(data);
        if (data.length > 0) {
          setSelectedPrompt(data[0].id || data[0].key);
        }
      } catch (error) {
        console.error('Error loading prompts:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchPrompts();
  }, []);

  if (loading) return <div>Loading prompts...</div>;

  return (
    <select
      value={selectedPrompt || ''}
      onChange={(e) => setSelectedPrompt(e.target.value)}
    >
      {prompts.map((prompt) => (
        <option key={prompt.id || prompt.key} value={prompt.id || prompt.key}>
          {prompt.name || 'Unnamed Prompt'}
        </option>
      ))}
    </select>
  );
}
```

## Fix the 405 Error

The 405 error suggests your frontend might be using the wrong HTTP method. Make sure you're using:

```typescript
// ✅ CORRECT - GET request
fetch('/api/system-prompt/list', {
  method: 'GET',  // Make sure it's GET, not POST
})

// ❌ WRONG - This will cause 405
fetch('/api/system-prompt/list', {
  method: 'POST',  // Wrong method
})
```

## Complete Example: Load and Select Prompt

```typescript
const [prompts, setPrompts] = useState<Array<{
  id?: string;
  key?: string;
  name?: string;
  prompt: string;
  is_default?: boolean;
}>>([]);

const [selectedPromptId, setSelectedPromptId] = useState<string | null>(null);

// Load prompts on component mount
useEffect(() => {
  const loadPrompts = async () => {
    try {
      const response = await fetch('/api/system-prompt/list');
      if (response.ok) {
        const data = await response.json();
        setPrompts(data);
        // Auto-select first prompt if available
        if (data.length > 0) {
          const firstId = data[0].id || data[0].key || 'default';
          setSelectedPromptId(firstId);
        }
      }
    } catch (error) {
      console.error('Failed to load prompts:', error);
    }
  };

  loadPrompts();
}, []);

// Get selected prompt details
const selectedPrompt = prompts.find(
  (p) => (p.id || p.key) === selectedPromptId
);

// Render dropdown
<select
  value={selectedPromptId || ''}
  onChange={(e) => setSelectedPromptId(e.target.value)}
>
  {prompts.map((prompt) => (
    <option
      key={prompt.id || prompt.key || 'default'}
      value={prompt.id || prompt.key || 'default'}
    >
      {prompt.name || 'Unnamed Prompt'}
    </option>
  ))}
</select>
```

## Test the Endpoint

You can test the endpoint directly:

```bash
# Get all prompts
curl http://localhost:8000/api/system-prompt/list

# Get prompts for specific organization
curl "http://localhost:8000/api/system-prompt/list?organization_id=your-org-id"

# Exclude default prompts
curl "http://localhost:8000/api/system-prompt/list?include_default=false"
```

## Summary

✅ **New endpoint added**: `GET /api/system-prompt/list`  
✅ **Returns all prompts** with names for dropdown  
✅ **Supports filtering** by organization  
✅ **Fixes 405 error** - Use GET method, not POST  

**Action Required**: Update your frontend to use `GET /api/system-prompt/list` instead of trying to GET `/api/system-prompt` (which only returns a single prompt).

