import React, { useEffect, useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { API_BASE, fetchApi } from '../api'

type Template = {
  id: string
  name: string
  playerCount: number
  duration: number
  tags?: string[]
}

type PlayerBackendConfig = {
  image?: string
  profileName?: string
  extraEnv?: Record<string, string>
}

type Player = {
  id: number
  name: string
  model: string
  apiKey?: string
  baseUrl?: string
  gatewayPort: number
  backendType: 'openclaw' | 'hermes'
  backendConfig: PlayerBackendConfig
}

type ConfigState = {
  matchName: string
  totalDuration: number
  defenseDuration: number
  repeatCount: number
  llmProvider: string
  llmBaseUrl: string
  llmApiKey?: string
  llmProxy?: string
  playerCount: number
  players: Player[]
  scoring?: { attackSuccess: number; defenseFailure: number; slaViolation: number }
  flagsRefreshInterval?: number
  targetImage?: string
  agentImage?: string
}

type LlmPreset = {
  key: string
  label: string
  baseUrl: string
  defaultModel: string
  models: string[]
  hint?: string
}

// 平台运行时统一走 OpenAI 兼容协议（/chat/completions），
// 因此所有预设都必须是 OpenAI 兼容端点；预设只负责填 Base URL 和模型建议，
// 模型名始终可自由输入。
const LLM_PRESETS: LlmPreset[] = [
  {
    key: 'openai',
    label: 'OpenAI',
    baseUrl: 'https://api.openai.com/v1',
    defaultModel: 'gpt-5.2',
    models: ['gpt-5.2', 'gpt-5.1', 'gpt-5', 'gpt-5-mini', 'o4-mini'],
  },
  {
    key: 'anthropic',
    label: 'Anthropic（OpenAI 兼容端点）',
    baseUrl: 'https://api.anthropic.com/v1',
    defaultModel: 'claude-sonnet-4-6',
    models: ['claude-sonnet-4-6', 'claude-opus-4-6', 'claude-haiku-4-5'],
  },
  {
    key: 'openrouter',
    label: 'OpenRouter（多模型路由）',
    baseUrl: 'https://openrouter.ai/api/v1',
    defaultModel: 'anthropic/claude-sonnet-4-6',
    models: [
      'anthropic/claude-sonnet-4-6',
      'openai/gpt-5.2',
      'google/gemini-3-pro',
      'deepseek/deepseek-chat',
      'qwen/qwen3-max',
    ],
    hint: '一个 Key 混用各家模型，适合多模型对局',
  },
  {
    key: 'deepseek',
    label: 'DeepSeek',
    baseUrl: 'https://api.deepseek.com/v1',
    defaultModel: 'deepseek-chat',
    models: ['deepseek-chat', 'deepseek-reasoner'],
  },
  {
    key: 'moonshot',
    label: 'Moonshot（Kimi）',
    baseUrl: 'https://api.moonshot.cn/v1',
    defaultModel: 'kimi-k2-0905-preview',
    models: ['kimi-k2-0905-preview', 'kimi-k2-turbo-preview'],
  },
  {
    key: 'zhipu',
    label: '智谱（GLM）',
    baseUrl: 'https://open.bigmodel.cn/api/paas/v4',
    defaultModel: 'glm-4.6',
    models: ['glm-4.6', 'glm-4.5'],
  },
  {
    key: 'gemini',
    label: 'Google Gemini（OpenAI 兼容端点）',
    baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai',
    defaultModel: 'gemini-3-pro-preview',
    models: ['gemini-3-pro-preview', 'gemini-2.5-pro', 'gemini-2.5-flash'],
  },
  {
    key: 'ollama',
    label: '本地 Ollama / vLLM',
    baseUrl: 'http://host.docker.internal:11434/v1',
    defaultModel: 'qwen3:32b',
    models: ['qwen3:32b', 'llama3.1:70b', 'deepseek-r1:32b'],
    hint: '本地推理无需 API Key',
  },
  {
    key: 'custom',
    label: '自定义（OpenAI 兼容）',
    baseUrl: '',
    defaultModel: '',
    models: [],
    hint: '填写任意 OpenAI 兼容网关地址',
  },
]

const DEFAULT_PRESET = LLM_PRESETS[0]

const findPreset = (key: string): LlmPreset =>
  LLM_PRESETS.find((p) => p.key === key) ?? LLM_PRESETS[LLM_PRESETS.length - 1]

const defaultPlayer = (idx: number, port: number, model = DEFAULT_PRESET.defaultModel): Player => ({
  id: idx,
  name: `Player ${idx}`,
  model,
  apiKey: '',
  gatewayPort: port,
  backendType: 'openclaw',
  backendConfig: {},
})

const ConfigPage: React.FC = () => {
  const navigate = useNavigate()
  const [templates, setTemplates] = useState<Template[]>([])
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null)
  const [showSave, setShowSave] = useState(false)
  const [saveName, setSaveName] = useState('')
  const [saveDesc, setSaveDesc] = useState('')
  const [importError, setImportError] = useState<string | null>(null)
  const [isStarting, setIsStarting] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)
  
  const [testingGlobalLlm, setTestingGlobalLlm] = useState(false)
  const [testingPlayerId, setTestingPlayerId] = useState<number | null>(null)

  const [config, setConfig] = useState<ConfigState>({
    matchName: 'OpenClaw AWD Match',
    totalDuration: 20,
    defenseDuration: 10,
    repeatCount: 1,
    llmProvider: DEFAULT_PRESET.key,
    llmBaseUrl: DEFAULT_PRESET.baseUrl,
    llmApiKey: '',
    llmProxy: '',
    playerCount: 4,
    players: Array.from({ length: 4 }).map((_, i) => defaultPlayer(i + 1, 18789 + i)),
    scoring: { attackSuccess: 100, defenseFailure: -50, slaViolation: -50 },
    flagsRefreshInterval: 5,
    targetImage: 'openclaw/ctf-target:v1',
    agentImage: 'alpine/openclaw:latest',
  })

  const currentPreset = findPreset(config.llmProvider)

  const applyPreset = (key: string) => {
    const preset = findPreset(key)
    setConfig((c) => ({
      ...c,
      llmProvider: preset.key,
      llmBaseUrl: preset.baseUrl || c.llmBaseUrl,
      players: c.players.map((p) => ({ ...p, model: preset.defaultModel || p.model })),
    }))
  }

  const attackDuration = Math.max(0, config.totalDuration - config.defenseDuration)
  const canStart = config.matchName.trim().length > 0 && config.players.length > 0
  const fileRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    setConfig((c) => {
      const current = c.players
      const n = c.playerCount
      if (current.length === n) return c
      if (current.length < n) {
        const added = Array.from({ length: n - current.length }).map((_, i) =>
          defaultPlayer(current.length + i + 1, 18789 + current.length + i)
        )
        return { ...c, players: [...current, ...added] }
      }
      return { ...c, players: current.slice(0, n) }
    })
  }, [config.playerCount])

  useEffect(() => {
    fetchApi(`${API_BASE}/api/templates`)
      .then((r) => r.json())
      .then((data) => {
        const t = Array.isArray(data) ? data : data.templates ?? []
        setTemplates(t)
      })
      .catch(() => {})
  }, [])

  const applyTemplate = (id: string) => {
    setSelectedTemplate(id)
    fetchApi(`${API_BASE}/api/templates/${id}`)
      .then((r) => r.json())
      .then((data: { template?: { config?: Record<string, unknown> } }) => {
        const tplConfig = data?.template?.config
        if (tplConfig) {
          const match = tplConfig.match as Record<string, unknown> | undefined
          const llm = tplConfig.llm as Record<string, unknown> | undefined
          const players = tplConfig.players as Player[] | undefined
          setConfig((c) => ({
            ...c,
            matchName: (match?.name as string) ?? c.matchName,
            totalDuration: match?.duration ? Math.round((match.duration as number) / 60) : c.totalDuration,
            defenseDuration: match?.phases ? Math.round(((match.phases as Record<string, number>).defense ?? 600) / 60) : c.defenseDuration,
            repeatCount: typeof tplConfig.repeatCount === 'number'
              ? tplConfig.repeatCount
              : typeof (tplConfig.loop as { repeatCount?: unknown } | undefined)?.repeatCount === 'number'
                ? ((tplConfig.loop as { repeatCount?: number }).repeatCount ?? c.repeatCount)
                : c.repeatCount,
            llmProvider: (llm?.provider as string) ?? c.llmProvider,
            llmBaseUrl: (llm?.baseUrl as string) ?? c.llmBaseUrl,
            playerCount: players ? players.length : c.playerCount,
            players: players
              ? players.map((p, i) => {
                  const bt = (p as { backendType?: string }).backendType ?? 
                             ((p as { backend_type?: string }).backend_type) ?? 
                             'openclaw'
                  return {
                    id: p.id ?? i + 1,
                    name: p.name ?? `Player ${p.id ?? i + 1}`,
                    model: p.model ?? c.players[i]?.model ?? '',
                    apiKey: '',
                    gatewayPort: p.gatewayPort ?? 18789 + i,
                    backendType: bt === 'hermes' ? 'hermes' as const : 'openclaw' as const,
                    backendConfig: (p as { backendConfig?: PlayerBackendConfig }).backendConfig ?? 
                                  ((p as { backend_config?: PlayerBackendConfig }).backend_config as PlayerBackendConfig) ?? 
                                  {},
                  }
                })
              : c.players,
          }))
        }
        fetchApi(`${API_BASE}/api/templates/${id}/use`, { method: 'POST' }).catch(() => {})
      })
      .catch(() => {})
  }

  const update = <K extends keyof ConfigState>(key: K, value: ConfigState[K]) => {
    setConfig((c) => ({ ...c, [key]: value }))
  }

  const testLlm = async (baseUrl: string, apiKey: string, proxy: string | undefined, model: string, isGlobal: boolean, playerId?: number) => {
    if (!baseUrl) {
      alert('请先填写 Base URL');
      return;
    }
    if (!apiKey) {
      alert('请先填写 API Key');
      return;
    }
    if (!model) {
      alert('请先填写模型名称');
      return;
    }

    if (isGlobal) setTestingGlobalLlm(true);
    else if (playerId) setTestingPlayerId(playerId);

    try {
      const res = await fetchApi(`${API_BASE}/api/test-llm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ baseUrl, apiKey, proxy, model }),
      });
      const data = await res.json();
      if (data.success) {
        alert(`测试成功！延迟: ${(data.latency * 1000).toFixed(0)}ms`);
      } else {
        alert(`测试失败: ${data.error}`);
      }
    } catch (e: any) {
      alert(`测试异常: ${e.message}`);
    } finally {
      if (isGlobal) setTestingGlobalLlm(false);
      else if (playerId) setTestingPlayerId(null);
    }
  }

  const startMatch = async () => {
    if (isStarting || !canStart) return

    setStartError(null)
    setIsStarting(true)

    const payload = {
      match: {
        name: config.matchName,
        duration: config.totalDuration * 60,
        phases: {
          defense: config.defenseDuration * 60,
          attack: attackDuration * 60,
        },
      },
      loop: {
        enabled: config.repeatCount > 1,
        repeatCount: Math.max(1, config.repeatCount),
      },
      llm: {
        provider: config.llmProvider,
        baseUrl: config.llmBaseUrl,
        apiKey: config.llmApiKey,
        proxy: config.llmProxy,
        // 全局回退模型：选手 model 留空时后端使用该值
        model: config.players.find((p) => p.model.trim())?.model.trim() || currentPreset.defaultModel || undefined,
      },
      players: config.players.map((p) => ({
        id: p.id,
        name: p.name,
        model: p.model,
        apiKey: p.apiKey,
        baseUrl: p.baseUrl?.trim() || undefined,
        gatewayPort: p.gatewayPort,
        backend_type: p.backendType,
        backend_config: {
          image: p.backendConfig.image ?? null,
          profile_name: p.backendConfig.profileName ?? null,
          extra_env: p.backendConfig.extraEnv ?? {},
        },
      })),
      scoring: config.scoring,
      flags: {
        refreshInterval: (config.flagsRefreshInterval ?? 5) * 60,
      },
      target_image: config.targetImage,
      agent_image: config.agentImage,
    }

    try {
      const response = await fetchApi(`${API_BASE}/api/matches/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const data: { match_id?: string; id?: string } = await response.json()
      const id = data?.match_id ?? data?.id

      if (!id) {
        throw new Error('未返回比赛 ID')
      }

      navigate(`/arena/${id}`)
    } catch (error) {
      const message = error instanceof Error ? error.message : '创建比赛失败'
      setStartError(message)
      setIsStarting(false)
    }
  }

  const onImport = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setImportError(null)
    const formData = new FormData()
    formData.append('file', file)
    fetchApi(`${API_BASE}/api/templates/import`, {
      method: 'POST',
      body: formData,
    })
      .then((resp) => {
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        return resp.json()
      })
      .then((resp: { success?: boolean; templateId?: string; template?: Template }) => {
        const tpl = resp.template
        if (tpl) {
          setTemplates((old) => [...old, tpl])
        }
      })
      .catch(() => setImportError('Import failed — invalid JSON file or server error'))
    e.target.value = ''
  }

  const useSameModelAll = () => {
    const m = config.players[0]?.model || currentPreset.defaultModel || ''
    setConfig((c) => ({ ...c, players: c.players.map((p) => ({ ...p, model: m })) }))
  }
  const autoFillNames = () => {
    setConfig((c) => ({ ...c, players: c.players.map((p, i) => ({ ...p, name: `Player ${i + 1}` })) }))
  }

  return (
    <div className="space-y-6">
      <section className="bg-slate-800/60 border border-slate-700 rounded-md p-4 flex flex-col gap-3">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-2 text-sm text-slate-200">
            <span>模板管理:</span>
            <select className="bg-slate-700 rounded-md px-2 py-1" value={selectedTemplate ?? ''} onChange={(e) => applyTemplate(e.target.value)}>
              <option value="" disabled>请选择模板</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>{t.name} — {t.playerCount} 玩者, {t.duration} 分钟</option>
              ))}
            </select>
          </div>
          <div className="flex gap-2">
            <button className="px-3 py-2 rounded-md bg-cyan-600 hover:bg-cyan-500 text-white" onClick={() => setShowSave(true)}>保存为模板</button>
            <button className="px-3 py-2 rounded-md bg-slate-700 hover:bg-slate-600 text-white" onClick={() => fileRef.current?.click()}>Import</button>
            <input ref={fileRef} type="file" accept="application/json" style={{ display: 'none' }} onChange={onImport} />
          </div>
        </div>
        <div className="text-xs text-slate-300">{templates.length ? templates.length + ' templates' : 'No templates'}</div>
      </section>

      <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-slate-800/60 border border-slate-700 rounded-md p-4 space-y-4">
          <h3 className="text-lg font-semibold">基础配置</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="block text-sm text-slate-300">赛事名称</label>
              <input className="w-full bg-slate-700 rounded-md px-2 py-1" value={config.matchName} onChange={(e) => update('matchName', e.target.value)} />
            </div>
            <div>
              <label className="block text-sm text-slate-300">总时长</label>
              <input type="number" className="w-full bg-slate-700 rounded-md px-2 py-1" value={config.totalDuration} onChange={(e) => update('totalDuration', Number(e.target.value))} />
            </div>
            <div>
              <label className="block text-sm text-slate-300">防守时长</label>
              <input type="number" className="w-full bg-slate-700 rounded-md px-2 py-1" value={config.defenseDuration} onChange={(e) => update('defenseDuration', Number(e.target.value))} />
            </div>
            <div>
              <label className="block text-sm text-slate-300">攻击时长</label>
              <input className="w-full bg-slate-700 rounded-md px-2 py-1" value={attackDuration} readOnly />
            </div>
            <div>
              <label className="block text-sm text-slate-300">循环次数</label>
              <input
                type="number"
                min={1}
                className="w-full bg-slate-700 rounded-md px-2 py-1"
                value={config.repeatCount}
                onChange={(e) => update('repeatCount', Math.max(1, Number(e.target.value) || 1))}
              />
            </div>
            <div className="md:col-span-2 rounded-md border border-cyan-800/60 bg-cyan-950/30 px-3 py-2 text-sm text-cyan-100">
              {config.repeatCount > 1
                ? `当前将连续执行 ${config.repeatCount} 场相同配置的比赛；每一场进入“finish-已清理”后会自动开始下一场。`
                : '循环次数为 1 时，仅启动单场比赛。'}
            </div>
          </div>
        </div>
        <div className="bg-slate-800/60 border border-slate-700 rounded-md p-4 space-y-4">
          <h3 className="text-lg font-semibold">LLM 配置</h3>
          <div className="text-xs text-slate-400">
            平台通过 OpenAI 兼容协议（<code>/chat/completions</code>）访问模型，
            选择预设会自动填入对应 Base URL 并提供模型建议；模型名可自由输入。
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="block text-sm text-slate-300">接入预设</label>
              <select className="w-full bg-slate-700 rounded-md px-2 py-1" value={currentPreset.key} onChange={(e) => applyPreset(e.target.value)}>
                {LLM_PRESETS.map((p) => (
                  <option key={p.key} value={p.key}>{p.label}</option>
                ))}
              </select>
              {currentPreset.hint && (
                <div className="mt-1 text-xs text-cyan-300/80">{currentPreset.hint}</div>
              )}
            </div>
            <div>
              <label className="block text-sm text-slate-300">Base URL</label>
              <input className="w-full bg-slate-700 rounded-md px-2 py-1" placeholder="https://your-openai-compatible-gateway/v1" value={config.llmBaseUrl} onChange={(e) => update('llmBaseUrl', e.target.value)} />
            </div>
            <div className="md:col-span-2">
              <label className="block text-sm text-slate-300">API Key</label>
              <input type="password" className="w-full bg-slate-700 rounded-md px-2 py-1" value={config.llmApiKey ?? ''} onChange={(e) => update('llmApiKey', e.target.value)} />
            </div>
            <div>
              <label className="block text-sm text-slate-300">代理 URL</label>
              <input className="w-full bg-slate-700 rounded-md px-2 py-1" value={config.llmProxy ?? ''} onChange={(e) => update('llmProxy', e.target.value)} />
            </div>
            <div className="md:col-span-2 flex justify-end">
              <button 
                className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-md text-sm text-white disabled:opacity-50"
                onClick={() => testLlm(config.llmBaseUrl, config.llmApiKey ?? '', config.llmProxy, config.players[0]?.model || currentPreset.defaultModel, true)}
                disabled={testingGlobalLlm}
              >
                {testingGlobalLlm ? '测试中...' : '测试全局 API'}
              </button>
            </div>
          </div>
        </div>
      </section>

      <section className="bg-slate-800/60 border border-slate-700 rounded-md p-4">
        <h3 className="text-lg font-semibold mb-2">选手配置</h3>
        <datalist id="llm-model-suggestions">
          {(currentPreset.models.length ? currentPreset.models : LLM_PRESETS.flatMap((p) => p.models)).map((m) => (
            <option key={m} value={m} />
          ))}
        </datalist>
        <div className="flex items-center gap-2 mb-3 text-sm text-slate-300">
          <span>选手数:</span>
          {[2,3,4,5,6,8,10].map((n) => (
            <button key={n} className={`px-2 py-1 rounded-md ${config.playerCount===n? 'bg-slate-700': 'bg-slate-700/60'}`} onClick={() => update('playerCount', n)}>{n}</button>
          ))}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {config.players.map((p, idx) => (
            <div key={p.id} className="bg-slate-700/40 border border-slate-600 rounded-md p-3 space-y-2">
              <div className="text-sm font-semibold">{p.name || `Player ${p.id}`}</div>
              <div>
                <div className="flex justify-between items-center">
                  <label className="text-xs text-slate-200">模型</label>
                  <button 
                    className="text-xs text-blue-400 hover:text-blue-300 disabled:opacity-50"
                    onClick={() => testLlm(p.baseUrl || config.llmBaseUrl, p.apiKey || config.llmApiKey || '', config.llmProxy, p.model, false, p.id)}
                    disabled={testingPlayerId === p.id}
                  >
                    {testingPlayerId === p.id ? '测试中...' : '测试可用性'}
                  </button>
                </div>
                <input
                  list="llm-model-suggestions"
                  className="w-full bg-slate-600 rounded-md px-2 py-1"
                  placeholder={currentPreset.defaultModel || '输入或选择模型名'}
                  value={p.model}
                  onChange={(e) => {
                    const nm = e.target.value
                    setConfig((c) => {
                      const players = c.players.slice()
                      players[idx] = { ...players[idx], model: nm }
                      return { ...c, players }
                    })
                  }}
                />
              </div>
              <div>
                <div className="flex justify-between items-center">
                  <label className="text-xs text-slate-200">API Key</label>
                  <span className="text-[10px] text-slate-400">留空使用全局 Key</span>
                </div>
                <input className="w-full bg-slate-600 rounded-md px-2 py-1" value={p.apiKey ?? ''} onChange={(e) => {
                  const k = e.target.value
                  setConfig((c) => {
                    const players = c.players.slice()
                    players[idx] = { ...players[idx], apiKey: k }
                    return { ...c, players }
                  })
                }} />
              </div>
              <div>
                <div className="flex justify-between items-center">
                  <label className="text-xs text-slate-200">Base URL 覆盖</label>
                  <span className="text-[10px] text-slate-400">多厂商直连对局</span>
                </div>
                <input
                  className="w-full bg-slate-600 rounded-md px-2 py-1"
                  placeholder="留空使用全局 Base URL"
                  value={p.baseUrl ?? ''}
                  onChange={(e) => {
                    const b = e.target.value
                    setConfig((c) => {
                      const players = c.players.slice()
                      players[idx] = { ...players[idx], baseUrl: b }
                      return { ...c, players }
                    })
                  }}
                />
              </div>
              <div>
                <label className="text-xs text-slate-200">网关端口</label>
                <input className="w-full bg-slate-600 rounded-md px-2 py-1" value={p.gatewayPort} readOnly />
              </div>
              <div>
                <label className="text-xs text-slate-200">后端类型</label>
                <select
                  className="w-full bg-slate-600 rounded-md px-2 py-1"
                  value={p.backendType}
                  onChange={(e) => {
                    const bt = e.target.value as 'openclaw' | 'hermes'
                    setConfig((c) => {
                      const players = c.players.slice()
                      players[idx] = { ...players[idx], backendType: bt }
                      return { ...c, players }
                    })
                  }}
                >
                  <option value="openclaw">OpenClaw</option>
                  <option value="hermes">Hermes</option>
                </select>
              </div>
              {p.backendType === 'hermes' && (
                <div className="space-y-2 pl-2 border-l-2 border-amber-600/50">
                  <div>
                    <label className="text-xs text-slate-300">镜像 (Hermes专用)</label>
                    <input
                      className="w-full bg-slate-600 rounded-md px-2 py-1"
                      placeholder="hermes-agent:latest"
                      value={p.backendConfig.image ?? ''}
                      onChange={(e) => {
                        setConfig((c) => {
                          const players = c.players.slice()
                          players[idx] = {
                            ...players[idx],
                            backendConfig: { ...players[idx].backendConfig, image: e.target.value }
                          }
                          return { ...c, players }
                        })
                      }}
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-300">额外环境变量 (JSON)</label>
                    <input
                      className="w-full bg-slate-600 rounded-md px-2 py-1"
                      placeholder='{"KEY": "value"}'
                      value={JSON.stringify(p.backendConfig.extraEnv ?? {})}
                      onChange={(e) => {
                        try {
                          const parsed = JSON.parse(e.target.value)
                          setConfig((c) => {
                            const players = c.players.slice()
                            players[idx] = {
                              ...players[idx],
                              backendConfig: { ...players[idx].backendConfig, extraEnv: parsed }
                            }
                            return { ...c, players }
                          })
                        } catch {}
                      }}
                    />
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
        <div className="flex space-x-2 mt-3">
          <button className="px-3 py-2 rounded-md bg-slate-700" onClick={useSameModelAll}>将全部模型设为同一模型</button>
          <button className="px-3 py-2 rounded-md bg-slate-700" onClick={autoFillNames}>自动生成名称</button>
        </div>
      </section>

      <section className="bg-slate-800/60 border border-slate-700 rounded-md p-4">
        <details>
          <summary className="cursor-pointer text-lg font-semibold">高级配置</summary>
          <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="block text-sm text-slate-300">Score weights (attack / defense / SLA)</label>
              <div className="grid grid-cols-3 gap-2">
                <input
                  type="number"
                  className="bg-slate-700 rounded-md px-2 py-1"
                  placeholder="attack"
                  value={config.scoring?.attackSuccess ?? 100}
                  onChange={(e) =>
                    setConfig((c) => ({ ...c, scoring: { ...(c.scoring ?? { attackSuccess: 100, defenseFailure: -50, slaViolation: -50 }), attackSuccess: Number(e.target.value) } }))
                  }
                />
                <input
                  type="number"
                  className="bg-slate-700 rounded-md px-2 py-1"
                  placeholder="defense"
                  value={config.scoring?.defenseFailure ?? -50}
                  onChange={(e) =>
                    setConfig((c) => ({ ...c, scoring: { ...(c.scoring ?? { attackSuccess: 100, defenseFailure: -50, slaViolation: -50 }), defenseFailure: Number(e.target.value) } }))
                  }
                />
                <input
                  type="number"
                  className="bg-slate-700 rounded-md px-2 py-1"
                  placeholder="sla"
                  value={config.scoring?.slaViolation ?? -50}
                  onChange={(e) =>
                    setConfig((c) => ({ ...c, scoring: { ...(c.scoring ?? { attackSuccess: 100, defenseFailure: -50, slaViolation: -50 }), slaViolation: Number(e.target.value) } }))
                  }
                />
              </div>
            </div>
            <div>
              <label className="block text-sm text-slate-300">Flag refresh interval (minutes)</label>
              <input
                type="number"
                className="w-full bg-slate-700 rounded-md px-2 py-1"
                value={config.flagsRefreshInterval ?? 5}
                onChange={(e) => update('flagsRefreshInterval', Number(e.target.value))}
              />
            </div>
            <div>
              <label className="block text-sm text-slate-300">Target image</label>
              <input
                className="w-full bg-slate-700 rounded-md px-2 py-1"
                value={config.targetImage ?? ''}
                onChange={(e) => update('targetImage', e.target.value)}
              />
            </div>
            <div>
              <label className="block text-sm text-slate-300">Agent image (仅用于OpenClaw默认)</label>
              <div className="text-xs text-slate-400 mt-1">每个选手可在下方单独选择后端类型</div>
              <input
                className="w-full bg-slate-700 rounded-md px-2 py-1"
                value={config.agentImage ?? ''}
                onChange={(e) => update('agentImage', e.target.value)}
              />
            </div>
          </div>
        </details>
      </section>

      <section className="flex justify-end gap-3">
        <button className="px-4 py-2 rounded-md bg-slate-600 disabled:opacity-50" disabled={isStarting} onClick={() => {
          setConfig({
            matchName: '', totalDuration: 20, defenseDuration: 10, repeatCount: 1, llmProvider: 'OpenAI', llmBaseUrl: '', llmApiKey: '', llmProxy: '', playerCount: 4,
            players: Array.from({ length: 4 }).map((_, i) => defaultPlayer(i + 1, 18789 + i)),
            scoring: { attackSuccess: 100, defenseFailure: -50, slaViolation: -50 },
            flagsRefreshInterval: 5,
            targetImage: 'openclaw/ctf-target:v1',
            agentImage: 'alpine/openclaw:latest',
          } as ConfigState)
        }}>重置</button>
        <button className="px-4 py-2 rounded-md bg-cyan-600 text-white disabled:opacity-50" onClick={startMatch} disabled={!canStart || isStarting}>{isStarting ? '创建中...' : config.repeatCount > 1 ? '🚀 开始循环比赛' : '🚀 开始比赛'}</button>
      </section>

      {startError && <div className="text-red-400 text-sm text-right">创建比赛失败：{startError}</div>}

      {showSave && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-900 text-slate-100 rounded-md p-6 w-full max-w-md">
            <h4 className="text-lg font-semibold mb-2">保存为模板</h4>
            <div className="mb-3">
              <label className="block text-sm text-slate-300">名称</label>
              <input className="w-full bg-slate-700 rounded-md px-2 py-1" value={saveName} onChange={(e) => setSaveName(e.target.value)} />
            </div>
            <div className="mb-3">
              <label className="block text-sm text-slate-300">描述</label>
              <textarea className="w-full bg-slate-700 rounded-md px-2 py-1" value={saveDesc} onChange={(e) => setSaveDesc(e.target.value)} />
            </div>
            <div className="flex justify-end gap-2">
              <button className="px-3 py-2 rounded-md bg-slate-700" onClick={() => setShowSave(false)}>取消</button>
              <button className="px-3 py-2 rounded-md bg-cyan-600 text-white" onClick={() => {
                fetchApi(`${API_BASE}/api/templates`, {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ name: saveName, description: saveDesc, config })
                }).then(() => setShowSave(false)).catch(() => setShowSave(false))
              }}>保存</button>
            </div>
          </div>
        </div>
      )}
      {isStarting && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-slate-900 text-slate-100 rounded-md border border-slate-700 p-6 w-full max-w-md shadow-2xl">
            <div className="flex items-center gap-4">
              <div className="h-10 w-10 rounded-full border-4 border-cyan-500/30 border-t-cyan-400 animate-spin" />
              <div className="space-y-1">
                <h4 className="text-lg font-semibold">正在创建比赛</h4>
                <p className="text-sm text-slate-300">正在创建会话并启动观战页面，请勿重复点击。</p>
              </div>
            </div>
          </div>
        </div>
      )}
      {importError && <div className="text-red-500">Import error: {importError}</div>}
    </div>
  )
}

export default ConfigPage
