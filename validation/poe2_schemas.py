"""Pydantic schemas for POE2 (Path of Exile 2) data structures.

This module provides validation schemas for POE2 game data including
item catalogs, price data, and price history entries.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class ItemCatalogEntry(BaseModel):
    """Schema for POE2 item catalog entry."""
    
    item_id: int = Field(..., ge=0)
    item_name: str = Field(..., min_length=1)
    base_type: str = Field(..., min_length=1)
    item_class: str = Field(..., min_length=1)
    rarity: str = Field(default="Normal")
    icon: Optional[str] = Field(default=None)
    metadata: Optional[str] = Field(default=None)  # JSON string
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
    
    @field_validator('rarity')
    @classmethod
    def validate_rarity(cls, v: str) -> str:
        """Validate that rarity is one of the allowed values."""
        allowed = ['Normal', 'Magic', 'Rare', 'Unique', 'Currency']
        if v not in allowed:
            raise ValueError(f"Rarity must be one of {allowed}, got '{v}'")
        return v


class PriceData(BaseModel):
    """Schema for POE2 price data (latest prices)."""
    
    item_id: int = Field(..., ge=0)
    item_name: str = Field(..., min_length=1)
    league: str = Field(..., min_length=1)
    price: float = Field(..., ge=0.0)
    currency: str = Field(default="chaos")
    price_date: str  # ISO timestamp
    source: Optional[str] = Field(default="api")
    metadata: Optional[str] = Field(default=None)  # JSON string
    
    @field_validator('price_date')
    @classmethod
    def validate_iso_timestamp(cls, v: str) -> str:
        """Validate that timestamp is valid ISO 8601 format."""
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Invalid ISO timestamp: {v}") from e
        return v
    
    @field_validator('currency')
    @classmethod
    def validate_currency(cls, v: str) -> str:
        """Validate that currency is one of the allowed values."""
        allowed = ['chaos', 'divine', 'gold', 'silver', 'copper']
        if v not in allowed:
            raise ValueError(f"Currency must be one of {allowed}, got '{v}'")
        return v


class PriceHistoryEntry(BaseModel):
    """Schema for POE2 price history entry."""
    
    item_id: int = Field(..., ge=0)
    item_name: str = Field(..., min_length=1)
    league: str = Field(..., min_length=1)
    price: float = Field(..., ge=0.0)
    currency: str = Field(default="chaos")
    price_date: str  # ISO timestamp
    volume: int = Field(default=0, ge=0)
    source: Optional[str] = Field(default="api")
    metadata: Optional[str] = Field(default=None)  # JSON string
    
    @field_validator('price_date')
    @classmethod
    def validate_iso_timestamp(cls, v: str) -> str:
        """Validate that timestamp is valid ISO 8601 format."""
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Invalid ISO timestamp: {v}") from e
        return v
    
    @field_validator('currency')
    @classmethod
    def validate_currency(cls, v: str) -> str:
        """Validate that currency is one of the allowed values."""
        allowed = ['chaos', 'divine', 'gold', 'silver', 'copper']
        if v not in allowed:
            raise ValueError(f"Currency must be one of {allowed}, got '{v}'")
        return v
