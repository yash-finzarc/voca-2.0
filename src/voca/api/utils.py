from typing import Optional

from src.voca.config import Config


def resolve_org_id(body_value: Optional[str] = None, query_value: Optional[str] = None, header_value: Optional[str] = None) -> Optional[str]:
    """Determine the organization ID from request components."""
    return body_value or query_value or header_value or Config.default_organization_id or None

