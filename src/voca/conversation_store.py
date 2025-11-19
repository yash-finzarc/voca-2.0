"""
Utilities for persisting and retrieving multi-tenant conversation data.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.voca.supabase_client import get_supabase_client, is_supabase_configured

logger = logging.getLogger("voca.conversation_store")


def save_conversation_snapshot(
    organization_id: Optional[str],
    call_sid: Optional[str],
    transcript: List[Dict[str, Any]],
    lead_data: Dict[str, Any],
    lead_status: Optional[str],
) -> bool:
    """
    Persist the latest conversation snapshot for analytics and CRM workflows.
    Returns True if the record was stored successfully.
    """
    if not organization_id:
        logger.debug("Conversation snapshot skipped: missing organization_id")
        return False

    if not is_supabase_configured():
        logger.debug("Supabase not configured, skipping conversation persistence")
        return False

    client = get_supabase_client()
    if client is None:
        logger.warning("Supabase client unavailable, skipping conversation persistence")
        return False

    payload = {
        "organization_id": organization_id,
        "call_sid": call_sid,
        "transcript": transcript or [],
        "lead_data": lead_data or {},
        "lead_status": lead_status,
        "created_at": datetime.utcnow().isoformat(),
    }

    try:
        table = client.table("conversations")
        if call_sid:
            table = table.upsert(payload, on_conflict="call_sid")
        else:
            table = table.insert(payload)
        table.execute()
        logger.debug("Conversation snapshot stored for org %s", organization_id)
        return True
    except Exception as exc:
        logger.error("Failed to persist conversation snapshot: %s", exc)
        return False

