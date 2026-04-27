"""Pydantic schemas for role configurations and data structures.

This module provides validation schemas for all role-specific data structures
including POE2, News Watcher, Dice Game, Beggar, Nordic Runes, Ring Accusations,
and MC (Master of Ceremonies) configurations.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class POE2Subscription(BaseModel):
    """Schema for POE2 subscription data."""
    
    league: str = Field(..., min_length=1)
    tracked_items: List[Dict[str, Any]] = Field(default_factory=list)
    purchases: List[Dict[str, Any]] = Field(default_factory=list)
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


class WatcherSubscription(BaseModel):
    """Schema for News Watcher subscription data."""
    
    feed_id: Optional[int] = None
    premises: Optional[str] = Field(default=None)
    keywords: Optional[str] = Field(default=None)
    method: str = Field(default="general")
    is_active: bool = Field(default=True)
    subscribed_at: str  # ISO timestamp
    created_by: Optional[str] = Field(default=None)
    
    @field_validator('subscribed_at')
    @classmethod
    def validate_iso_timestamp(cls, v: str) -> str:
        """Validate that timestamp is valid ISO 8601 format."""
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Invalid ISO timestamp: {v}") from e
        return v
    
    @field_validator('method')
    @classmethod
    def validate_method(cls, v: str) -> str:
        """Validate that method is one of the allowed values."""
        allowed = ['general', 'premise', 'keyword']
        if v not in allowed:
            raise ValueError(f"Method must be one of {allowed}, got '{v}'")
        return v


class DiceGameStats(BaseModel):
    """Schema for Dice Game statistics."""
    
    player_id: str = Field(..., min_length=1)
    total_wins: int = Field(default=0, ge=0)
    total_losses: int = Field(default=0, ge=0)
    total_rolls: int = Field(default=0, ge=0)
    last_played_at: Optional[str] = Field(default=None)  # ISO timestamp
    created_at: str  # ISO timestamp
    
    @field_validator('created_at', 'last_played_at')
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


class BeggarSubrole(BaseModel):
    """Schema for Beggar subrole data."""
    
    player_id: str = Field(..., min_length=1)
    request_count: int = Field(default=0, ge=0)
    last_request_at: Optional[str] = Field(default=None)  # ISO timestamp
    created_at: str  # ISO timestamp
    
    @field_validator('created_at', 'last_request_at')
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


class NordicRunesReading(BaseModel):
    """Schema for Nordic Runes reading data."""
    
    user_id: str = Field(..., min_length=1)
    reading_date: str = Field(..., min_length=1)  # ISO date (YYYY-MM-DD)
    runes_drawn: List[str] = Field(default_factory=list)
    interpretation: Optional[str] = Field(default=None)
    created_at: str  # ISO timestamp
    
    @field_validator('reading_date')
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        """Validate that reading_date is in YYYY-MM-DD format."""
        try:
            datetime.strptime(v, '%Y-%m-%d')
        except ValueError as e:
            raise ValueError(f"Invalid date format (expected YYYY-MM-DD): {v}") from e
        return v
    
    @field_validator('created_at')
    @classmethod
    def validate_iso_timestamp(cls, v: str) -> str:
        """Validate that timestamp is valid ISO 8601 format."""
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Invalid ISO timestamp: {v}") from e
        return v


class RingAccusation(BaseModel):
    """Schema for Ring Accusation game data."""
    
    accuser_id: str = Field(..., min_length=1)
    accused_id: str = Field(..., min_length=1)
    accusation_text: str = Field(..., min_length=1)
    verdict: Optional[str] = Field(default=None)
    created_at: str  # ISO timestamp
    
    @field_validator('created_at')
    @classmethod
    def validate_iso_timestamp(cls, v: str) -> str:
        """Validate that timestamp is valid ISO 8601 format."""
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Invalid ISO timestamp: {v}") from e
        return v


class MCPlaylist(BaseModel):
    """Schema for MC (Master of Ceremonies) playlist data."""
    
    playlist_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    songs: List[Dict[str, Any]] = Field(default_factory=list)
    created_by: str = Field(..., min_length=1)
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


class MCQueueEntry(BaseModel):
    """Schema for MC queue entry data."""
    
    song_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)
    requested_by: str = Field(..., min_length=1)
    added_at: str  # ISO timestamp
    
    @field_validator('added_at')
    @classmethod
    def validate_iso_timestamp(cls, v: str) -> str:
        """Validate that timestamp is valid ISO 8601 format."""
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Invalid ISO timestamp: {v}") from e
        return v


class MCPreferences(BaseModel):
    """Schema for MC user preferences data."""
    
    user_id: str = Field(..., min_length=1)
    volume: float = Field(default=1.0, ge=0.0, le=1.0)
    auto_play: bool = Field(default=True)
    shuffle: bool = Field(default=False)
    updated_at: str  # ISO timestamp
    
    @field_validator('updated_at')
    @classmethod
    def validate_iso_timestamp(cls, v: str) -> str:
        """Validate that timestamp is valid ISO 8601 format."""
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Invalid ISO timestamp: {v}") from e
        return v
