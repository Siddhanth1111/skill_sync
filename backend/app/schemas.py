"""Pydantic schemas: the LLM output contracts and the API payloads."""
from __future__ import annotations

from datetime import datetime
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
    skill_years: Dict[str, float] = {}  # canonical skill -> years from dated roles that mention it (code, not LLM)
    skill_links: Dict[str, List[int]] = {}  # canonical skill -> indexes of resume units that show it
    education_level: int = 0
    source: str = "llm"  # llm | rules
    warnings: List[str] = []


KINDS = ("hard_skill", "experience", "education", "soft_skill", "duty")
SCORED_KINDS = ("hard_skill", "experience", "education")


class JDRequirement(BaseModel):
    text: str
    type: str = Field(pattern="^(skill|experience|education)$")
    importance: str = Field(pattern="^(must|should|nice)$")
    skills: List[str] = []
    years_required: Optional[float] = Field(None, ge=0)
    degree_level_required: Optional[int] = Field(None, ge=1, le=3)
    # hard_skill, experience and education are scored; soft_skill and duty are listed but never scored.
    kind: Optional[str] = Field(None, pattern="^(hard_skill|experience|education|soft_skill|duty)$")
    # "any": the requirement is met by any one listed skill (A / B / C). "all": every listed skill is needed.
    skills_mode: str = Field("all", pattern="^(all|any)$")


class JDExtraction(BaseModel):
    """What the LLM must return for a job description (JDExtraction schema in the spec)."""

    requirements: List[JDRequirement]


# ---- API payloads -------------------------------------------------------------------------

class JobCreate(BaseModel):
    title: str
    text: str = Field(min_length=20)
    mode: str = Field("recruiter", pattern="^(recruiter|student)$")


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
    kind: Optional[str] = Field(None, pattern="^(hard_skill|experience|education|soft_skill|duty)$")
    skills_mode: Optional[str] = Field(None, pattern="^(all|any)$")


class JobOut(BaseModel):
    id: int
    title: str
    text: str
    requirements: List[RequirementOut] = []
    requirements_source: Optional[str] = None
    mode: str = "recruiter"
    scores_stale: bool = False
    created_at: Optional[datetime] = None
    candidate_count: int = 0
    parsed_count: int = 0

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


class ChunkOut(BaseModel):
    id: int
    idx: int
    section: str
    text: str
    context: Optional[str] = None

    model_config = {"from_attributes": True}


class CandidateDetail(CandidateStatus):
    job_id: Optional[int] = None
    profile: Optional[Dict[str, Any]] = None
    raw_text: Optional[str] = None
    chunks: List[ChunkOut] = []


class FeedbackIn(BaseModel):
    rating: str = Field(pattern="^(up|down)$")


class EvidenceFeedbackIn(BaseModel):
    requirement_id: int
    judgement: str = Field(pattern="^(wrong_evidence|correct|missed_evidence)$")
    grade: Optional[int] = Field(None, ge=0, le=2)  # optional: the grade the reviewer would give


class ImpactIn(BaseModel):
    groups: Dict[str, str]  # candidate id -> group label (consented, self-reported, or a marked demo)
    top_n: int = Field(ge=1)
    consent: bool = False  # the labels are self-reported and consented
    demo: bool = False  # the labels are made up to try the audit; the report is marked DEMO


class WeatIn(BaseModel):
    groups: str = Field("gender", pattern="^(gender|origin)$")


class MatchIn(BaseModel):
    candidate_id: int
    job_ids: List[int] = Field(min_length=1)


class WhatIfIn(BaseModel):
    candidate_id: int
    job_id: int
    addition: str = Field(min_length=5, max_length=2000)


# ---- auth
import re as _re
_EMAIL = _re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=72)  # bcrypt ignores bytes past 72
    full_name: str = Field("", max_length=120)
    role: str = Field("recruiter", pattern="^(recruiter|student)$")  # admins are created by the operator, never self-service

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL.match(v):
            raise ValueError("enter a valid email address")
        return v


class LoginIn(BaseModel):
    email: str
    password: str = Field(max_length=72)


class UserOut(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    role: str
    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
