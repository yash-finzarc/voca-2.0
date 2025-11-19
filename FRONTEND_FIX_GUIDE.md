# Frontend Fix Guide - Organization ID Error

## The Problem

Your frontend is showing: **"Organization ID is required. Please configure NEXT_PUBLIC_DEFAULT_ORGANIZATION_ID..."**

This error is coming from **your frontend validation**, not the backend. The backend now fully supports creating prompts **without** organization_id.

## Solution Options

### Option 1: Remove Organization ID Requirement (Easiest - Recommended)

**Update your frontend to make organization_id optional:**

```typescript
// ❌ REMOVE THIS VALIDATION:
if (!organizationId) {
  throw new Error('Organization ID is required...');
}

// ✅ INSTEAD, just send the request without organization_id:
const createPrompt = async (prompt: string, name?: string) => {
  const response = await fetch('/api/system-prompt', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      prompt: prompt,
      name: name || 'Custom Prompt',
      // Don't include organization_id - backend will save as default
    }),
  });

  const data = await response.json();
  return data;
};
```

**This will save the prompt as the "default prompt"** which works perfectly for single-tenant setups.

### Option 2: Create Organization First, Then Prompt

If you want to use organizations, follow these steps:

#### Step 1: Create an Organization

```typescript
// Create organization first
const createOrganization = async (name: string) => {
  const response = await fetch('/api/organizations', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      name: name,  // e.g., "Heal Card"
      domain: 'healcard.com',  // optional
      api_key: null,  // optional
    }),
  });

  const org = await response.json();
  return org.id;  // Save this organization_id
};
```

#### Step 2: Use Organization ID When Creating Prompt

```typescript
// Then create prompt with organization_id
const createPrompt = async (prompt: string, name: string, orgId: string) => {
  const response = await fetch('/api/system-prompt', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      prompt: prompt,
      name: name,
      organization_id: orgId,  // Use the org ID from step 1
    }),
  });

  return response.json();
};
```

### Option 3: Auto-Create Organization if Missing

```typescript
const createPromptWithAutoOrg = async (prompt: string, name: string, orgName?: string) => {
  let orgId = null;

  // If organization name provided, create or get organization
  if (orgName) {
    // Try to find existing organization
    const orgsResponse = await fetch('/api/organizations');
    const orgs = await orgsResponse.json();
    const existingOrg = orgs.find((o: any) => o.name === orgName);

    if (existingOrg) {
      orgId = existingOrg.id;
    } else {
      // Create new organization
      const newOrgResponse = await fetch('/api/organizations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: orgName }),
      });
      const newOrg = await newOrgResponse.json();
      orgId = newOrg.id;
    }
  }

  // Create prompt (with or without org_id)
  const response = await fetch('/api/system-prompt', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      prompt: prompt,
      name: name,
      ...(orgId && { organization_id: orgId }),
    }),
  });

  return response.json();
};
```

## Quick Test

Test the backend directly to verify it works:

```bash
# Test 1: Create prompt WITHOUT organization_id (saves as default)
curl -X POST http://localhost:8000/api/system-prompt \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "You are Heal Card assistant...",
    "name": "Heal Card Prompt"
  }'

# Test 2: Create organization first
curl -X POST http://localhost:8000/api/organizations \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Heal Card",
    "domain": "healcard.com"
  }'

# Test 3: Create prompt WITH organization_id (use ID from Test 2)
curl -X POST http://localhost:8000/api/system-prompt \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "You are Heal Card assistant...",
    "name": "Heal Card Prompt",
    "organization_id": "YOUR_ORG_ID_FROM_TEST_2"
  }'
```

## New Backend Endpoints Available

1. **POST /api/organizations** - Create organization
2. **GET /api/organizations** - List all organizations
3. **GET /api/organizations/{id}** - Get specific organization

## Summary

✅ **Backend is ready** - Accepts prompts with or without organization_id  
✅ **Organization endpoints** - Can create/list organizations via API  
✅ **Better error messages** - Clear feedback when organization doesn't exist  
✅ **Default prompt support** - Works without multi-tenant setup  

**Action Required**: Update your frontend to **remove the organization_id requirement** from validation. The backend will automatically save it as the default prompt if no organization_id is provided.

