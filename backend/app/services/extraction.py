"""Stages 3-4: LLM extraction with schema validation, retries, sanity checks and rule fallback."""
import logging
import re
from typing import Optional, Tuple

from ..config import Settings
from ..schemas import CandidateProfile, JDExtraction, ProfileExtraction
from .dates import years_of_experience
from .fallback import degree_level, extract_jd_rules, extract_profile_rules, jd_bullets
from .llm import LLMClient, LLMInvalidOutput, LLMUnavailable, generate_validated
from .requirements import _toks, dedupe_requirements, finalize_requirement, promote_if_nothing_scored
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
    "(1 bachelor, 2 master, 3 PhD) only when stated. Ignore benefits, perks, company blurbs and legal text. "
    "Include EVERY requirement or qualification the posting lists, including preferred and nice-to-have items "
    "(importance nice). Do not merge separate bullets and do not skip any. "
    "kind is hard_skill (a named technology, tool or technical concept), experience (years of work), education "
    "(a degree), soft_skill (communication, teamwork, leadership, stakeholder work) or duty (a task the person "
    "will perform, such as 'design APIs'). Only hard_skill, experience and education are scored. "
    "skills_mode is any when the posting accepts any one of several alternatives (A / B / C, A or B), else all. "
    "For a year range such as 2 to 5 years put the lower number in years_required."
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
    """Stage 4. Returns (requirements, source). Code, not the LLM, assigns weights from importance."""
    if llm is not None:
        try:
            prompt = "Job description:\n\n" + jd_text[: settings.llm_max_input_chars]
            result = generate_validated(llm, JD_SYSTEM, prompt, JDExtraction, settings.llm_max_retries)
            cleaned = _clean_requirements(result, jd_text)
            if cleaned.requirements:
                return cleaned, "llm"
            log.warning("JD LLM returned no usable requirements; using rules")
        except (LLMUnavailable, LLMInvalidOutput) as exc:
            log.warning("JD LLM extraction failed (%s); using rules", type(exc).__name__)
    return _clean_requirements(extract_jd_rules(jd_text), jd_text), "rules"


def _match_bullet(req_text: str, bullets: list) -> Optional[dict]:
    """The posting bullet this requirement came from (the LLM may split one bullet into several requirements)."""
    sig = _toks(req_text)
    best, best_score = None, 0.0
    for b in bullets:
        bsig = _toks(b["text"])
        if not sig or not bsig:
            continue
        score = len(sig & bsig) / min(len(sig), len(bsig))
        if score > best_score:
            best, best_score = b, score
    return best if best_score >= 0.6 else None


def _clean_requirements(result: JDExtraction, jd_text: str = "") -> JDExtraction:
    """Drop empty requirements, give each a kind / year minimum / any-of mode, take importance from the posting's
    own headings when the bullet can be found (so weights follow importance, B4), merge near-duplicates."""
    bullets = jd_bullets(jd_text) if jd_text else []
    out = []
    for r in result.requirements:
        text = re.sub(r"\s+", " ", r.text).strip()
        if len(text) < 3:
            continue
        r = r.model_copy(update={"text": text})
        b = _match_bullet(text, bullets)
        if b is not None:
            r = r.model_copy(update={"importance": b["importance"]})
        out.append(finalize_requirement(r, duty_hint=bool(b and b["duty"])))
    return JDExtraction(requirements=promote_if_nothing_scored(dedupe_requirements(out)))


def default_weight(importance: str, settings: Settings) -> float:
    """Default weights 3 / 2 / 1 for must / should / nice (configurable)."""
    return float(settings.weights[importance])


def weight_for(kind: Optional[str], importance: str, settings: Settings) -> float:
    """3 / 2 / 1 by importance for scored kinds. Soft skills and duties are listed, not scored: weight 0."""
    from .requirements import is_scored
    return default_weight(importance, settings) if is_scored(kind) else 0.0
