import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthProvider'

export default function AuthCallback() {
  const { handleCallback } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    let cancelled = false
    handleCallback().then(() => {
      if (!cancelled) {
        navigate('/workbench', { replace: true })
      }
    })
    return () => {
      cancelled = true
    }
  }, [handleCallback, navigate])

  return (
    <div className="flex items-center justify-center min-h-screen bg-background-primary">
      <p className="text-sm text-text-secondary">Completing sign-in…</p>
    </div>
  )
}
