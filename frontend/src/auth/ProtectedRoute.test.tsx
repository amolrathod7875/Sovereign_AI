import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import type { ReactElement } from 'react'
import { AuthProvider } from '../auth/AuthProvider'
import { ProtectedRoute } from '../auth/ProtectedRoute'

function renderWithProviders(ui: ReactElement) {
  return render(
    <BrowserRouter>
      <AuthProvider>{ui}</AuthProvider>
    </BrowserRouter>
  )
}

describe('ProtectedRoute', () => {
  beforeEach(() => {
    window.sessionStorage.clear()
    vi.restoreAllMocks()
  })

  it('passes through in development mode', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ auth_mode: 'development', authentication_required: false, oidc: null }),
    } as any)

    renderWithProviders(
      <ProtectedRoute>
        <div data-testid="protected">Protected content</div>
      </ProtectedRoute>
    )

    await waitFor(() => {
      expect(screen.getByTestId('protected')).toBeDefined()
    })
  })

  it('redirects to login when unauthenticated in OIDC mode', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ auth_mode: 'oidc', authentication_required: true, oidc: { authority: 'http://localhost', client_id: 'test', scope: 'openid' } }),
    } as any)

    renderWithProviders(
      <ProtectedRoute>
        <div data-testid="protected">Protected content</div>
      </ProtectedRoute>
    )

    await waitFor(() => {
      expect(screen.queryByTestId('protected')).toBeNull()
    })
  })

  it('redirects to org-select when org selection required', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ auth_mode: 'oidc', authentication_required: true, oidc: { authority: 'http://localhost', client_id: 'test', scope: 'openid' } }),
    } as any)

    window.sessionStorage.setItem('sovereign_auth_session', JSON.stringify({
      access_token: 'token',
      expires_at: Date.now() + 3600000,
      user_id: 'u1',
      display_name: 'U',
    }))

    renderWithProviders(
      <ProtectedRoute>
        <div data-testid="protected">Protected content</div>
      </ProtectedRoute>
    )

    await waitFor(() => {
      expect(screen.queryByTestId('protected')).toBeNull()
    })
  })
})
