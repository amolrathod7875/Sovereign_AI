import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from 'react'
import type { AuthConfig, AuthBootstrapResponse, AuthMeResponse, AuthSession } from './types'
import { getStoredSession, storeSession, clearSession, getSelectedOrganizationId, setSelectedOrganizationId, clearAuthState } from './session'
import { createUserManager, signinRedirect, signinRedirectCallback, signout, getUser } from './oidc'

// ---------------------------------------------------------------------------
// Context shape
// ---------------------------------------------------------------------------

interface AuthContextValue {
  // Config
  authMode: 'development' | 'oidc'
  authConfig: AuthConfig | null
  configLoading: boolean
  configError: string | null

  // OIDC session
  session: AuthSession | null
  isAuthenticated: boolean
  initializing: boolean

  // Organization
  selectedOrgId: string | null
  memberships: AuthBootstrapResponse['memberships']
  orgSelectionRequired: boolean
  userInfo: AuthBootstrapResponse['user'] | null
  authMe: AuthMeResponse | null

  // Actions
  refreshConfig: () => Promise<void>
  login: () => Promise<void>
  handleCallback: () => Promise<void>
  logout: () => Promise<void>
  selectOrganization: (orgId: string) => Promise<void>
  switchOrganization: (orgId: string) => Promise<void>
  refreshAuthMe: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [authConfig, setAuthConfig] = useState<AuthConfig | null>(null)
  const [configLoading, setConfigLoading] = useState(true)
  const [configError, setConfigError] = useState<string | null>(null)

  const [session, setSession] = useState<AuthSession | null>(null)
  const [initializing, setInitializing] = useState(true)

  const [memberships, setMemberships] = useState<AuthBootstrapResponse['memberships']>([])
  const [userInfo, setUserInfo] = useState<AuthBootstrapResponse['user'] | null>(null)
  const [authMe, setAuthMe] = useState<AuthMeResponse | null>(null)

  const authMode = authConfig?.auth_mode ?? 'development'

  const configLoadedRef = useRef(false)

  // -------------------------------------------------------------------------
  // Config
  // -------------------------------------------------------------------------

  const refreshConfig = useCallback(async () => {
    if (configLoadedRef.current) return
    setConfigLoading(true)
    setConfigError(null)
    try {
      const res = await fetch('/api/auth/config')
      if (!res.ok) {
        throw new Error(`Config fetch failed: ${res.status}`)
      }
      const data = (await res.json()) as AuthConfig
      setAuthConfig(data)
    } catch (err) {
      setConfigError(err instanceof Error ? err.message : 'Failed to load auth config')
    } finally {
      setConfigLoading(false)
      configLoadedRef.current = true
    }
  }, [])

  // -------------------------------------------------------------------------
  // OIDC helpers
  // -------------------------------------------------------------------------

  const getOidcUserManager = useCallback(() => {
    if (!authConfig?.oidc) return null
    return createUserManager(authConfig)
  }, [authConfig])

  // -------------------------------------------------------------------------
  // Auth me helper (defined before bootstrap because bootstrap calls it)
  // -------------------------------------------------------------------------

  const refreshAuthMe = useCallback(async (accessToken: string, orgId: string) => {
    try {
      const res = await fetch('/api/auth/me', {
        headers: {
          Authorization: `Bearer ${accessToken}`,
          'X-Sovereign-Organization': orgId,
        },
      })
      if (res.ok) {
        const data = (await res.json()) as AuthMeResponse
        setAuthMe(data)
      }
    } catch {
      // ignore
    }
  }, [])

  // -------------------------------------------------------------------------
  // Bootstrap + org selection
  // -------------------------------------------------------------------------

  const runBootstrapAndOrgSelect = useCallback(async (accessToken: string) => {
    try {
      const res = await fetch('/api/auth/bootstrap', {
        headers: { Authorization: `Bearer ${accessToken}` },
      })
      if (!res.ok) {
        if (res.status === 401 || res.status === 403) {
          clearAuthState()
          setSession(null)
          setMemberships([])
          setUserInfo(null)
          setAuthMe(null)
          setSelectedOrganizationId(null)
        }
        return
      }
      const data = (await res.json()) as AuthBootstrapResponse
      setUserInfo(data.user)
      setMemberships(data.memberships)

      const storedOrg = getSelectedOrganizationId()
      const validOrg = data.memberships.find((m) => m.organization_id === storedOrg)

      if (data.memberships.length === 1) {
        const orgId = data.memberships[0].organization_id
        setSelectedOrganizationId(orgId)
        await refreshAuthMe(accessToken, orgId)
      } else if (validOrg) {
        await refreshAuthMe(accessToken, validOrg.organization_id)
      } else if (data.memberships.length > 1 && !storedOrg) {
        // multi-org, need selection
        setSelectedOrganizationId(null)
        setAuthMe(null)
      }
    } catch {
      // ignore bootstrap errors
    } finally {
      setInitializing(false)
    }
  }, [refreshAuthMe])

