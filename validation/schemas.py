"""Base Pydantic schemas for data validation.

This module provides core validation schemas for the most critical data structures
in RoleAgentBot: agent configuration and interaction records.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class ValidationError(Exception):
    """Custom validation error for data validation failures."""
    pass


class AgentConfig(BaseModel):
    """Schema for agent_config.json."""
    
    default_personality: str = Field(..., min_length=1)
    default_language: str = Field(default="en-US")
    platform: str = Field(default="discord")
    llm: Dict[str, Any] = Field(default_factory=dict)
    dev_options: Dict[str, Any] = Field(default_factory=dict)
    gdpr: Dict[str, Any] = Field(default_factory=dict)
    fatigue_limits: Dict[str, Any] = Field(default_factory=dict)
    roles: Dict[str, Any] = Field(default_factory=dict)
    
    @field_validator('default_language')
    @classmethod
    def validate_language(cls, v: str) -> str:
        """Validate that language is one of the supported values."""
        allowed = ['en-US', 'es-ES', 'zh-CN']
        if v not in allowed:
            raise ValueError(f"Language must be one of {allowed}, got '{v}'")
        return v
    
    @field_validator('platform')
    @classmethod
    def validate_platform(cls, v: str) -> str:
        """Validate that platform is supported."""
        allowed = ['discord']
        if v not in allowed:
            raise ValueError(f"Platform must be one of {allowed}, got '{v}'")
        return v


class InteractionRecord(BaseModel):
    """Schema for interaction records in interactions.jsonl."""
    
    usuario_id: str = Field(..., min_length=1)
    usuario_nombre: Optional[str] = Field(default=None)
    canal_id: Optional[str] = Field(default=None)
    tipo_interaccion: str = Field(..., min_length=1)
    contexto: str = Field(..., min_length=1)
    metadata: Optional[str] = Field(default=None)  # JSON string
    fecha: str  # ISO format timestamp
    servidor_id: Optional[str] = Field(default=None)
    
    @field_validator('fecha')
    @classmethod
    def validate_iso_timestamp(cls, v: str) -> str:
        """Validate that fecha is a valid ISO 8601 timestamp."""
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Invalid ISO timestamp: {v}") from e
        return v
    
    @field_validator('usuario_id', 'canal_id', 'servidor_id')
    @classmethod
    def validate_id_fields(cls, v: Optional[str]) -> Optional[str]:
        """Validate that ID fields are either None or non-empty strings."""
        if v is not None and len(v.strip()) == 0:
            raise ValueError("ID fields must be non-empty strings or None")
        return v


class DailyMemoryEntry(BaseModel):
    """Schema for daily memory entries in state.json."""
    
    memory_date: str = Field(..., min_length=1)  # ISO date (YYYY-MM-DD)
    summary: str = Field(..., min_length=1)
    metadata: Optional[str] = Field(default=None)  # JSON string
    updated_at: str  # ISO timestamp
    
    @field_validator('memory_date')
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        """Validate that memory_date is in YYYY-MM-DD format."""
        try:
            datetime.strptime(v, '%Y-%m-%d')
        except ValueError as e:
            raise ValueError(f"Invalid date format (expected YYYY-MM-DD): {v}") from e
        return v
    
    @field_validator('updated_at')
    @classmethod
    def validate_iso_timestamp(cls, v: str) -> str:
        """Validate that updated_at is a valid ISO 8601 timestamp."""
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Invalid ISO timestamp: {v}") from e
        return v


class RelationshipEntry(BaseModel):
    """Schema for user relationship entries in state.json."""
    
    summary: str = Field(..., min_length=1)
    metadata: Optional[str] = Field(default=None)  # JSON string
    updated_at: str  # ISO timestamp
    last_interaction_at: Optional[str] = Field(default=None)
    
    @field_validator('updated_at', 'last_interaction_at')
    @classmethod
    def validate_iso_timestamp(cls, v: Optional[str]) -> Optional[str]:
        """Validate that timestamps are valid ISO 8601 format."""
        if v is None:
            return v
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Invalid ISO timestamp: {v}") from e
        return v


class NotableRecollection(BaseModel):
    """Schema for notable recollections in state.json."""
    
    memory_date: str = Field(..., min_length=1)  # ISO date (YYYY-MM-DD)
    recollection_text: str = Field(..., min_length=1)
    source_paragraph: Optional[str] = Field(default=None)
    extracted_at: str  # ISO timestamp
    used_count: int = Field(default=0, ge=0)
    last_used_at: Optional[str] = Field(default=None)
    
    @field_validator('memory_date')
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        """Validate that memory_date is in YYYY-MM-DD format."""
        try:
            datetime.strptime(v, '%Y-%m-%d')
        except ValueError as e:
            raise ValueError(f"Invalid date format (expected YYYY-MM-DD): {v}") from e
        return v
    
    @field_validator('extracted_at', 'last_used_at')
    @classmethod
    def validate_iso_timestamp(cls, v: Optional[str]) -> Optional[str]:
        """Validate that timestamps are valid ISO 8601 format."""
        if v is None:
            return v
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Invalid ISO timestamp: {v}") from e
        return v
