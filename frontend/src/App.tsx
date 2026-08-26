import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/layout/Layout'
import Dashboard from './pages/Dashboard'
import Workbench from './pages/Workbench'
import KnowledgeBase from './pages/KnowledgeBase'
import ExecutionTrace from './pages/ExecutionTrace'
import ModelRegistry from './pages/ModelRegistry'
import Artifacts from './pages/Artifacts'
import NetworkMonitor from './pages/NetworkMonitor'
import System from './pages/System'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/workbench" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="workbench" element={<Workbench />} />
          <Route path="knowledge-base" element={<KnowledgeBase />} />
          <Route path="executions" element={<ExecutionTrace />} />
          <Route path="models" element={<ModelRegistry />} />
          <Route path="artifacts" element={<Artifacts />} />
          <Route path="network" element={<NetworkMonitor />} />
          <Route path="system" element={<System />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
