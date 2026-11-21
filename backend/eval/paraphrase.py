"""The paraphrase regression set from the review plan (section 4): each requirement must grade as expected whatever
the wording. Runs the full v2 path (rules extraction, units, hybrid retrieval, rerank, scoring), so it exercises the
same code as a real job.

    python -m eval.paraphrase            # real models (downloads them on first use)
    python -m eval.paraphrase --light    # the light stand-ins, for a quick check without downloads

Cases marked needs_real depend on what a trained reranker knows and are skipped with --light.
"""
import argparse
import sys
from typing import Dict, List

from app.config import Settings
from app.services.chunking import chunk_resume
from app.services.extraction import extract_requirements, weight_for
from app.services.fallback import extract_profile_rules
from app.services.models import build_models
from app.services.requirements import requirement_meta
from app.services.scoring import ReqView, embed_queries, score_candidate, units_for_text
from app.services.skillgraph import link_skills

# (requirement, resume wording, acceptable statuses, needs_real)  statuses: met | partial | not_met | unscored
CASES = [
    ("Query optimization and performance tuning", "Tuned slow SQL using execution plans and indexes", {"met"}, False),
    ("Strong knowledge of RDBMS", "Designed schemas in PostgreSQL and MySQL", {"met"}, False),
    ("CI/CD pipelines", "Automated builds and deployments with Jenkins", {"met"}, False),
    # Soft skills are listed, never scored (a documented change from the plan's "partial or met").
    ("Stakeholder management", "Worked with business teams to agree scope and priorities", {"unscored"}, False),
    ("Machine learning", "Trained a logistic regression model to predict churn", {"partial"}, True),
    ("Kafka", "Built streaming ingestion with RabbitMQ", {"partial", "not_met"}, False),
    ("Python", "Wrote automation scripts in Perl", {"not_met"}, False),
    ("3+ years of backend experience", "Built backend services and APIs", {"met"}, False),
]


def run_case(requirement: str, wording: str, models, settings: Settings) -> Dict:
    jd = "Requirements\n- %s\n" % requirement
    ext, _ = extract_requirements(jd, None, settings)
    r = ext.requirements[0]
    if weight_for(r.kind, r.importance, settings) == 0:
        return {"status": "unscored", "score": None, "kind": r.kind}
    # the wording sits under a dated backend role, as it would on a real resume
    resume = "EXPERIENCE\nBackend Developer, Acme   Jan 2021 - Dec 2023\n- %s\n" % wording
    profile = extract_profile_rules(resume).model_dump()
    _, views, profile = units_for_text(resume, profile, models, settings)
    rv = ReqView(1, 0, r.text, r.type, r.importance, 3.0, requirement_meta(r))
    row = score_candidate([rv], embed_queries([rv], models), views, resume, profile, models, settings)[0]
    return {"status": row.status, "score": row.final_score, "kind": r.kind, "trace": row.trace}


def run(models, settings: Settings, light: bool = False) -> List[Dict]:
    out = []
    for requirement, wording, expected, needs_real in CASES:
        if light and needs_real:
            continue
        got = run_case(requirement, wording, models, settings)
        out.append({"requirement": requirement, "wording": wording, "expected": sorted(expected), **got,
                    "ok": got["status"] in expected})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--light", action="store_true")
    args = ap.parse_args()
    settings = Settings(model_backend="light" if args.light else "real")
    rows = run(build_models(settings), settings, args.light)
    for r in rows:
        score = "-" if r["score"] is None else "%.2f" % r["score"]
        print("%-4s %-45s -> %-10s %s (expected %s)" % ("ok" if r["ok"] else "FAIL", r["requirement"][:45], r["status"], score, "/".join(r["expected"])))
    print("\n%d of %d as expected (models: %s)" % (sum(r["ok"] for r in rows), len(rows), settings.model_backend))
    return 0 if all(r["ok"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
