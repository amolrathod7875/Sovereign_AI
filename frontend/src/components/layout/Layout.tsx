import { useEffect } from 'react'
import { Outlet, Link, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  MessageSquare,
  Database,
  ListChecks,
  Cpu,
  FileOutput,
  Network,
  Settings,
  Shield,
  ShieldCheck,
  LogOut,
  User,
} from 'lucide-react'
import clsx from 'clsx'
import { useSystemStore, summarizeModels } from '../../lib/store'
import { useAuth } from '../../auth/AuthProvider'

const navItems = [
  { path: '/workbench', label: 'AI Workbench', icon: MessageSquare },
  { path: '/judge', label: 'Judge Mode', icon: ShieldCheck },
  { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/knowledge-base', label: 'Knowledge Base', icon: Database },
  { path: '/executions', label: 'Executions', icon: ListChecks },
  { path: '/models', label: 'Models', icon: Cpu },
  { path: '/artifacts', label: 'Artifacts', icon: FileOutput },
  { path: '/network', label: 'Network Monitor', icon: Network },
  { path: '/system', label: 'System', icon: Settings },
]

export default function Layout() {
  const location = useLocation()
  const status = useSystemStore((s) => s.status)
  const models = useSystemStore((s) => s.models)
  const error = useSystemStore((s) => s.error)
  const startPolling = useSystemStore((s) => s.startPolling)
  const { authMode, authMe, logout, selectedOrgId, memberships, switchOrganization } = useAuth()

  useEffect(() => {
    const stop = startPolling(15000)
    return stop
  }, [startPolling])

  const modelSummary = summarizeModels(models, status?.components)
  const externalCalls = status?.external_api_calls ?? 0
  const backendUp = !error && status !== null
  const localLabel = backendUp ? 'LOCAL ONLY' : 'BACKEND OFFLINE'
  const localTone = backendUp ? 'bg-accent-sovereign' : 'bg-accent-danger'

  const currentMembership = memberships.find((m) => m.organization_id === selectedOrgId)
  const displayName = authMe?.display_name || authMode === 'oidc' ? 'User' : undefined

  return (
    <div className="flex h-screen bg-background-primary">
      {/* Sidebar */}
      <aside className="w-56 bg-background-secondary border-r border-border flex flex-col">
        {/* Logo */}
        <div className="p-4 border-b border-border">
          <div className="flex items-center gap-2">
            <Shield className="w-6 h-6 text-accent-sovereign" />
            <div>
              <h1 className="text-sm font-bold text-text-primary">SOVEREIGN AI</h1>
              <p className="text-xs text-text-secondary">PS 26117</p>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-2 space-y-1">
          {navItems.map(({ path, label, icon: Icon }) => (
            <Link
              key={path}
              to={path}
              className={clsx(
                'flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors',
                location.pathname === path
                  ? 'bg-accent-primary/10 text-accent-primary'
                  : 'text-text-secondary hover:bg-background-tertiary hover:text-text-primary'
              )}
            >
              <Icon className="w-4 h-4" />
              {label}
            </Link>
          ))}
        </nav>

        {/* Sovereignty Badge — driven by real backend status */}
        <div className="p-4 border-t border-border">
          <div className={clsx('flex items-center gap-2', backendUp ? 'text-accent-sovereign' : 'text-accent-danger')}>
            <div className={clsx('w-2 h-2 rounded-full animate-pulse', localTone)} />
            <span className="text-xs font-medium">{localLabel}</span>
          </div>
          {backendUp && (
            <p className="text-[10px] text-text-secondary mt-1">
              External calls: <span className="font-mono text-text-primary">{externalCalls}</span>
            </p>
          )}
        </div>

        {/* User identity */}
        {authMode === 'oidc' && displayName && (
          <div className="p-4 border-t border-border space-y-2">
            <div className="flex items-center gap-2 text-xs">
              <User className="w-3 h-3 text-text-secondary" />
              <span className="text-text-primary truncate">{displayName}</span>
            </div>
            {currentMembership && (
              <div className="text-[10px] text-text-secondary">
                <span className="truncate block">{currentMembership.organization_name}</span>
                <span className="capitalize">{currentMembership.role}</span>
              </div>
            )}
            {memberships.length > 1 && (
              <select
                value={selectedOrgId ?? ''}
                onChange={(e) => {
                  if (e.target.value) switchOrganization(e.target.value)
                }}
                className="w-full bg-background-tertiary border border-border rounded px-1 py-0.5 text-[10px] text-text-primary"
              >
                {memberships.map((m) => (
                  <option key={m.organization_id} value={m.organization_id}>
                    {m.organization_name} ({m.role})
                  </option>
                ))}
              </select>
            )}
            <button
              type="button"
              onClick={logout}
              className="flex items-center gap-1 text-[10px] text-text-secondary hover:text-text-primary"
            >
              <LogOut className="w-3 h-3" /> Sign out
            </button>
          </div>
        )}
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="h-14 bg-background-secondary border-b border-border flex items-center justify-between px-6">
          <h2 className="text-sm font-semibold text-text-primary">
            {navItems.find(item => item.path === location.pathname)?.label || 'Sovereign AI'}
          </h2>
          <div className="flex items-center gap-4">
            <div className={clsx('flex items-center gap-2', backendUp ? 'text-accent-sovereign' : 'text-accent-danger')}>
              <div className={clsx('w-2 h-2 rounded-full animate-pulse', localTone)} />
              <span className="text-xs font-medium">{localLabel}</span>
            </div>
            {backendUp && (
              <div className="flex items-center gap-3 text-xs text-text-secondary">
                <span>
                  Models:{' '}
                  <span className={modelSummary.available === modelSummary.total ? 'text-accent-success' : 'text-accent-warning'}>
                    {modelSummary.available}/{modelSummary.total}
                  </span>
                </span>
                <span>
                  Network:{' '}
                  <span className={externalCalls === 0 ? 'text-accent-success' : 'text-accent-danger'}>
                    {externalCalls} external
                  </span>
                </span>
              </div>
            )}
          </div>
        </header>

        {/* Page Content */}
        <div className="flex-1 overflow-auto p-6">
          <Outlet />
        </div>

        {/* Status Bar — real component states from /api/system/status */}
        <footer className="h-8 bg-background-secondary border-t border-border flex items-center px-4 text-xs text-text-secondary">
          <div className="flex items-center gap-4 overflow-x-auto">
            <span>
              GPU:{' '}
              {status?.gpu?.name ?? (status ? 'none detected' : '--')}
              {status?.gpu?.memory_used_gb != null && ` (${status.gpu.memory_used_gb}/${status.gpu.memory_total_gb} GB)`}
            </span>
            {(status?.components ?? []).map((c) => (
              <span key={c.id} className="flex items-center gap-1" title={c.detail}>
                <span
                  className={
                    'w-1.5 h-1.5 rounded-full ' +
                    (c.status === 'ONLINE'
                      ? 'bg-accent-success'
                      : c.status === 'OFFLINE'
                        ? 'bg-accent-warning'
                        : c.status === 'UNAVAILABLE'
                          ? 'bg-accent-danger'
                          : 'bg-text-secondary')
                  }
                />
                {c.name}
              </span>
            ))}
          </div>
        </footer>
      </main>
    </div>
  )
}
