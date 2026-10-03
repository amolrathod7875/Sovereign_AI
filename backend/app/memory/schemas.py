"""Memory scope, type, and operation enumerations.

These are the canonical values for the M4 long-term memory layer.
Scopes and types are intentionally centralized so every consumer
(candidates, repository, API, tests) shares one source of truth.
"""
from enum import Enum


class MemoryScope(str, Enum):
    PERSONAL = "PERSONAL"
    CONVERSATION = "CONVERSATION"
    PROJECT = "PROJECT"
    ORGANIZATION = "ORGANIZATION"


class MemoryType(str, Enum):
    USER_PREFERENCE = "USER_PREFERENCE"
    PROJECT_FACT = "PROJECT_FACT"
    DECISION = "DECISION"
    WORKING_CONTEXT = "WORKING_CONTEXT"
    ENTITY = "ENTITY"
    TASK_STATE = "TASK_STATE"
    CONVERSATION_FACT = "CONVERSATION_FACT"
    OTHER = "OTHER"


class MemoryOutboxOperation(str, Enum):
    UPSERT = "UPSERT"
    DELETE = "DELETE"


class MemoryOutboxStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


# Scopes allowed for automatic extraction
AUTOMATIC_SCOPES = {MemoryScope.PERSONAL, MemoryScope.CONVERSATION}

# Scopes reserved for future explicit/authorized creation only
RESERVED_SCOPES = {MemoryScope.PROJECT, MemoryScope.ORGANIZATION}
