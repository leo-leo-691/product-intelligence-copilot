from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ConfidenceBand(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class SourceType(str, Enum):
    DOCUMENT = "document"
    IMAGE = "image"
    WEB = "web"


class ExtractionMethod(str, Enum):
    TABLE_PARSE = "table-parse"
    TEXT_LLM = "text-LLM"
    VISION_LLM = "vision-LLM"
    WEB_AGENT = "web-agent"
    MOCK = "mock"


class FieldProvenance(BaseModel):
    value: Any = None
    confidence_score: ConfidenceBand = ConfidenceBand.LOW
    confidence_raw: float = 0.0
    confidence_reasoning: dict[str, float] = Field(default_factory=dict)
    source_type: SourceType | None = None
    source_snippet: str | None = None
    source_location: str | None = None
    extraction_method: ExtractionMethod = ExtractionMethod.MOCK
    needs_review: bool = True
    review_status: str = "pending"  # pending | approved | rejected | edited
    not_found: bool = False
    validation_errors: list[str] = Field(default_factory=list)


class ConflictCandidate(BaseModel):
    value: Any
    source_type: SourceType
    source_snippet: str | None = None
    source_location: str | None = None
    extraction_method: ExtractionMethod


class FieldConflict(BaseModel):
    field_name: str
    candidates: list[ConflictCandidate]
    resolved: bool = False


class ConfidenceComponents(BaseModel):
    method_reliability: float
    cross_source_agreement: float
    validation_score: float
    format_match: float
    raw: float
    band: ConfidenceBand
