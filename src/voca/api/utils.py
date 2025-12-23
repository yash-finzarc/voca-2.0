"""
Utility functions for API routes.
"""
import audioop
from typing import Optional

from src.voca.config import Config


def pcm_to_mulaw(pcm_bytes: bytes) -> bytes:
    """Convert 16-bit PCM audio to 8-bit mu-law for Twilio."""
    # Twilio expects mu-law at 8kHz. Sarvam often returns 22050Hz or 16kHz.
    # This utility assumes the caller provides 8kHz 16-bit PCM or handles resampling.
    return audioop.lin2ulaw(pcm_bytes, 2)


def mulaw_to_pcm(mulaw_bytes: bytes) -> bytes:
    """Convert 8-bit mu-law to 16-bit PCM."""
    return audioop.ulaw2lin(mulaw_bytes, 2)


def resolve_org_id(
    body_value: Optional[str] = None,
    query_value: Optional[str] = None,
    header_value: Optional[str] = None,
) -> Optional[str]:
    """Determine the organization ID from request components."""
    return body_value or query_value or header_value or Config.default_organization_id or None

