import { Link } from 'react-router-dom'
import { Button } from '../components/ui/Button.jsx'
import { EmptyState } from '../components/ui/Feedback.jsx'

export default function NotFound() {
  return (
    <div className="flex h-full items-center justify-center bg-background">
      <EmptyState title="Page not found" action={<Link to="/"><Button variant="outline">Go to your home page</Button></Link>}>
        This address does not exist, or you do not have access to it.
      </EmptyState>
    </div>
  )
}
