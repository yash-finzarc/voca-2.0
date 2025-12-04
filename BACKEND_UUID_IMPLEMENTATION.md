# Backend UUID Implementation for System Prompts

## Overview

This document explains the backend changes made to align with the frontend's UUID-based system prompt management. The backend now uses UUIDs (stored in the existing `id` column) to identify and manage prompts, matching the frontend's approach where `crypto.randomUUID()` generates unique identifiers.

## Key Changes

### 1. **Updated SystemPromptRequest Model** (`src/voca/api.py`)

**Change**: Added optional `id` field to accept UUID from frontend.

```python
class SystemPromptRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    name: Optional[str] = None
    welcome_message: Optional[str] = None
    organization_id: Optional[str] = None
    id: Optional[str] = None  # NEW: UUID from frontend
```

**Why**: Frontend generates UUID using `crypto.randomUUID()` and passes it in the request. This allows the backend to identify which prompt to create/update.

---

### 2. **New Function: `create_prompt_with_id()`** (`src/voca/system_prompt.py`)

**Purpose**: Creates a new system prompt using the UUID provided by the frontend.

**How it works**:
1. Frontend generates UUID: `const promptId = crypto.randomUUID()`
2. Frontend calls `create()` with UUID
3. Backend receives UUID in `request.id`
4. Backend deactivates all previous default prompts (`is_active = false`)
5. Backend creates new prompt with:
   - `id` = UUID from frontend (stored in existing `id` column)
   - `key` = auto-generated unique key (e.g., `"default_abc123_1234567890"`)
   - `is_active = true` (new prompt is automatically active)
   - `is_default = true`

