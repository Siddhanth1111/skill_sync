import { useCallback, useEffect, useMemo, useState } from 'react'
import { useOutletContext, useSearchParams } from 'react-router-dom'
import { Play, RotateCcw, Save, ThumbsDown, ThumbsUp } from 'lucide-react'
import { api } from '../../api/index.js'
import { useApi, usePolling } from '../../api/hooks.js'
import { rankCandidates } from '../../lib/rank.js'
import { Button } from '../../components/ui/Button.jsx'
import { Badge, ImportanceBadge, isScoredKind } from '../../components/ui/Badge.jsx'
import { Card, CardHeader } from '../../components/ui/Card.jsx'
import { ScoreBar } from '../../components/ui/Charts.jsx'
import { Alert, EmptyState, ErrorState, Progress, SkeletonRows } from '../../components/ui/Feedback.jsx'
import { DataTable } from '../../components/ui/Layout.jsx'
import { Select } from '../../components/ui/Form.jsx'
import { useToast } from '../../components/ui/Toast.jsx'
import EvidenceSheet from '../../components/EvidenceSheet.jsx'

// Stages 7 to 11 in the UI. Scores come from the server once (the matrix). After that, moving a slider or changing an
// importance re-ranks here with the same formula as the backend (lib/rank.js), with no server call and no model call.
export default function RankingTab() {
  const { job, setJob, reloadJob } = useOutletContext()
  const toast = useToast()
  const [params, setParams] = useSearchParams()
  const matrix = useApi(() => api.matrix(job.id), [job.id])
  const server = useApi(() => api.ranking(job.id), [job.id])
  const run = useApi(() => api.scoringStatus(job.id), [job.id])
  const [reqs, setReqs] = useState([])
  const [minScore, setMinScore] = useState(0)
  const [starting, setStarting] = useState(false)
  const [saving, setSaving] = useState(false)

  const m = matrix.data
  useEffect(() => { if (m) setReqs(m.requirements.map((r) => ({ ...r }))) }, [m])

  const running = run.data?.status === 'running'
  // When a run stops running (including a run so fast it finished before the first poll), refresh everything it changed.
  const refreshAfterRun = async () => { await Promise.all([matrix.reload(true), server.reload(true)]); reloadJob() }
  usePolling(async () => {
    const r = await run.reload(true)
    if (r && r.status !== 'running') await refreshAfterRun()
  }, running, 1200)

  const start = async () => {
    setStarting(true)
    try {
      await api.startScoring(job.id)
      const r = await run.reload(true)
      if (r && r.status !== 'running') await refreshAfterRun()
    } catch (e) { toast.error(e.message) } finally { setStarting(false) }
  }

  const scored = useMemo(() => (m ? m.candidates.filter((c) => c.scored) : []), [m])
  const byId = useMemo(() => Object.fromEntries((m?.candidates || []).map((c) => [c.id, c])), [m])
  const ranked = useMemo(() => {
    if (!m) return []
    const matrixScores = Object.fromEntries(scored.map((c) => [c.id, Object.fromEntries(Object.entries(c.scores).map(([k, v]) => [k, v.score]))]))
    // requirements whose evidence could not be read are never penalised as missing
    const flags = Object.fromEntries(scored.map((c) => [c.id, Object.fromEntries(Object.entries(c.scores).filter(([, v]) => v.unverifiable).map(([k]) => [k, true]))]))
    return rankCandidates(reqs, matrixScores, m.thresholds, flags)
  }, [m, scored, reqs])
  const serverRank = useMemo(() => Object.fromEntries((server.data?.ranking || []).map((r) => [r.candidate_id, r])), [server.data])

  const edit = (id, field, value) => setReqs((rs) => rs.map((r) => (r.id === id ? { ...r, [field]: value } : r)))
  const dirty = m && reqs.some((r, i) => r.importance !== m.requirements[i].importance || Number(r.weight) !== Number(m.requirements[i].weight))
  const reset = () => setReqs(m.requirements.map((r) => ({ ...r })))
  const saveWeights = async () => {
    setSaving(true)
    try {
      setJob(await api.patchRequirements(job.id, reqs.map((r) => ({ id: r.id, importance: r.importance, weight: Number(r.weight) }))))
      await matrix.reload(true)
      toast.success('Weights saved as the default.')
    } catch (e) { toast.error(e.message) } finally { setSaving(false) }
  }

  const selectedId = Number(params.get('candidate')) || null
  const select = (id) => setParams(id ? { candidate: id } : {}, { replace: true })
  const sel = selectedId ? byId[selectedId] : null
  const rate = async (rating) => {
    try { await api.rate(selectedId, rating); await server.reload(true) } catch (e) { toast.error(e.message) }
  }

  if (matrix.error) return <ErrorState error={matrix.error} onRetry={matrix.reload} />
  const unscored = m ? m.candidates.length - scored.length : 0
  const shown = ranked.filter((r) => r.final_score * 100 >= minScore)
  const cfg = run.data?.config

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <div className="flex flex-wrap items-center gap-3 p-4">
          <Button leftIcon={<Play />} onClick={start} loading={starting} disabled={running || !m?.candidates.length}>{scored.length ? 'Re-run scoring' : 'Run scoring'}</Button>
          <div className="min-w-0 flex-1 text-sm text-muted-foreground">
            {running ? <div className="max-w-sm"><Progress value={run.data.done} max={run.data.total} label="Scoring progress" /><p className="mt-1 text-xs">Scoring {run.data.done} of {run.data.total} resumes. The first run loads the models and takes longer.</p></div>
              : cfg ? <span className="text-xs">Last run: pipeline {cfg.pipeline_version || 'v1'}, {cfg.embedder}, {cfg.reranker}, {cfg.nli}{cfg.blind_scoring ? ', identity details removed before scoring' : ''}.</span>
              : 'Scoring finds the best passage for each requirement in every parsed resume.'}
          </div>
        </div>
      </Card>
      {run.data?.status === 'failed' && <Alert color="destructive" title="The last scoring run failed">{run.data.error}</Alert>}
      {m?.stale && <Alert color="warning" title="Requirement wording changed since the last run">Re-run scoring to refresh the evidence.</Alert>}
      {unscored > 0 && !running && scored.length > 0 && <Alert color="warning">{unscored} parsed resume{unscored > 1 ? 's have' : ' has'} not been scored yet.</Alert>}

      {matrix.loading ? <Card><SkeletonRows /></Card>
        : !m.candidates.length ? <Card><EmptyState title="No parsed resumes yet">Upload resumes on the Resumes tab and wait for them to finish parsing.</EmptyState></Card>
        : !scored.length ? <Card><EmptyState title="Not scored yet">{m.candidates.length} resume{m.candidates.length > 1 ? 's are' : ' is'} ready. Run scoring to rank them.</EmptyState></Card>
        : (
          <div className="grid gap-4 xl:grid-cols-[20rem_1fr]">
            <Card className="self-start">
              <CardHeader title="Weights" description="Changes re-rank instantly in your browser." />
              <ul className="divide-y divide-border">
                {reqs.filter((r) => isScoredKind(r.meta?.kind)).map((r) => (
                  <li key={r.id} className="p-3">
                    <p className="text-sm">{r.text}</p>
                    <div className="mt-2 flex items-center gap-2">
                      <Select value={r.importance} onChange={(e) => edit(r.id, 'importance', e.target.value)} className="h-8 w-24" aria-label={`Importance of ${r.text}`}>
                        <option value="must">Must</option><option value="should">Should</option><option value="nice">Nice</option>
                      </Select>
                      <input type="range" min="0" max="5" step="0.5" value={r.weight} onChange={(e) => edit(r.id, 'weight', Number(e.target.value))}
                        className="h-2 flex-1 cursor-pointer accent-primary" aria-label={`Weight of ${r.text}`} />
                      <span className="w-6 text-right text-sm tabular-nums">{r.weight}</span>
                    </div>
                  </li>
                ))}
              </ul>
              <div className="flex flex-col gap-3 border-t border-border p-3">
                <label className="flex items-center gap-2 text-xs text-muted-foreground">Show scores of at least
                  <input type="range" min="0" max="100" step="5" value={minScore} onChange={(e) => setMinScore(Number(e.target.value))} className="h-2 flex-1 accent-primary" />
                  <span className="w-6 text-right tabular-nums text-foreground">{minScore}</span></label>
                <div className="flex gap-2">
                  <Button leftIcon={<Save />} disabled={!dirty} loading={saving} onClick={saveWeights}>Save as default</Button>
                  <Button variant="outline" leftIcon={<RotateCcw />} disabled={!dirty} onClick={reset}>Reset</Button>
                </div>
              </div>
            </Card>

            <Card>
              <CardHeader title={`Ranking (${shown.length})`} description="Candidates in the same tier are too close to order reliably. Click one to see the evidence behind every score." />
              <DataTable rows={shown} rowKey={(r) => r.candidate_id} selectedKey={selectedId} onRowClick={(r) => select(r.candidate_id)}
                columns={[
                  { key: 'rank', header: '#', width: '3rem', render: (r) => <span className="tabular-nums text-muted-foreground">{r.rank}</span> },
                  { key: 'tier', header: 'Tier', width: '4.5rem', render: (r) => <Badge color={r.tied ? 'warning' : 'neutral'} title={r.tied ? 'Within the tier band of another candidate: treat as a tie' : 'Clearly separated'}>{r.tied ? `Tier ${r.tier} ≈` : `Tier ${r.tier}`}</Badge> },
                  { key: 'who', header: 'Candidate', render: (r) => { const c = byId[r.candidate_id]; return <div className="min-w-0"><p className="truncate font-medium">{c.name || c.filename}</p><p className="truncate text-xs text-muted-foreground">{c.filename}</p></div> } },
                  { key: 'score', header: 'Score', width: '12rem', render: (r) => <ScoreBar value={r.final_score} /> },
                  { key: 'met', header: 'Met', width: '3.5rem', align: 'right', render: (r) => r.met },
                  { key: 'partial', header: 'Partial', width: '4rem', align: 'right', render: (r) => r.partial },
                  { key: 'miss', header: 'Missing', width: '4.5rem', align: 'right', render: (r) => r.not_met + (r.not_verifiable ? ` (+${r.not_verifiable}?)` : '') },
                  { key: 'must', header: 'Musts met', width: '5.5rem', align: 'right', render: (r) => `${r.musts_met} of ${r.musts}` },
                  { key: 'learn', header: 'Learned', width: '5rem', align: 'right', render: (r) => { const p = serverRank[r.candidate_id]?.learned_probability; return p == null ? <span className="text-muted-foreground">-</span> : `${(p * 100).toFixed(0)}%` } },
                  { key: 'rate', header: '', width: '2.5rem', render: (r) => { const t = serverRank[r.candidate_id]?.rating; return t === 'up' ? <ThumbsUp className="size-4 text-success" aria-label="Rated good fit" /> : t === 'down' ? <ThumbsDown className="size-4 text-destructive" aria-label="Rated not a fit" /> : null } },
                ]}
                empty={<EmptyState title="No candidates at this score">Lower the minimum score to see more.</EmptyState>} />
            </Card>
          </div>
        )}

      <EvidenceSheet candidate={sel?.scored ? sel : null} requirements={reqs} thresholds={m?.thresholds} hubMax={m?.hub_max_reuse}
        finalScore={ranked.find((r) => r.candidate_id === selectedId)?.final_score ?? 0} rankRow={ranked.find((r) => r.candidate_id === selectedId)}
        rating={serverRank[selectedId]?.rating} onRate={rate} onClose={() => select(null)} />
    </div>
  )
}
