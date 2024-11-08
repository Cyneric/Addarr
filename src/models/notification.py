from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
from telegram.constants import ParseMode

class NotificationType(Enum):
    """Types of notifications"""
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    ADMIN = "ADMIN"

@dataclass
class Notification:
    """Notification data model"""
    type: NotificationType
    message: str
    target_chat_ids: List[int]
    notify_admin: bool = True
    parse_mode: Optional[str] = ParseMode.HTML 