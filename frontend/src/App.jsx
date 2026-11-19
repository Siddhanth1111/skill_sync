import { Navigate, Route, Routes } from 'react-router-dom'
import { homeFor, useAuth } from './auth/AuthContext.jsx'
import ProtectedRoute, { PublicOnly } from './auth/ProtectedRoute.jsx'
import AppShell from './components/AppShell.jsx'
import Login from './pages/auth/Login.jsx'
import Register from './pages/auth/Register.jsx'
import Settings from './pages/Settings.jsx'
import NotFound from './pages/NotFound.jsx'
import RecruiterDashboard from './pages/recruiter/Dashboard.jsx'
import Jobs from './pages/recruiter/Jobs.jsx'
import NewJob from './pages/recruiter/NewJob.jsx'
import JobLayout from './pages/recruiter/JobLayout.jsx'
import RequirementsTab from './pages/recruiter/RequirementsTab.jsx'
import ResumesTab from './pages/recruiter/ResumesTab.jsx'
import RankingTab from './pages/recruiter/RankingTab.jsx'
import FairnessTab from './pages/recruiter/FairnessTab.jsx'
import LearningTab from './pages/recruiter/LearningTab.jsx'
import JobAnalyticsTab from './pages/recruiter/JobAnalyticsTab.jsx'
import SearchPage from './pages/recruiter/SearchPage.jsx'
import AnalyticsOverview from './pages/recruiter/AnalyticsOverview.jsx'
import StudentOverview from './pages/student/Overview.jsx'
import StudentResume from './pages/student/Resume.jsx'
import StudentJobs from './pages/student/Jobs.jsx'
import StudentMatches from './pages/student/Matches.jsx'
import StudentRoadmap from './pages/student/RoadmapPage.jsx'
import AdminOverview from './pages/admin/Overview.jsx'
import AdminUsers from './pages/admin/Users.jsx'
import AdminActivity from './pages/admin/Activity.jsx'

function RootRedirect() {
  const { user, booting } = useAuth()
  if (booting) return null
  return <Navigate to={user ? homeFor(user.role) : '/login'} replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<RootRedirect />} />
      <Route element={<PublicOnly />}>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
      </Route>

      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route path="/settings" element={<Settings />} />

          <Route path="/recruiter" element={<ProtectedRoute roles={['recruiter']} />}>
            <Route index element={<RecruiterDashboard />} />
            <Route path="jobs" element={<Jobs />} />
            <Route path="jobs/new" element={<NewJob />} />
            <Route path="jobs/:jobId" element={<JobLayout />}>
              <Route index element={<RequirementsTab />} />
              <Route path="resumes" element={<ResumesTab />} />
              <Route path="ranking" element={<RankingTab />} />
              <Route path="fairness" element={<FairnessTab />} />
              <Route path="learning" element={<LearningTab />} />
              <Route path="analytics" element={<JobAnalyticsTab />} />
            </Route>
            <Route path="search" element={<SearchPage />} />
            <Route path="analytics" element={<AnalyticsOverview />} />
          </Route>

          <Route path="/student" element={<ProtectedRoute roles={['student']} />}>
            <Route index element={<StudentOverview />} />
            <Route path="resume" element={<StudentResume />} />
            <Route path="jobs" element={<StudentJobs />} />
            <Route path="matches" element={<StudentMatches />} />
            <Route path="matches/:jobId" element={<StudentRoadmap />} />
          </Route>

          <Route path="/admin" element={<ProtectedRoute roles={['admin']} />}>
            <Route index element={<AdminOverview />} />
            <Route path="users" element={<AdminUsers />} />
            <Route path="activity" element={<AdminActivity />} />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}
