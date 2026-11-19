import { useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { Brain, ThumbsDown, ThumbsUp } from 'lucide-react'
import { api } from '../../api/index.js'
import { useApi } from '../../api/hooks.js'
import { Button } from '../../components/ui/Button.jsx'
import { Badge } from '../../components/ui/Badge.jsx'
import { Card, CardHeader } from '../../components/ui/Card.jsx'
import { Alert, Progress } from '../../components/ui/Feedback.jsx'
import { DataTable, StatCard } from '../../components/ui/Layout.jsx'
import { useToast } from '../../components/ui/Toast.jsx'

const NAMES = { overall_score: 'overall score', mean_must: 'musts', mean_should: 'shoulds', mean_nice: 'nices', share_met: 'share met', share_partial: 'share partial', share_not_met: 'share not met' }

// Stage 13: ratings become an optional learned score, shown beside the rule-based score and never replacing it.
export default function LearningTab() {
  const { job } = useOutletContext()
  const toast = useToast()
  const model = useApi(() => api.model(job.id), [job.id])
  const ranking = useApi(() => api.ranking(job.id), [job.id])
  const [busy, setBusy] = useState(false)
  const m = model.data

  const train = async () => {
    setBusy(true)
    try { model.setData(await api.trainModel(job.id)); await ranking.reload(true); toast.success('Learned score trained.') }
    catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  if (model.loading || !m) return null
  const total = m.up + m.down
  const k = m.metrics

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader title="Learn from your ratings" description={`Rate candidates with the thumbs in the evidence panel. With at least ${m.min_ratings} ratings and ${m.min_each} of each kind, a model can learn what you prefer.`}
          actions={<Button leftIcon={<Brain />} loading={busy} disabled={!m.can_train} onClick={train}>{m.trained ? 'Retrain' : 'Train learned score'}</Button>} />
        <div className="flex flex-wrap items-center gap-4 p-4">
          <Badge color="success" dot><ThumbsUp className="size-3" /> {m.up} good fit</Badge>
          <Badge color="destructive" dot><ThumbsDown className="size-3" /> {m.down} not a fit</Badge>
          <div className="min-w-48 flex-1"><Progress value={Math.min(total, m.min_ratings)} max={m.min_ratings} label="Ratings collected" /></div>
          <span className="text-xs text-muted-foreground">{total} of {m.min_ratings} ratings{!m.can_train && total >= m.min_ratings ? `, need ${m.min_each} of each kind` : ''}</span>
        </div>
      </Card>

      {k && (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard label="Cross-validated AUC" value={k.cv_auc.toFixed(2)} hint="0.5 means no signal, 1.0 is perfect" />
            <StatCard label="Brier score" value={k.brier.toFixed(3)} hint="Lower is better" />
            <StatCard label="Calibration error" value={k.ece.toFixed(3)} hint="0 means probabilities match outcomes" />
          </div>
          <Alert>{m.note} Based on {k.n} ratings in {k.cv_folds}-fold cross-validation.</Alert>
          <Card>
            <CardHeader title="Rule score and learned score" description="The learned likelihood of a thumbs up is a second opinion. It never reorders the ranking." />
            <DataTable rows={ranking.data?.ranking || []} rowKey={(r) => r.candidate_id} columns={[
              { key: 'n', header: 'Candidate', render: (r) => r.name || r.filename },
              { key: 's', header: 'Rule score', width: '7rem', align: 'right', render: (r) => (r.final_score * 100).toFixed(1) },
              { key: 'l', header: 'Learned', width: '7rem', align: 'right', render: (r) => { const p = m.learned[r.candidate_id]; return p ? `${(p.probability * 100).toFixed(0)}%` : '-' } },
              { key: 'w', header: 'What drives it (SHAP, log-odds)', render: (r) => { const p = m.learned[r.candidate_id]; return <span className="text-xs text-muted-foreground">{p ? Object.entries(p.shap).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 3).map(([f, v]) => `${NAMES[f]} ${v >= 0 ? '+' : ''}${v.toFixed(2)}`).join(' · ') : ''}</span> } },
            ]} />
          </Card>
        </>
      )}
    </div>
  )
}
