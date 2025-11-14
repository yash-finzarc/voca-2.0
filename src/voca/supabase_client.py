"""
Supabase client initialization for VOCA.
Handles connection to Supabase database.
"""
import logging
from typing import Optional

from src.voca.config import Config

logger = logging.getLogger("voca.supabase")

_supabase_client: Optional[object] = None


def get_supabase_client():
    """Get or create Supabase client instance."""
    global _supabase_client
    
    if _supabase_client is not None:
        return _supabase_client
    
    if not Config.supabase_url or not Config.supabase_key:
        logger.warning("Supabase credentials not configured. System prompt will use default.")
        return None
    
    try:
        from supabase import create_client, Client
        
        _supabase_client = create_client(Config.supabase_url, Config.supabase_key)
        logger.info("Supabase client initialized successfully")
        return _supabase_client
    except ImportError:
        logger.error("supabase package not installed. Install with: pip install supabase")
        return None
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")
        return None


def is_supabase_configured() -> bool:
    """Check if Supabase is properly configured."""
    return bool(Config.supabase_url and Config.supabase_key)