**Key Points**:
- Uses existing `id` column (UUID type) to store frontend-generated UUID
- Preserves all previous prompts (they're deactivated, not deleted)
- New prompt is automatically active
- Clears cache to force refresh

**Alignment with Frontend**:
- Matches frontend's `create()` function behavior
- Frontend generates UUID → Backend uses it as `id`

---

### 3. **New Function: `update_prompt_by_id()`** (`src/voca/system_prompt.py`)

**Purpose**: Updates an existing prompt identified by UUID.

**How it works**:
1. Frontend calls `update(promptId, newData)`
2. Backend receives UUID in `request.id`
3. Backend finds prompt where `id = promptId`
4. Backend updates only that prompt's fields:
   - `prompt` text
   - `name` (if provided)
   - `welcome_message` (if provided)
   - `updated_at` timestamp

**Key Points**:
- Updates only the specified prompt (by UUID)
- Does not affect other prompts
- Clears cache to force refresh

**Alignment with Frontend**:
- Matches frontend's `update()` function behavior
- Frontend passes UUID → Backend updates that specific prompt

---

### 4. **New Function: `activate_prompt_by_id()`** (`src/voca/system_prompt.py`)

**Purpose**: Activates a prompt by UUID and deactivates all others.

**How it works**:
1. Frontend user selects a prompt from dropdown
2. Frontend automatically calls `activate(promptId)`
3. Backend receives UUID
4. Backend:
   - Verifies prompt exists and is a default prompt
   - Deactivates ALL other default prompts (`is_active = false`)
   - Activates the selected prompt (`is_active = true`)

**Key Points**:
- Only one prompt can be active at a time
- Automatically deactivates others (matches frontend behavior)
- Clears cache to force refresh

**Alignment with Frontend**:
- Matches frontend's `handlePromptActivation()` behavior
- When user selects prompt → Frontend calls `activate()` → Backend activates that prompt

---

### 5. **Updated API Endpoint: `POST/PUT/PATCH /api/system-prompt`** (`src/voca/api.py`)

**Change**: Now supports both UUID-based (new) and organization_id-based (legacy) operations.

**How it works**:

**If `request.id` (UUID) is provided** (new frontend approach):
1. Check if prompt with that UUID exists
2. If exists → call `update_prompt_by_id()`
3. If doesn't exist → call `create_prompt_with_id()`

**If `request.id` is NOT provided** (legacy approach):
- Falls back to old behavior using `organization_id`
- Maintains backward compatibility

**Key Points**:
- Prioritizes UUID-based operations (new frontend)
- Falls back to legacy behavior for compatibility
- Handles both create and update in one endpoint

**Alignment with Frontend**:
- Frontend always provides `id` (UUID) → Backend uses UUID operations
- Frontend's `create()` and `update()` both use this endpoint

---

### 6. **New API Endpoint: `POST /api/system-prompt/activate`** (`src/voca/api.py`)

**Purpose**: Dedicated endpoint for activating prompts by UUID.

**How it works**:
1. Frontend calls: `POST /api/system-prompt/activate?prompt_id=<UUID>`
2. Backend receives UUID
3. Backend calls `activate_prompt_by_id(UUID)`
4. Returns success/error response

**Key Points**:
- Separate endpoint for activation (cleaner API design)
- Takes UUID as query parameter
- Aligns with frontend's `activate()` function

**Alignment with Frontend**:
- Matches frontend's `activate()` API service call
- Frontend calls this when user selects a prompt

---

## Database Schema (No Changes Required)

The existing `system_prompts` table already has all needed columns:

- `id` (UUID) - **Used to store frontend-generated UUID**
- `key` (TEXT) - Internal key for organization (auto-generated)
- `name` (TEXT) - Prompt name
- `prompt` (TEXT) - Prompt text
- `is_default` (BOOLEAN) - Whether it's a default prompt
- `is_active` (BOOLEAN) - Whether it's currently active
- `welcome_message` (TEXT) - Custom welcome message
- `created_at` (TIMESTAMP) - Creation timestamp
- `updated_at` (TIMESTAMP) - Last update timestamp

**Key Point**: We use the existing `id` column to store the frontend-generated UUID. No schema changes needed!

---

## Flow Diagrams

### Creating a New Prompt

```
Frontend:
1. const promptId = crypto.randomUUID()
2. api.create(promptId, { prompt, name, welcome_message })

Backend:
1. Receives request.id = promptId
2. Checks if prompt with that id exists → NO
3. Calls create_prompt_with_id(promptId, ...)
4. Deactivates all previous prompts
5. Inserts new prompt with id = promptId, is_active = true
6. Returns success

Result: New prompt created with UUID, all others deactivated
```

### Updating an Existing Prompt

```
Frontend:
1. api.update(promptId, { prompt, name, welcome_message })

Backend:
1. Receives request.id = promptId
2. Checks if prompt with that id exists → YES
3. Calls update_prompt_by_id(promptId, ...)
4. Updates only that prompt's fields
5. Returns success

Result: Only the specified prompt is updated
```

### Activating a Prompt

```
Frontend:
1. User selects prompt from dropdown
2. handlePromptChange() → handlePromptActivation()
3. api.activate(promptId)

Backend:
1. Receives prompt_id = promptId
2. Calls activate_prompt_by_id(promptId)
3. Deactivates all other default prompts
4. Activates the selected prompt
5. Returns success

Result: Selected prompt is active, all others are inactive
```

---

## Backward Compatibility

The implementation maintains backward compatibility:

1. **Legacy Support**: If `request.id` is not provided, the endpoint falls back to `organization_id`-based operations
2. **Existing Functions**: All existing functions (`update_prompt()`, `reset_prompt()`, etc.) still work
3. **No Breaking Changes**: Existing API calls without UUID still function

---

## Key Design Decisions

1. **Use Existing `id` Column**: No need for a separate UUID column. The existing `id` (UUID type) stores the frontend-generated UUID.

2. **Auto-Deactivation**: When creating/activating a prompt, all others are automatically deactivated. This matches frontend behavior where only one prompt is active.

3. **Preserve History**: Old prompts are deactivated (not deleted), preserving full history.

4. **Cache Clearing**: All UUID-based operations clear the cache to ensure fresh data.

5. **Minimal Changes**: Only added new functions and updated one endpoint. Existing code remains unchanged for compatibility.

---

## Testing Checklist

- [ ] Create new prompt with UUID → Should create and activate it
- [ ] Update existing prompt by UUID → Should update only that prompt
- [ ] Activate prompt by UUID → Should activate it and deactivate others
- [ ] List all prompts → Should show all prompts (active and inactive)
- [ ] Legacy calls without UUID → Should still work (backward compatibility)

---

## Summary

The backend now fully supports UUID-based prompt management:
- ✅ Uses existing `id` column to store frontend UUIDs
- ✅ Creates prompts with UUID from frontend
- ✅ Updates prompts by UUID
- ✅ Activates prompts by UUID (deactivates others)
- ✅ Maintains backward compatibility
- ✅ Preserves all prompt history
- ✅ Aligns perfectly with frontend behavior

All changes use existing database columns - no schema changes required!

