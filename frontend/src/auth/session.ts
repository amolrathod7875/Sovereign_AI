import type { AuthSession } from './types'

const AUTH_SESSION_KEY = 'sovereign_auth_session'
const SELECTED_ORG_KEY = 'sovereign_selected_org_id'

function safeGetItem(key: string): string | null {
  try {
    return window.sessionStorage.getItem(key)
  } catch {
    return null
  }
}

function safeSetItem(key: string, value: string): void {
  try {
    window.sessionStorage.setItem(key, value)
  } catch {
    // sessionStorage may be unavailable in some contexts
  }
}

function safeRemoveItem(key: string): void {
  try {
    window.sessionStorage.removeItem(key)
  } catch {
    // ignore
  }
}

export function getStoredSession(): AuthSession | null {
  const raw = safeGetItem(AUTH_SESSION_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as AuthSession
  } catch {
    return null
  }
}

export function storeSession(session: AuthSession): void {
  safeSetItem(AUTH_SESSION_KEY, JSON.stringify(session))
}

export function clearSession(): void {
  safeRemoveItem(AUTH_SESSION_KEY)
}

export function getSelectedOrganizationId(): string | null {
  return safeGetItem(SELECTED_ORG_KEY)
}

export function setSelectedOrganizationId(orgId: string | null): void {
  if (orgId === null) {
    safeRemoveItem(SELECTED_ORG_KEY)
  } else {
    safeSetItem(SELECTED_ORG_KEY, orgId)
  }
}

export function clearAuthState(): void {
  clearSession()
  setSelectedOrganizationId(null)
}
