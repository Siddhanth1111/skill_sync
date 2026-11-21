// The ranking formula, identical to backend/app/services/ranking.py (a backend test runs both and compares).
//
// final = weighted mean of requirement scores, times `must_penalty` (0.9) for every 'must' requirement that is
// confidently not met. A requirement whose evidence could not be read ("not verifiable") is never penalised.
// Requirements with weight 0 (soft skills, duties) are listed but not scored, so they never count.
// Ties: more met musts first, then lower candidate id. Candidates within `tier_band` of their tier's leader share
// a tier, so a small difference never decides a ranking on its own.
// Moving a slider only re-runs this function in the browser; no server call and no model call is needed because
// per-requirement scores are stored.

export function statusOf(score, th) {
  return score >= th.met ? 'met' : score >= th.partial ? 'partial' : 'not_met'
}

export function finalScore(items, th) {
  // items: [{importance, weight, score, unverifiable?}]
  const total = items.reduce((a, i) => a + i.weight, 0)
  if (total <= 0) return 0
  let value = items.reduce((a, i) => a + i.weight * i.score, 0) / total
  for (const i of items) {
    if (i.importance === 'must' && i.weight > 0 && !i.unverifiable && statusOf(i.score, th) === 'not_met') {
      value *= th.must_penalty
    }
  }
  return value
}

// requirements: [{id, importance, weight}]; matrix: {candidateId: {requirementId: score}};
// flags: {candidateId: {requirementId: true}} for requirements that could not be verified
export function rankCandidates(requirements, matrix, th, flags = {}) {
  const rows = Object.entries(matrix).map(([cid, scores]) => {
    const cf = flags[cid] || {}
    const items = []
    const counts = { met: 0, partial: 0, not_met: 0, not_verifiable: 0 }
    let mustsMet = 0
    let musts = 0
    for (const r of requirements) {
      const s = scores[r.id]
      if (s === undefined || Number(r.weight) <= 0) continue
      const unverifiable = Boolean(cf[r.id])
      items.push({ importance: r.importance, weight: Number(r.weight), score: s, unverifiable })
      const st = unverifiable ? 'not_verifiable' : statusOf(s, th)
      counts[st] += 1
      if (r.importance === 'must') {
        musts += 1
        if (st === 'met') mustsMet += 1
      }
    }
    return { candidate_id: Number(cid), final_score: finalScore(items, th), ...counts, musts_met: mustsMet, musts }
  })
  rows.sort((a, b) => b.final_score - a.final_score || b.musts_met - a.musts_met || a.candidate_id - b.candidate_id)
  rows.forEach((r, i) => { r.rank = i + 1 })
  assignTiers(rows, th.tier_band ?? 0.02)
  return rows
}

// Rows must already be sorted best first.
export function assignTiers(rows, band) {
  let tier = 0
  let leader = null
  for (const r of rows) {
    if (leader === null || leader - r.final_score >= band) {
      tier += 1
      leader = r.final_score
    }
    r.tier = tier
  }
  const sizes = {}
  rows.forEach((r) => { sizes[r.tier] = (sizes[r.tier] || 0) + 1 })
  rows.forEach((r) => { r.tied = sizes[r.tier] > 1 })
}

// Stage 12: points a candidate would gain by fully meeting each requirement. Weight-0 requirements never appear.
export function gaps(requirements, scores) {
  const present = requirements.filter((r) => scores[r.id] !== undefined && Number(r.weight) > 0)
  const total = present.reduce((a, r) => a + Number(r.weight), 0) || 1
  return present
    .filter((r) => scores[r.id] < 1)
    .map((r) => ({ requirement_id: r.id, points_gain: (100 * Number(r.weight) * (1 - scores[r.id])) / total }))
    .sort((a, b) => b.points_gain - a.points_gain)
}
