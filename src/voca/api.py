"""
FastAPI application for VOCA frontend backend integration.
DEPRECATED: This file is kept for backward compatibility.
New code should import from src.voca.api.main instead.

This file now just re-exports the app from the new modular structure.
"""
import logging

logger = logging.getLogger(__name__)

# Import from the new modular structure
from src.voca.api.main import app

# Re-export app for backward compatibility
__all__ = ['app']