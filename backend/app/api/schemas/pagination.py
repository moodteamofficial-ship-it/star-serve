"""Shared pagination / search query params."""

from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1, le=10_000)
    limit: int = Field(default=25, ge=1, le=100)

    model_config = {"extra": "forbid"}

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


class PaginatedData(BaseModel):
    items: list
    page: int
    limit: int
    total: int

    model_config = {"extra": "forbid"}
