import { UserManager, WebStorageStateStore } from 'oidc-client-ts'
import type { AuthConfig } from './types'

export function createUserManager(config: AuthConfig): UserManager {
  const authority = config.oidc!.authority.replace(/\/$/, '')
  const redirectUri = `${window.location.origin}/auth/callback`
  const postLogoutRedirectUri = `${window.location.origin}/login`

  return new UserManager({
    authority,
    client_id: config.oidc!.client_id,
    redirect_uri: redirectUri,
    post_logout_redirect_uri: postLogoutRedirectUri,
    response_type: 'code',
    scope: config.oidc!.scope,
    userStore: new WebStorageStateStore({ store: window.sessionStorage }),
    stateStore: new WebStorageStateStore({ store: window.sessionStorage }),
    automaticSilentRenew: false,
    loadUserInfo: false,
  })
}

export async function signinRedirect(userManager: UserManager): Promise<void> {
  await userManager.signinRedirect()
}

export async function signinRedirectCallback(userManager: UserManager) {
  const user = await userManager.signinRedirectCallback()
  return user
}

export async function signout(userManager: UserManager): Promise<void> {
  await userManager.signoutRedirect()
}

export async function getUser(userManager: UserManager) {
  return userManager.getUser()
}
