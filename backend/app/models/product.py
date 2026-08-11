from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from backend.app.schemas.fields import FieldConflict, FieldProvenance


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProductInput(BaseModel):
    sku: str
    category_id: str
    source_template_id: str | None = None
    text: str | None = None
    pdf_path: str | None = None
    image_path: str | None = None
    url: str | None = None
    seed_web_overrides: dict[str, Any] | None = None


class ProductRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    sku: str
    category_id: str
    source_template_id: str | None = None
    fields: dict[str, FieldProvenance] = Field(default_factory=dict)
    conflicts: list[FieldConflict] = Field(default_factory=list)
    batch_id: str | None = None
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    status: str = "pending_review"  # pending_review | partially_approved | approved


class BatchRun(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    product_ids: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)


class PropagationSuggestion(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    source_template_id: str
    field_name: str
    old_value: Any
    new_value: Any
    source_product_id: str
    candidate_product_ids: list[str]
    status: str = "pending"  # pending | applied | dismissed


class DashboardStats(BaseModel):
    total_products: int = 0
    total_fields: int = 0
    high_confidence_pct: float = 0.0
    medium_confidence_pct: float = 0.0
    low_confidence_pct: float = 0.0
    fields_approved: int = 0
    fields_pending: int = 0
    conflicts_count: int = 0
    propagations_applied: int = 0
    estimated_minutes_saved: float = 0.0
