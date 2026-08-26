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
} from 'lucide-react'
import clsx from 'clsx'

const navItems = [
  { path: '/workbench', label: 'AI Workbench', icon: MessageSquare },
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

        {/* Sovereignty Badge */}
        <div className="p-4 border-t border-border">
          <div className="flex items-center gap-2 text-accent-sovereign">
            <div className="w-2 h-2 rounded-full bg-accent-sovereign animate-pulse" />
            <span className="text-xs font-medium">LOCAL / AIR-GAPPED</span>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="h-14 bg-background-secondary border-b border-border flex items-center justify-between px-6">
          <h2 className="text-sm font-semibold text-text-primary">
            {navItems.find(item => item.path === location.pathname)?.label || 'Sovereign AI'}
          </h2>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-accent-sovereign">
              <div className="w-2 h-2 rounded-full bg-accent-sovereign animate-pulse" />
              <span className="text-xs font-medium">LOCAL ONLY</span>
            </div>
          </div>
        </header>

        {/* Page Content */}
        <div className="flex-1 overflow-auto p-6">
          <Outlet />
        </div>

        {/* Status Bar */}
        <footer className="h-8 bg-background-secondary border-t border-border flex items-center px-4 text-xs text-text-secondary">
          <div className="flex items-center gap-6">
            <span>GPU: --</span>
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-accent-sovereign" />
              vLLM
            </span>
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-accent-sovereign" />
              Qdrant
            </span>
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-accent-sovereign" />
              PostgreSQL
            </span>
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-accent-sovereign" />
              Piston
            </span>
          </div>
        </footer>
      </main>
    </div>
  )
}
