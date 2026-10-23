"""Request-local page session identity. Never written to persistent storage."""
from contextvars import ContextVar

page_session_id: ContextVar[str] = ContextVar("powerwave_page_session", default="")
