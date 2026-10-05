import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from '@/auth/AuthProvider'
import OrganizationSelector from './OrganizationSelector'

describe('OrganizationSelector', () => {
  beforeEach(() => {
    window.sessionStorage.clear()
    vi.restoreAllMocks()
  })

  it('shows select an organization heading', async () => {
    let callCount = 0
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: () => {
        callCount += 1
        if (callCount === 1) {
          return Promise.resolve({ auth_mode: 'oidc', authentication_required: true, oidc: { authority: 'http://localhost', client_id: 'test', scope: 'openid' } })
        }
        return Promise.resolve({
          user: { user_id: 'u1', display_name: 'Test User', email: 'u@test' },
          memberships: [
            { organization_id: 'org-1', organization_name: 'Org 1', role: 'member' },
            { organization_id: 'org-2', organization_name: 'Org 2', role: 'admin' },
          ],
        })
      },
    } as any)

    window.sessionStorage.setItem('sovereign_auth_session', JSON.stringify({
      access_token: 'token',
      expires_at: Date.now() + 3600000,
      user_id: 'u1',
      display_name: 'Test User',
    }))

    render(
      <BrowserRouter>
        <AuthProvider>
          <OrganizationSelector />
        </AuthProvider>
      </BrowserRouter>
    )

    await waitFor(() => {
      expect(screen.getByText((content) => content.includes('select an organization'))).toBeDefined()
    }, { timeout: 5000 })
  })
})
