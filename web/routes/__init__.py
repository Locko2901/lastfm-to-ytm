"""Web dashboard route blueprints."""

from .actions import actions_bp
from .api import api_bp
from .auth import auth_bp
from .sync import sync_bp

__all__ = ["actions_bp", "api_bp", "auth_bp", "sync_bp"]
