"""Stages 3-4: LLM extraction with schema validation, retries, sanity checks and rule fallback."""
import logging
import re
from typing import Optional, Tuple

from ..config import Settings
from ..schemas import CandidateProfile, JDExtraction, ProfileExtraction
from .dates import years_of_experience
from .fallback import degree_level, extract_jd_rules, extract_profile_rules
from .llm import LLMClient, LLMInvalidOutput, LLMUnavailable, generate_validated
from .taxonomy import contains_skill

log = logging.getLogger(__name__)  # never log resume text or personal data

RESUME_SYSTEM = (
    "You extract structured data from resumes. Return JSON only, matching the schema. "
    "Copy values exactly as written in the resume. Use null for anything not present. Never guess or invent. "
    "Education level: 0 none or other, 1 bachelor, 2 master, 3 PhD. Dates as YYYY-MM, YYYY or 'present'."
)
JD_SYSTEM = (
    "You split a job description into atomic, individually checkable requirements. Return JSON only, matching "
    "the schema. type is skill, experience or education. importance is must (required), should (expected) or "
    "nice (preferred or bonus). Put related skills in skills. Set years_required or degree_level_required "
    "(1 bachelor, 2 master, 3 PhD) only when stated. Ignore benefits, perks, company blurbs and legal text."
)


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def _normalise(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def sanity_check(profile: ProfileExtraction, text: str) -> CandidateProfile:
    """Checks on LLM output: email and phone must appear in the text, skills must appear in the text, and
    years of experience are computed by code from role dates (overlaps merged). Dropped values are noted."""
    warnings = []
    email = profile.email
    if email and _normalise(email) not in _normalise(text):
        warnings.append("email not found in resume text; dropped")
        email = None
    phone = profile.phone
    if phone and _digits(phone) not in _digits(text):
        warnings.append("phone not found in resume text; dropped")
        phone = None

    kept, dropped = [], 0
    seen = set()
    for skill in profile.skills:
        key = skill.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        if contains_skill(text, skill):
            kept.append(skill.strip())
        else:
            dropped += 1
    if dropped:
        warnings.append("%d skill(s) not found in resume text; dropped" % dropped)

    level = max([e.level for e in profile.education], default=0)
    rule_level = degree_level(text)
    if level > rule_level:
        warnings.append("education level %d from LLM is higher than any degree wording found by rules" % level)

    return CandidateProfile(
        name=profile.name, email=email, phone=phone, skills=kept,
        roles=profile.roles, education=profile.education,
        years_experience=years_of_experience(profile.roles),
        education_level=level, source="llm", warnings=warnings,
    )


def extract_profile(text: str, llm: Optional[LLMClient], settings: Settings) -> CandidateProfile:
    """Stage 3. LLM first (temperature 0, schema-validated, retried with the error fed back); on any LLM failure
    the rule extractor answers and the profile is marked source='rules'."""
    if llm is not None:
        try:
            prompt = "Resume text:\n\n" + text[: settings.llm_max_input_chars]
            raw = generate_validated(llm, RESUME_SYSTEM, prompt, ProfileExtraction, settings.llm_max_retries)
            return sanity_check(raw, text)
        except (LLMUnavailable, LLMInvalidOutput) as exc:
            log.warning("resume LLM extraction failed (%s); using rules", type(exc).__name__)
    profile = extract_profile_rules(text)
    profile.warnings.append("extracted by rules (LLM unavailable or invalid output)")
    return profile


def extract_requirements(jd_text: str, llm: Optional[LLMClient], settings: Settings) -> Tuple[JDExtraction, str]:
    """Stage 4. Returns (requirements, source). Code, not the LLM, will assign weights from importance."""
    if llm is not None:
        try:
            prompt = "Job description:\n\n" + jd_text[: settings.llm_max_input_chars]
            result = generate_validated(llm, JD_SYSTEM, prompt, JDExtraction, settings.llm_max_retries)
            cleaned = _clean_requirements(result)
            if cleaned.requirements:
                return cleaned, "llm"
            log.warning("JD LLM returned no usable requirements; using rules")
        except (LLMUnavailable, LLMInvalidOutput) as exc:
            log.warning("JD LLM extraction failed (%s); using rules", type(exc).__name__)
    return _clean_requirements(extract_jd_rules(jd_text)), "rules"


def _clean_requirements(result: JDExtraction) -> JDExtraction:
    """Drop empty and duplicate requirements; keep order."""
    seen, out = set(), []
    for r in result.requirements:
        text = re.sub(r"\s+", " ", r.text).strip()
        if len(text) < 3 or _normalise(text) in seen:
            continue
        seen.add(_normalise(text))
        out.append(r.model_copy(update={"text": text}))
    return JDExtraction(requirements=out)


def default_weight(importance: str, settings: Settings) -> float:
    """Default weights 3 / 2 / 1 for must / should / nice (configurable)."""
    return float(settings.weights[importance])