  // -------------------------------------------------------------------------
  // Session restore
  // -------------------------------------------------------------------------

  const restoreSession = useCallback(async () => {
    if (authMode !== 'oidc' || !authConfig?.oidc) {
      setInitializing(false)
      return
    }

    const userManager = getOidcUserManager()
    if (!userManager) {
      setInitializing(false)
      return
    }

    try {
      const stored = getStoredSession()
      if (stored && stored.expires_at > Date.now()) {
        // Try to verify with backend
        setSession(stored)
        await runBootstrapAndOrgSelect(stored.access_token)
        return
      }
    } catch {
      // ignore restore failures
    }

    // Try silent renew via library
    try {
      const user = await getUser(userManager)
      if (user?.access_token) {
        const newSession: AuthSession = {
          access_token: user.access_token,
          id_token: user.id_token,
          expires_at: (user.expires_at ?? 0) * 1000,
          user_id: user.profile?.sub ?? '',
          display_name: user.profile?.name ?? '',
          email: user.profile?.email,
        }
        if (newSession.expires_at <= Date.now()) {
          await userManager.removeUser()
          clearSession()
          setSession(null)
        } else {
          setSession(newSession)
          storeSession(newSession)
          await runBootstrapAndOrgSelect(newSession.access_token)
          return
        }
      }
    } catch {
      // silent renew failed
    }

    setSession(null)
    setInitializing(false)
  }, [authMode, authConfig, getOidcUserManager, runBootstrapAndOrgSelect])

  // -------------------------------------------------------------------------
  // Actions
  // -------------------------------------------------------------------------

  const selectOrganization = useCallback(async (orgId: string) => {
    if (!session?.access_token) return
    setSelectedOrganizationId(orgId)
    await refreshAuthMe(session.access_token, orgId)
  }, [session, refreshAuthMe])

  const switchOrganization = useCallback(async (orgId: string) => {
    if (!session?.access_token) return
    setSelectedOrganizationId(orgId)
    setAuthMe(null)
    setMemberships([])
    setUserInfo(null)
    await refreshAuthMe(session.access_token, orgId)
    // Reload page data after switch
    window.location.reload()
  }, [session, refreshAuthMe])

  const login = useCallback(async () => {
    const userManager = getOidcUserManager()
    if (!userManager) return
    await signinRedirect(userManager)
  }, [getOidcUserManager])

  const handleCallback = useCallback(async () => {
    const userManager = getOidcUserManager()
    if (!userManager) return
    try {
      const user = await signinRedirectCallback(userManager)
      if (user?.access_token) {
        const newSession: AuthSession = {
          access_token: user.access_token,
          id_token: user.id_token,
          expires_at: (user.expires_at ?? 0) * 1000,
          user_id: user.profile?.sub ?? '',
          display_name: user.profile?.name ?? '',
          email: user.profile?.email,
        }
        setSession(newSession)
        storeSession(newSession)
        // Clean up URL
        window.history.replaceState({}, '', window.location.pathname)
        await runBootstrapAndOrgSelect(newSession.access_token)
      }
    } catch (err) {
      console.error('Auth callback failed:', err)
      clearAuthState()
      setSession(null)
      setInitializing(false)
    }
  }, [getOidcUserManager, runBootstrapAndOrgSelect])

  const logout = useCallback(async () => {
    const userManager = getOidcUserManager()
    try {
      if (userManager) {
        await signout(userManager)
      }
    } catch {
      // ignore logout errors
    } finally {
      clearAuthState()
      setSession(null)
      setMemberships([])
      setUserInfo(null)
      setAuthMe(null)
      setSelectedOrganizationId(null)
    }
  }, [getOidcUserManager])

  // -------------------------------------------------------------------------
  // Init
  // -------------------------------------------------------------------------

  const restoreSessionRef = useRef(restoreSession)
  restoreSessionRef.current = restoreSession

  useEffect(() => {
    let cancelled = false
    refreshConfig().then(() => {
      if (cancelled) return
      restoreSessionRef.current()
    })
    return () => {
      cancelled = true
    }
  }, [refreshConfig])

  // -------------------------------------------------------------------------
  // Derived
  // -------------------------------------------------------------------------

  const selectedOrgId = getSelectedOrganizationId()
  const orgSelectionRequired = authMode === 'oidc' && memberships.length > 1 && !selectedOrgId
  const isAuthenticated = authMode === 'development' || (!!session && !!selectedOrgId)

  const value: AuthContextValue = {
    authMode,
    authConfig,
    configLoading,
    configError,
    session,
    isAuthenticated,
    initializing,
    selectedOrgId,
    memberships,
    orgSelectionRequired,
    userInfo,
    authMe,
    refreshConfig,
    login,
    handleCallback,
    logout,
    selectOrganization,
    switchOrganization,
    refreshAuthMe: async () => {
      if (session?.access_token && selectedOrgId) {
        await refreshAuthMe(session.access_token, selectedOrgId)
      }
    },
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return ctx
}
