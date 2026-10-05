export interface AuthConfig {
  auth_mode: 'development' | 'oidc'
  authentication_required: boolean
  oidc: {
    authority: string
    client_id: string
    scope: string
  } | null
}

export interface AuthBootstrapUser {
  user_id: string
  display_name: string
  email?: string
}

export interface AuthBootstrapMembership {
  organization_id: string
  organization_name: string
  role: string
}

export interface AuthBootstrapResponse {
  user: AuthBootstrapUser
  memberships: AuthBootstrapMembership[]
}

export interface AuthMeResponse {
  user_id: string
  organization_id: string
  display_name?: string
  email?: string
  roles: string[]
  authenticated: boolean
  source: string
}

export interface AuthSession {
  access_token: string
  id_token?: string
  expires_at: number
  user_id: string
  display_name: string
  email?: string
}
