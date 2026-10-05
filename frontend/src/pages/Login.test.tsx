import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from '../auth/AuthProvider'
import Login from '../pages/Login'

function renderLogin() {
  return render(
    <BrowserRouter>
      <AuthProvider>
        <Login />
      </AuthProvider>
    </BrowserRouter>
  )
}

describe('Login', () => {
  beforeEach(() => {
    window.sessionStorage.clear()
    vi.restoreAllMocks()
  })

  it('returns null in development mode', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ auth_mode: 'development', authentication_required: false, oidc: null }),
    } as any)

    const { container } = renderLogin()
    await waitFor(() => {
      expect(container.innerHTML).toBe('')
    })
  })

  it('shows sign-in button in OIDC mode', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ auth_mode: 'oidc', authentication_required: true, oidc: { authority: 'http://localhost', client_id: 'test', scope: 'openid' } }),
    } as any)

    renderLogin()
    await waitFor(() => {
      expect(screen.getByText('Sign in')).toBeDefined()
    })
  })

  it('shows "Sign in with your organization account"', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ auth_mode: 'oidc', authentication_required: true, oidc: { authority: 'http://localhost', client_id: 'test', scope: 'openid' } }),
    } as any)

    renderLogin()
    await waitFor(() => {
      expect(screen.getByText('Sign in with your organization account')).toBeDefined()
    })
  })
})
