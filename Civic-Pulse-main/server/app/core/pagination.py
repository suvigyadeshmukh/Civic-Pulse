"""Civic Pulse — Generic Pydantic v2 pagination and response envelope schemas.

Every JSON endpoint wraps its payload in :class:`ApiEnvelope` so the React
client can rely on a single response shape::

    {
        "success": true,
        "data": { ... },
        "meta": {                   // present only on list endpoints
            "page": 1,
            "page_size": 20,
            "total_items": 142,
            "total_pages": 8
        }
    }
"""

from __future__ import annotations

import math
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedMeta(BaseModel):
    """Pagination metadata attached to paginated list responses."""

    page: int = Field(ge=1, description="Current page number (1-indexed).")
    page_size: int = Field(ge=1, le=100, description="Items per page.")
    total_items: int = Field(ge=0, description="Total matching items across all pages.")
    total_pages: int = Field(ge=0, description="Total number of pages.")

    @classmethod
    def build(
        cls,
        *,
        page: int,
        page_size: int,
        total_items: int,
    ) -> PaginatedMeta:
        """Convenience factory that calculates ``total_pages`` automatically."""
        return cls(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=math.ceil(total_items / page_size) if page_size > 0 else 0,
        )


class ApiEnvelope(BaseModel, Generic[T]):
    """Standard API response wrapper consumed by every endpoint.

    Usage::

        @router.get("/items/{id}", response_model=ApiEnvelope[ItemOut])
        async def get_item(...):
            return ApiEnvelope(data=item)

    For paginated lists::

        return ApiEnvelope(
            data=items,
            meta=PaginatedMeta.build(page=page, page_size=size, total_items=total),
        )
    """

    success: bool = True
    data: T
    meta: PaginatedMeta | None = None


class PaginationParams(BaseModel):
    """Query parameters for paginated list endpoints.

    Domain routers can depend on this directly::

        @router.get("/items")
        async def list_items(params: PaginationParams = Depends()):
            ...
    """

    page: int = Field(default=1, ge=1, description="Page number (1-indexed).")
    page_size: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Number of items per page (max 100).",
    )

    @property
    def offset(self) -> int:
        """SQL ``OFFSET`` value derived from page and page_size."""
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        """Alias for ``page_size`` — convenience for SQLAlchemy ``.limit()``."""
        return self.page_size

