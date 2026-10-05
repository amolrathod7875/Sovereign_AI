import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from '../auth/AuthProvider'
import AuthCallback from '../pages/AuthCallback'

describe('AuthCallback', () => {
  beforeEach(() => {
    window.sessionStorage.clear()
    vi.restoreAllMocks()
  })

  it('shows completing sign-in message', async () => {
    render(
      <BrowserRouter>
        <AuthProvider>
          <AuthCallback />
        </AuthProvider>
      </BrowserRouter>
    )

    await waitFor(() => {
      expect(screen.getByText('Completing sign-in…')).toBeDefined()
    })
  })
})
