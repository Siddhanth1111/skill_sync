"""Backend and browser must give the same ranking for the same matrix and weights (spec: definition of done)."""
import json
import os
import random
import shutil
import subprocess

import pytest

from app.services.ranking import rank_candidates

RANK_JS = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "src", "lib", "rank.js")
TH = {"met": 0.6, "partial": 0.3, "must_penalty": 0.9, "tier_band": 0.02}


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_python_and_javascript_rank_identically():
    rng = random.Random(7)
    for trial in range(30):
        reqs = [{"id": i, "importance": rng.choice(["must", "should", "nice"]), "weight": rng.choice([0, 1, 2, 3, 0.5, 2.5])}
                for i in range(1, rng.randint(2, 9))]
        if sum(r["weight"] for r in reqs) == 0:
            reqs[0]["weight"] = 1
        # include exact-threshold scores and ties on purpose
        pool = [0.0, 0.3, 0.6, 0.29999, 0.59999, 1.0, 0.85, 0.45]
        matrix = {c: {r["id"]: rng.choice(pool + [rng.random()]) for r in reqs if rng.random() > 0.1}
                  for c in range(1, rng.randint(2, 12))}
        flags = {c: {rid: True for rid in m if rng.random() < 0.15} for c, m in matrix.items()}
        py = rank_candidates(reqs, matrix, TH, flags)
        script = ("import {rankCandidates} from %s;"
                  "const d=JSON.parse(process.argv[1]);"
                  "const m={};for(const[k,v]of Object.entries(d.matrix))m[k]=Object.fromEntries(Object.entries(v));"
                  "console.log(JSON.stringify(rankCandidates(d.reqs,m,d.th,d.flags)))") % json.dumps("file://" + os.path.abspath(RANK_JS))
        out = subprocess.run(["node", "--input-type=module", "-e", script, json.dumps({"reqs": reqs, "matrix": matrix, "th": TH, "flags": flags})],
                             capture_output=True, text=True, check=True).stdout
        js = json.loads(out)
        assert [r["candidate_id"] for r in js] == [r["candidate_id"] for r in py], trial
        for a, b in zip(js, py):
            assert abs(a["final_score"] - b["final_score"]) < 1e-12
            keys = ("met", "partial", "not_met", "not_verifiable", "musts_met", "musts", "rank", "tier", "tied")
            assert tuple(a[k] for k in keys) == tuple(b[k] for k in keys)
