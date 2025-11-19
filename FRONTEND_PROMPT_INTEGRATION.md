# Frontend System Prompt Integration Guide

## Backend Changes Made

The backend now **explicitly supports creating prompts without organization_id**. When `organization_id` is `None` or not provided, the prompt will be saved as the **default prompt** in the `system_prompts` table.

## Frontend Implementation Options

### Option 1: Allow Creating Default Prompt (Recommended for Initial Setup)

**Remove the organization_id requirement** from your frontend validation. The backend will handle it gracefully:

```typescript
// Example: React/Next.js
const createPrompt = async (prompt: string, name?: string) => {
  try {
    const response = await fetch('/api/system-prompt', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        prompt: prompt,
        name: name || 'Custom Prompt',
        // organization_id is OPTIONAL - omit it to save as default
        // organization_id: organizationId,  // Only include if you have one
      }),
    });

    const data = await response.json();
    if (data.status === 'success') {
      console.log('Prompt saved:', data.message);
      // Success message will indicate if saved as default or org-specific
    }
  } catch (error) {
    console.error('Failed to create prompt:', error);
  }
};
```

### Option 2: Use Header for Organization ID

If you want to pass organization_id via header:

```typescript
const createPrompt = async (prompt: string, name?: string, orgId?: string) => {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  
  // Add organization ID as header if provided
  if (orgId) {
    headers['X-Organization-Id'] = orgId;
  }

  const response = await fetch('/api/system-prompt', {
    method: 'POST',
    headers,
    body: JSON.stringify({
      prompt: prompt,
      name: name || 'Custom Prompt',
    }),
  });
  
  return response.json();
};
```

### Option 3: Query Parameter

You can also pass organization_id as a query parameter:

```typescript
const createPrompt = async (prompt: string, name?: string, orgId?: string) => {
  const url = new URL('/api/system-prompt', window.location.origin);
  if (orgId) {
    url.searchParams.set('organization_id', orgId);
  }

  const response = await fetch(url.toString(), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      prompt: prompt,
      name: name || 'Custom Prompt',
    }),
  });
  
  return response.json();
};
```

## Frontend Validation Fix

**Remove or make organization_id optional** in your frontend validation:

```typescript
// ❌ OLD - Too strict
if (!organizationId) {
  throw new Error('Organization ID is required');
}

// ✅ NEW - Allow None
// Just proceed - backend will save as default prompt
// Optionally show a message:
if (!organizationId) {
  console.log('No organization ID provided - will save as default prompt');
}
```

## Response Messages

The backend now returns clear messages:

- **With org_id**: `"System prompt updated successfully for organization {org_id}"`
- **Without org_id**: `"System prompt updated successfully as default prompt"`

## Testing

1. **Test without organization_id**:
   ```bash
   curl -X POST http://localhost:8000/api/system-prompt \
     -H "Content-Type: application/json" \
     -d '{
       "prompt": "Your prompt text here",
       "name": "Heal Card Prompt"
     }'
   ```

2. **Test with organization_id**:
   ```bash
   curl -X POST http://localhost:8000/api/system-prompt \
     -H "Content-Type: application/json" \
     -H "X-Organization-Id: your-org-id" \
     -d '{
       "prompt": "Your prompt text here",
       "name": "Heal Card Prompt"
     }'
   ```

## Environment Variables (Optional)

If you want to set a default organization for your frontend:

```env
# .env.local (Frontend)
NEXT_PUBLIC_DEFAULT_ORGANIZATION_ID=your-org-id-here
```

Then in your frontend code:
```typescript
const defaultOrgId = process.env.NEXT_PUBLIC_DEFAULT_ORGANIZATION_ID;
// Use defaultOrgId if user hasn't selected an organization
```

## Summary

✅ **Backend is ready** - It accepts prompts with or without organization_id  
✅ **Default prompt support** - Works without multi-tenant setup  
✅ **Better error messages** - Clear feedback about what was saved  
✅ **Multiple ways to pass org_id** - Body, header, or query parameter  

**Action Required**: Update your frontend to **remove the organization_id requirement** and allow creating prompts without it. The backend will automatically save it as the default prompt.

