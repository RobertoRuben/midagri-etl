from __future__ import annotations

from pydantic import BaseModel


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_prev: bool

    @classmethod
    def build(cls, page: int, page_size: int, total_items: int) -> PaginationMeta:
        total_pages = (total_items + page_size - 1) // page_size if page_size else 0
        return cls(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        )
