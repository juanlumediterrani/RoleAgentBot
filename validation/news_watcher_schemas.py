"""Pydantic schemas for News Watcher data structures.

This module provides validation schemas for RSS feed configurations,
health logs, and user premises for the News Watcher role.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class FeedConfig(BaseModel):
    """Schema for RSS feed configuration."""
    
    feed_id: int = Field(..., ge=0)
    feed_name: str = Field(..., min_length=1)
    feed_url: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    language: str = Field(default="en")
    update_interval_hours: int = Field(default=1, ge=1)
    is_active: bool = Field(default=True)
    created_at: str  # ISO timestamp
    updated_at: str  # ISO timestamp
    
    @field_validator('created_at', 'updated_at')
    @classmethod
    def validate_iso_timestamp(cls, v: str) -> str:
        """Validate that timestamps are valid ISO 8601 format."""
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Invalid ISO timestamp: {v}") from e
        return v
    
    @field_validator('language')
    @classmethod
    def validate_language(cls, v: str) -> str:
        """Validate that language is one of the supported values."""
        allowed = ['en', 'es', 'zh']
        if v not in allowed:
            raise ValueError(f"Language must be one of {allowed}, got '{v}'")
        return v


class FeedHealthEntry(BaseModel):
    """Schema for feed health log entry."""
    
    feed_id: int = Field(..., ge=0)
    feed_name: str = Field(..., min_length=1)
    status: str = Field(..., min_length=1)
    error_message: Optional[str] = Field(default=None)
    last_check: str  # ISO timestamp
    last_success: Optional[str] = Field(default=None)  # ISO timestamp
    consecutive_failures: int = Field(default=0, ge=0)
    
    @field_validator('last_check', 'last_success')
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
    
    @field_validator('status')
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Validate that status is one of the allowed values."""
        allowed = ['healthy', 'unhealthy', 'error', 'disabled']
        if v not in allowed:
            raise ValueError(f"Status must be one of {allowed}, got '{v}'")
        return v


class UserPremises(BaseModel):
    """Schema for user premises in News Watcher."""
    
    user_id: str = Field(..., min_length=1)
    premises: List[str] = Field(default_factory=list)
    context: Optional[str] = Field(default=None)
    created_at: str  # ISO timestamp
    updated_at: str  # ISO timestamp
    
    @field_validator('premises')
    @classmethod
    def validate_premises_count(cls, v: List[str]) -> List[str]:
        """Validate that there are at most 3 premises."""
        if len(v) > 3:
            raise ValueError(f"Maximum 3 premises allowed, got {len(v)}")
        return v
    
    @field_validator('premises')
    @classmethod
    def validate_premises_content(cls, v: List[str]) -> List[str]:
        """Validate that all premises are non-empty strings."""
        for premise in v:
            if not isinstance(premise, str) or len(premise.strip()) == 0:
                raise ValueError("All premises must be non-empty strings")
        return v
    
    @field_validator('created_at', 'updated_at')
    @classmethod
    def validate_iso_timestamp(cls, v: str) -> str:
        """Validate that timestamps are valid ISO 8601 format."""
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Invalid ISO timestamp: {v}") from e
        return v


class NewsArticle(BaseModel):
    """Schema for news article data."""
    
    article_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)
    summary: Optional[str] = Field(default=None)
    published_at: str  # ISO timestamp
    feed_id: int = Field(..., ge=0)
    feed_name: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    language: str = Field(default="en")
    
    @field_validator('published_at')
    @classmethod
    def validate_iso_timestamp(cls, v: str) -> str:
        """Validate that timestamp is valid ISO 8601 format."""
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Invalid ISO timestamp: {v}") from e
        return v
    
    @field_validator('language')
    @classmethod
    def validate_language(cls, v: str) -> str:
        """Validate that language is one of the supported values."""
        allowed = ['en', 'es', 'zh']
        if v not in allowed:
            raise ValueError(f"Language must be one of {allowed}, got '{v}'")
        return v
