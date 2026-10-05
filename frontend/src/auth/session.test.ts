import { describe, it, expect, beforeEach } from 'vitest'
import type { AuthSession } from '../auth/types'
import { getStoredSession, storeSession, clearSession, getSelectedOrganizationId, setSelectedOrganizationId, clearAuthState } from '../auth/session'

describe('auth/session', () => {
  beforeEach(() => {
    window.sessionStorage.clear()
  })

  describe('getStoredSession / storeSession / clearSession', () => {
    it('returns null when no session stored', () => {
      expect(getStoredSession()).toBeNull()
    })

    it('stores and retrieves a session', () => {
      const session: AuthSession = {
        access_token: 'test-token',
        id_token: 'test-id-token',
        expires_at: Date.now() + 3600000,
        user_id: 'user-1',
        display_name: 'Test User',
        email: 'test@example.com',
      }
      storeSession(session)
      expect(getStoredSession()).toEqual(session)
    })

    it('clears session', () => {
      const session: AuthSession = {
        access_token: 'test-token',
        expires_at: Date.now() + 3600000,
        user_id: 'user-1',
        display_name: 'Test User',
      }
      storeSession(session)
      clearSession()
      expect(getStoredSession()).toBeNull()
    })

    it('handles corrupted sessionStorage gracefully', () => {
      window.sessionStorage.setItem('sovereign_auth_session', 'not-json')
      expect(getStoredSession()).toBeNull()
    })
  })

  describe('getSelectedOrganizationId / setSelectedOrganizationId', () => {
    it('returns null when no org selected', () => {
      expect(getSelectedOrganizationId()).toBeNull()
    })

    it('stores and retrieves org id', () => {
      setSelectedOrganizationId('org-123')
      expect(getSelectedOrganizationId()).toBe('org-123')
    })

    it('clears org id when set to null', () => {
      setSelectedOrganizationId('org-123')
      setSelectedOrganizationId(null)
      expect(getSelectedOrganizationId()).toBeNull()
    })
  })

  describe('clearAuthState', () => {
    it('clears both session and org', () => {
      const session: AuthSession = {
        access_token: 'test-token',
        expires_at: Date.now() + 3600000,
        user_id: 'user-1',
        display_name: 'Test User',
      }
      storeSession(session)
      setSelectedOrganizationId('org-123')
      clearAuthState()
      expect(getStoredSession()).toBeNull()
      expect(getSelectedOrganizationId()).toBeNull()
    })
  })
})
