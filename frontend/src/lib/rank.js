// The ranking formula, identical to backend/app/services/ranking.py (a backend test runs both and compares).
//
// final = weighted mean of requirement scores, times `must_penalty` (0.9) for every 'must' requirement that is
// not met. Ties: more met musts first, then lower candidate id. Moving a slider only re-runs this function in the
// browser; no server call and no model call is needed because per-requirement scores are stored.

export function statusOf(score, th) {
  return score >= th.met ? 'met' : score >= th.partial ? 'partial' : 'not_met'
}

export function finalScore(items, th) {
  // items: [{importance, weight, score}]
  const total = items.reduce((a, i) => a + i.weight, 0)
  if (total <= 0) return 0
  let value = items.reduce((a, i) => a + i.weight * i.score, 0) / total
  for (const i of items) {
    if (i.importance === 'must' && statusOf(i.score, th) === 'not_met') value *= th.must_penalty
  }
  return value
}

// requirements: [{id, importance, weight}]; matrix: {candidateId: {requirementId: score}}
export function rankCandidates(requirements, matrix, th) {
  const rows = Object.entries(matrix).map(([cid, scores]) => {
    const items = []
    const counts = { met: 0, partial: 0, not_met: 0 }
    let mustsMet = 0
    for (const r of requirements) {
      const s = scores[r.id]
      if (s === undefined) continue
      items.push({ importance: r.importance, weight: Number(r.weight), score: s })
      const st = statusOf(s, th)
      counts[st] += 1
      if (r.importance === 'must' && st === 'met') mustsMet += 1
    }
    return { candidate_id: Number(cid), final_score: finalScore(items, th), ...counts, musts_met: mustsMet }
  })
  rows.sort((a, b) => b.final_score - a.final_score || b.musts_met - a.musts_met || a.candidate_id - b.candidate_id)
  rows.forEach((r, i) => { r.rank = i + 1 })
  return rows
}

// Stage 12: points a candidate would gain by fully meeting each requirement.
export function gaps(requirements, scores) {
  const present = requirements.filter((r) => scores[r.id] !== undefined)
  const total = present.reduce((a, r) => a + Number(r.weight), 0) || 1
  return present
    .filter((r) => scores[r.id] < 1)
    .map((r) => ({ requirement_id: r.id, points_gain: (100 * Number(r.weight) * (1 - scores[r.id])) / total }))
    .sort((a, b) => b.points_gain - a.points_gain)
}
