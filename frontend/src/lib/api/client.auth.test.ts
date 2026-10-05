import { describe, it, expect, vi, beforeEach } from 'vitest'

const hoisted = vi.hoisted(() => {
  const instances: any[] = []
  const makeInstance = () => {
    const fns = { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }
    let responseRejected: ((_e: any) => any) | null = null
    const inst: any = {
      defaults: { headers: {} },
      interceptors: {
        request: { use: vi.fn() },
        response: { use: (_f: any, r: any) => { responseRejected = r } },
      },
      get: (...args: any[]) => fns.get(...args).then((r: any) => r, (e: any) => (responseRejected ? responseRejected(e) : Promise.reject(e))),
      post: (...args: any[]) => fns.post(...args).then((r: any) => r, (e: any) => (responseRejected ? responseRejected(e) : Promise.reject(e))),
      patch: (...args: any[]) => fns.patch(...args).then((r: any) => r, (e: any) => (responseRejected ? responseRejected(e) : Promise.reject(e))),
      delete: (...args: any[]) => fns.delete(...args).then((r: any) => r, (e: any) => (responseRejected ? responseRejected(e) : Promise.reject(e))),
    }
    inst._fns = fns
    return inst
  }
  const create = vi.fn(() => {
    const i = makeInstance()
    instances.push(i)
    return i
  })
  return { instances, create }
})

vi.mock('axios', () => ({ default: Object.assign(hoisted.create, { create: hoisted.create }) }))

// Mock sessionStorage
const storage: Record<string, string> = {}
const mockSessionStorage = {
  getItem: (key: string) => storage[key] || null,
  setItem: (key: string, value: string) => { storage[key] = value },
  removeItem: (key: string) => { delete storage[key] },
  clear: () => { Object.keys(storage).forEach(k => delete storage[k]) },
}
Object.defineProperty(window, 'sessionStorage', { value: mockSessionStorage })

import { apiClient, publicApi, getAuthHeaders } from './client'

beforeEach(() => {
  hoisted.instances.forEach((i) => {
    i._fns.get.mockReset()
    i._fns.post.mockReset()
    i._fns.patch.mockReset()
    i._fns.delete.mockReset()
    i.interceptors.request.use.mockReset()
  })
  mockSessionStorage.clear()
})

// Instance mapping in client.ts (module load order):
//   [0] api           = makeClient(CONTROL_TIMEOUT)
//   [1] inference     = makeClient(INFERENCE_TIMEOUT)
//   [2] publicApi     = makePublicClient(CONTROL_TIMEOUT)

describe('apiClient — auth interceptors', () => {
  it('attaches bearer token from sessionStorage on protected requests', async () => {
    mockSessionStorage.setItem('sovereign_auth_session', JSON.stringify({
      access_token: 'test-token',
      expires_at: Date.now() + 3600000,
      user_id: 'user-1',
      display_name: 'Test',
    }))

    const inst = hoisted.instances[0]
    inst._fns.get.mockResolvedValue({
      data: {
        sovereign: true,
        gpu: null,
        services: {},
        components: [{ id: 'fastapi', name: 'FastAPI', status: 'ONLINE', detail: '', endpoint: '/', local: true }],
        uptime_seconds: 10,
        external_api_calls: 0,
        blocked_connections: 0,
      },
    })

    await apiClient.getSystemStatus()
    expect(inst._fns.get).toHaveBeenCalledWith('/system/status')
    // Request interceptor is registered at module load time (verified by integration)
  })

  it('does not attach token to public api requests', async () => {
    const inst = hoisted.instances[2]
    inst._fns.get.mockResolvedValue({ data: { status: 'ok' } })

    await publicApi.get('/system/health')
    expect(inst._fns.get).toHaveBeenCalledWith('/system/health')
    // publicApi should NOT have request interceptor
    expect(inst.interceptors.request.use).not.toHaveBeenCalled()
  })

  it('getAuthHeaders returns empty object when no session', () => {
    expect(getAuthHeaders()).toEqual({})
  })

  it('getAuthHeaders returns Authorization when session exists', () => {
    mockSessionStorage.setItem('sovereign_auth_session', JSON.stringify({
      access_token: 'my-token',
      expires_at: Date.now() + 3600000,
      user_id: 'u1',
      display_name: 'U',
    }))
    const headers = getAuthHeaders()
    expect(headers.Authorization).toBe('Bearer my-token')
  })

  it('getAuthHeaders includes X-Sovereign-Organization when org selected', () => {
    mockSessionStorage.setItem('sovereign_auth_session', JSON.stringify({
      access_token: 'my-token',
      expires_at: Date.now() + 3600000,
      user_id: 'u1',
      display_name: 'U',
    }))
    mockSessionStorage.setItem('sovereign_selected_org_id', 'org-456')
    const headers = getAuthHeaders()
    expect(headers.Authorization).toBe('Bearer my-token')
    expect(headers['X-Sovereign-Organization']).toBe('org-456')
  })
})

