import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { homeFor, useAuth } from './AuthContext.jsx'
import { Spinner } from '../components/ui/Feedback.jsx'

// Gate a group of routes: must be signed in, and (optionally) have one of the allowed roles.
export default function ProtectedRoute({ roles }) {
  const { user, booting } = useAuth()
  const location = useLocation()
  if (booting) return <div className="flex h-full items-center justify-center"><Spinner className="size-6" /></div>
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  if (roles && !roles.includes(user.role)) return <Navigate to={homeFor(user.role)} replace />
  return <Outlet />
}

// Public pages (login, register): signed-in users go straight to their home.
export function PublicOnly() {
  const { user, booting } = useAuth()
  if (booting) return <div className="flex h-full items-center justify-center"><Spinner className="size-6" /></div>
  if (user) return <Navigate to={homeFor(user.role)} replace />
  return <Outlet />
}
