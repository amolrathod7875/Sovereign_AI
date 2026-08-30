import { describe, it, expect, vi, beforeEach } from 'vitest'

const hoisted = vi.hoisted(() => {
  const instances: any[] = []
  const makeInstance = () => {
    const fns = { get: vi.fn(), post: vi.fn() }
    let onRejected: ((_e: any) => any) | null = null
    const inst: any = {
      defaults: { headers: {} },
      interceptors: { response: { use: (_f: any, r: any) => { onRejected = r } } },
      get: (...args: any[]) => fns.get(...args).then((r: any) => r, (e: any) => (onRejected ? onRejected(e) : Promise.reject(e))),
      post: (...args: any[]) => fns.post(...args).then((r: any) => r, (e: any) => (onRejected ? onRejected(e) : Promise.reject(e))),
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

import { apiClient } from './client'

beforeEach(() => {
  hoisted.instances.forEach((i) => {
    i._fns.get.mockReset()
    i._fns.post.mockReset()
  })
})

describe('apiClient — control-plane calls', () => {
  it('getSystemStatus returns probed status', async () => {
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
    const status = await apiClient.getSystemStatus()
    expect(status.external_api_calls).toBe(0)
    expect(status.components[0].status).toBe('ONLINE')
    expect(inst._fns.get).toHaveBeenCalledWith('/system/status')
  })

  it('listModels maps registry entries', async () => {
    const inst = hoisted.instances[0]
    inst._fns.get.mockResolvedValue({
      data: [{ id: 'general', name: 'Qwen2.5-3B-Instruct', endpoint: 'http://localhost:8001/v1', capabilities: ['reasoning'], context_length: 8192, status: 'online', local: true, modalities: ['text'] }],
    })
    const models = await apiClient.listModels()
    expect(models[0].name).toBe('Qwen2.5-3B-Instruct')
  })

  it('routeTask posts to /models/route', async () => {
    const inst = hoisted.instances[0]
    inst._fns.post.mockResolvedValue({
      data: { task_type: 'CODING', modality: 'text', selected_model: 'qwen-coder', models_required: ['qwen-coder'], requires_rag: false, requires_tools: true, confidence: 0.88, reason: 'code', capabilities: ['code generation'], local_only: true, all_local: true, external_calls: 0 },
    })
    const d = await apiClient.routeTask({ task: 'write python function' })
    expect(d.selected_model).toBe('qwen-coder')
    expect(inst._fns.post).toHaveBeenCalledWith('/models/route', { task: 'write python function' })
  })
})

describe('apiClient — inference calls', () => {
  it('runCoder uses the inference client and returns files', async () => {
    const inst = hoisted.instances[1]
    inst._fns.post.mockResolvedValue({
      data: { run_id: 'c1', status: 'success', files: ['solution.py'], file_contents: { 'solution.py': 'print(1)' }, test_output: { passed: true, exit_code: 0 }, test_command: 'pytest', iterations: 1, failure_analysis: '', workspace: '/tmp', execution_trace: [], errors: [], external_calls: 0, routing: { task_type: 'CODING', modality: 'text', selected_model: 'qwen-coder', models_required: ['qwen-coder'], requires_rag: false, requires_tools: true, confidence: 0.88, reason: '', capabilities: [], local_only: true, all_local: true, external_calls: 0 } },
    })
    const res = await apiClient.runCoder('write a reynolds function')
    expect(res.files).toContain('solution.py')
    expect(res.external_calls).toBe(0)
  })

  it('uploadDocument posts multipart form data', async () => {
    const inst = hoisted.instances[0]
    inst._fns.post.mockResolvedValue({
      data: { document_id: 'd1', filename: 'a.pdf', mime_type: 'application/pdf', size: 10, checksum: 'abc', stored_path: '/uploads/a.pdf', parse_supported: true, vision_supported: false },
    })
    const res = await apiClient.uploadDocument(new File([], 'a.pdf'))
    expect(res.stored_path).toBe('/uploads/a.pdf')
  })
})

describe('apiClient — error handling', () => {
  it('rejects with a typed ApiError carrying the backend status', async () => {
    const inst = hoisted.instances[0]
    inst._fns.get.mockRejectedValue({ response: { status: 503, data: { detail: 'PostgreSQL is not configured.' } }, message: 'fail' })
    await expect(apiClient.getSystemStatus()).rejects.toMatchObject({ status: 503, detail: 'PostgreSQL is not configured.' })
  })
})
