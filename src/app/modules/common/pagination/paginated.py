from __future__ import annotations

from pydantic import BaseModel

from app.modules.common.pagination.pagination_meta import PaginationMeta


class Paginated[T](BaseModel):
    data: list[T]
    pagination: PaginationMeta
