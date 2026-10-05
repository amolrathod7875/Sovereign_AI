import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './auth/AuthProvider'
import { ProtectedRoute } from './auth/ProtectedRoute'
import Layout from './components/layout/Layout'
import Dashboard from './pages/Dashboard'
import Workbench from './pages/Workbench'
import KnowledgeBase from './pages/KnowledgeBase'
import ExecutionTrace from './pages/ExecutionTrace'
import ModelRegistry from './pages/ModelRegistry'
import Artifacts from './pages/Artifacts'
import NetworkMonitor from './pages/NetworkMonitor'
import System from './pages/System'
import JudgeMode from './pages/JudgeMode'
import Login from './pages/Login'
import AuthCallback from './pages/AuthCallback'
import OrganizationSelector from './components/auth/OrganizationSelector'

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/auth/callback" element={<AuthCallback />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <Layout />
              </ProtectedRoute>
            }
          >
            <Route index element={<Navigate to="/workbench" replace />} />
            <Route path="dashboard" element={<Dashboard />} />
            <Route path="workbench" element={<Workbench />} />
            <Route path="knowledge-base" element={<KnowledgeBase />} />
            <Route path="executions" element={<ExecutionTrace />} />
            <Route path="models" element={<ModelRegistry />} />
            <Route path="artifacts" element={<Artifacts />} />
            <Route path="network" element={<NetworkMonitor />} />
            <Route path="system" element={<System />} />
            <Route path="judge" element={<JudgeMode />} />
          </Route>
          <Route path="/org-select" element={<OrganizationSelector />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
