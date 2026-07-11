"""Council web UI backend — chat feed and owner actions."""

from council.web.chat import build_chat_feed
from council.web.service import CouncilWebService

__all__ = ["CouncilWebService", "build_chat_feed"]