import { Routes, Route, Navigate, useParams } from 'react-router'
import { DashboardPage } from './pages/DashboardPage'
import { LoginPage } from './pages/LoginPage'
import { AuthGuard } from './components/AuthGuard'

function AreaRedirect() {
  const { areaCode } = useParams<{ areaCode: string }>()
  return <Navigate to={`/?area=${areaCode}`} replace />
}

function SensorRedirect() {
  const { code } = useParams<{ code: string }>()
  return <Navigate to={`/?sensor=${code}`} replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<AuthGuard />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/area/:areaCode" element={<AreaRedirect />} />
        <Route path="/sensor/:code" element={<SensorRedirect />} />
      </Route>
    </Routes>
  )
}