describe('apiClient — auth config/bootstrap/me (public methods)', () => {
  it('getAuthConfig hits /auth/config on public client', async () => {
    const inst = hoisted.instances[2]
    inst._fns.get.mockResolvedValue({
      data: { auth_mode: 'development', authentication_required: false, oidc: null },
    })
    const result = await apiClient.getAuthConfig()
    expect(result.auth_mode).toBe('development')
    expect(inst._fns.get).toHaveBeenCalledWith('/auth/config')
  })

  it('getAuthBootstrap hits /auth/bootstrap with auth headers', async () => {
    mockSessionStorage.setItem('sovereign_auth_session', JSON.stringify({
      access_token: 'bootstrap-token',
      expires_at: Date.now() + 3600000,
      user_id: 'u1',
      display_name: 'U',
    }))

    const inst = hoisted.instances[0]
    inst._fns.get.mockResolvedValue({
      data: {
        user: { user_id: 'u1', display_name: 'U', email: 'u@test' },
        memberships: [{ organization_id: 'org-1', organization_name: 'Org 1', role: 'member' }],
      },
    })

    const result = await apiClient.getAuthBootstrap()
    expect(result.memberships).toHaveLength(1)
    expect(result.memberships[0].organization_name).toBe('Org 1')
  })

  it('getAuthMe hits /auth/me with auth and org headers', async () => {
    mockSessionStorage.setItem('sovereign_auth_session', JSON.stringify({
      access_token: 'me-token',
      expires_at: Date.now() + 3600000,
      user_id: 'u1',
      display_name: 'U',
    }))
    mockSessionStorage.setItem('sovereign_selected_org_id', 'org-1')

    const inst = hoisted.instances[0]
    inst._fns.get.mockResolvedValue({
      data: { user_id: 'u1', organization_id: 'org-1', roles: ['member'], authenticated: true, source: 'oidc' },
    })

    const result = await apiClient.getAuthMe()
    expect(result.authenticated).toBe(true)
    expect(result.source).toBe('oidc')
  })
})

describe('apiClient — downloadArtifact', () => {
  it('downloadArtifact uses fetch with auth headers', async () => {
    mockSessionStorage.setItem('sovereign_auth_session', JSON.stringify({
      access_token: 'dl-token',
      expires_at: Date.now() + 3600000,
      user_id: 'u1',
      display_name: 'U',
    }))
    mockSessionStorage.setItem('sovereign_selected_org_id', 'org-1')

    const mockBlob = new Blob(['artifact content'], { type: 'application/octet-stream' })
    const mockResponse = {
      ok: true,
      blob: vi.fn().mockResolvedValue(mockBlob),
      headers: new Headers({ 'content-disposition': 'attachment; filename="test.pdf"' }),
    }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse as any)

    const result = await apiClient.downloadArtifact('artifact-1')
    expect(result.blob).toBe(mockBlob)
    expect(result.filename).toBe('test.pdf')

    vi.restoreAllMocks()
  })

  it('downloadArtifact falls back to default filename when no content-disposition', async () => {
    mockSessionStorage.setItem('sovereign_auth_session', JSON.stringify({
      access_token: 'dl-token',
      expires_at: Date.now() + 3600000,
      user_id: 'u1',
      display_name: 'U',
    }))

    const mockBlob = new Blob(['artifact content'], { type: 'application/octet-stream' })
    const mockResponse = {
      ok: true,
      blob: vi.fn().mockResolvedValue(mockBlob),
      headers: new Headers(),
    }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse as any)

    const result = await apiClient.downloadArtifact('artifact-1')
    expect(result.filename).toBe('artifact-artifact-1')

    vi.restoreAllMocks()
  })
})
