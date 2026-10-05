import { useEffect } from 'react'
import { Shield } from 'lucide-react'
import { useAuth } from '../auth/AuthProvider'

export default function Login() {
  const { authMode, login, configLoading, session, orgSelectionRequired } = useAuth()

  useEffect(() => {
    if (authMode === 'development') {
      window.location.href = '/'
    }
  }, [authMode])

  if (authMode === 'development' || configLoading) {
    return null
  }

  // If user has a session but needs org selection, redirect to org selector
  if (session && orgSelectionRequired) {
    window.location.href = '/org-select'
    return null
  }

  return (
    <div className="flex items-center justify-center min-h-screen bg-background-primary">
      <div className="w-full max-w-sm rounded-lg border border-border bg-background-secondary p-8 text-center">
        <div className="flex justify-center mb-4">
          <Shield className="w-10 h-10 text-accent-sovereign" />
        </div>
        <h1 className="text-lg font-bold text-text-primary mb-1">SOVEREIGN AI</h1>
        <p className="text-xs text-text-secondary mb-6">Sign in with your organization account</p>
        <button
          type="button"
          onClick={login}
          className="w-full rounded-md bg-accent-primary px-4 py-2 text-sm font-medium text-white hover:bg-accent-primary/90"
        >
          Sign in
        </button>
      </div>
    </div>
  )
}
