"""Capabilities set only by the verified server-side administration guard."""
from contextvars import ContextVar
private_tools_allowed: ContextVar[bool] = ContextVar("private_tools_allowed", default=False)
