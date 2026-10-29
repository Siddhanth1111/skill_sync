"""Pydantic schemas: the LLM output contracts and the API payloads."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from .services.dates import parse_date


class Role(BaseModel):
    title: str
    company: Optional[str] = None
    start: Optional[str] = Field(None, description="YYYY-MM or YYYY")
    end: Optional[str] = Field(None, description="YYYY-MM, YYYY, or 'present'")

    @field_validator("start", "end")
    @classmethod
    def _date_must_parse(cls, v: Optional[str]) -> Optional[str]:
        # Raising here makes the validation-retry loop feed a precise error back to the LLM.
        if v is not None and parse_date(v) is None:
            raise ValueError("unparseable date %r; use YYYY-MM, YYYY or 'present'" % v)
        return v


class Education(BaseModel):
    degree: str
    institution: Optional[str] = None
    level: int = Field(ge=0, le=3, description="0 none/other, 1 bachelor, 2 master, 3 PhD")
    year: Optional[str] = None


class ProfileExtraction(BaseModel):
    """What the LLM must return (CandidateProfile schema in the spec)."""

    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    skills: List[str] = []
    roles: List[Role] = []
    education: List[Education] = []


class CandidateProfile(ProfileExtraction):
    """Validated profile as stored. The fields below are filled by code, never by the LLM."""

    years_experience: float = 0.0
    education_level: int = 0
    source: str = "llm"  # llm | rules
    warnings: List[str] = []


class JDRequirement(BaseModel):
    text: str
    type: str = Field(pattern="^(skill|experience|education)$")
    importance: str = Field(pattern="^(must|should|nice)$")
    skills: List[str] = []
    years_required: Optional[float] = Field(None, ge=0)
    degree_level_required: Optional[int] = Field(None, ge=1, le=3)


class JDExtraction(BaseModel):
    """What the LLM must return for a job description (JDExtraction schema in the spec)."""

    requirements: List[JDRequirement]


# ---- API payloads -------------------------------------------------------------------------

class JobCreate(BaseModel):
    title: str
    text: str = Field(min_length=20)


class RequirementOut(BaseModel):
    id: int
    idx: int
    text: str
    type: str
    importance: str
    weight: float
    meta: Dict[str, Any]

    model_config = {"from_attributes": True}


class RequirementPatch(BaseModel):
    id: int
    text: Optional[str] = None
    importance: Optional[str] = Field(None, pattern="^(must|should|nice)$")
    weight: Optional[float] = Field(None, ge=0)


class JobOut(BaseModel):
    id: int
    title: str
    text: str
    requirements: List[RequirementOut] = []
    requirements_source: Optional[str] = None

    model_config = {"from_attributes": True}


class CandidateStatus(BaseModel):
    id: int
    filename: str
    status: str
    error: Optional[str] = None
    source: Optional[str] = None
    needs_ocr: bool = False
    parse_confidence: Optional[Dict[str, Any]] = None

    model_config = {"from_attributes": True}


class JobStatus(BaseModel):
    job_id: int
    total: int
    counts: Dict[str, int]
    files: List[CandidateStatus]
