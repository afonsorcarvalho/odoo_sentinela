import { Routes, Route, useParams } from 'react-router'
import { OverviewPage } from './pages/OverviewPage'
import { SensorDetailPage } from './pages/SensorDetailPage'
import { AreaPage } from './pages/AreaPage'
import { LoginPage } from './pages/LoginPage'
import { AuthGuard } from './components/AuthGuard'

function SensorRoute() {
  const { code } = useParams<{ code: string }>()
  return <SensorDetailPage code={code!} />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<AuthGuard />}>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/area/:areaCode" element={<AreaPage />} />
        <Route path="/sensor/:code" element={<SensorRoute />} />
      </Route>
    </Routes>
  )
}
