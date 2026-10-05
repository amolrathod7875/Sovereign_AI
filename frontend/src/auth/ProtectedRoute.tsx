import { Navigate } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useAuth } from '../auth/AuthProvider'

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { authMode, configLoading, initializing, isAuthenticated, session, orgSelectionRequired } = useAuth()

  if (authMode === 'development') {
    return <>{children}</>
  }

  if (configLoading || initializing) {
    return (
      <div className="flex items-center justify-center h-screen bg-background-primary">
        <p className="text-sm text-text-secondary">Loading…</p>
      </div>
    )
  }

  if (!isAuthenticated) {
    if (session && orgSelectionRequired) {
      return <Navigate to="/org-select" replace />
    }
    return <Navigate to="/login" replace />
  }

  return <>{children}</>
}
