import React, { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { API_BASE, fetchApi } from '../api'

type AnalyticsPlayer = {
  player_id: number
  display_name: string
  model: string | null
  first_exploit_at: string | null
  time_to_first_exploit_seconds: number | null
  flags_captured: number
  attack_score: number
  attack_slots_captured: string[]
  flags_lost: number
  defense_score: number
  sla_down_minutes: number
  total_score: number
  submissions_made: number
  successful_submissions: number
  submission_success_rate: number
  score_per_submission: number
}

type AnalyticsData = {
  match_id: string
  duration_seconds: number
  defense_duration_seconds: number
  attack_duration_seconds: number
  players: AnalyticsPlayer[]
  summary: {
    total_submissions: number
    total_successful: number
    fastest_exploit_seconds: number | null
    slowest_exploit_seconds: number | null
    players_with_exploit: number
    players_without_exploit: number
  }
}

type MatchRow = {
  match_id: string
  id?: string
  name?: string
  status: string
  player_count?: number
  playerCount?: number
  created_at?: string
  createdAt?: string
  duration?: number
  resource_destroyed?: boolean
  resourceDestroyed?: boolean
  can_end?: boolean
  canEnd?: boolean
  finished_at?: string
  finishedAt?: string
}

const isTerminalStatus = (status: string): boolean => ['finished', 'error', 'aborted'].includes(status)

const HistoryPage: React.FC = () => {
  const [matches, setMatches] = useState<MatchRow[]>([])
  const [statusFilter, setStatusFilter] = useState<string>('All')
  const [endingMatchId, setEndingMatchId] = useState<string | null>(null)
  const [exportingCodeMatchId, setExportingCodeMatchId] = useState<string | null>(null)
  const [analyticsMatchId, setAnalyticsMatchId] = useState<string | null>(null)
  const [analyticsData, setAnalyticsData] = useState<AnalyticsData | null>(null)
  const [analyticsLoading, setAnalyticsLoading] = useState(false)
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const highlightedMatchId = searchParams.get('matchId')
  const highlightedRowRef = useRef<HTMLTableRowElement | null>(null)

  const loadMatches = () => {
    fetchApi(`${API_BASE}/api/matches`)
      .then((r) => r.json())
      .then((data) => {
        const list = Array.isArray(data) ? data : data.matches ?? []
        const sortedList = (list as MatchRow[]).sort((a, b) => {
          const tA = new Date(a.created_at ?? a.createdAt ?? 0).getTime()
          const tB = new Date(b.created_at ?? b.createdAt ?? 0).getTime()
          return tB - tA
        })
        setMatches(sortedList)
      })
  }

  useEffect(() => {
    loadMatches()
  }, [])

  useEffect(() => {
    if (!highlightedMatchId || matches.length === 0) return

    const hasHighlightedMatch = matches.some((m) => (m.match_id ?? m.id ?? '') === highlightedMatchId)
    if (!hasHighlightedMatch) return

    highlightedRowRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [highlightedMatchId, matches])

  const filteredMatches = matches.filter(m => statusFilter === 'All' || m.status === statusFilter)
  const uniqueStatuses = Array.from(new Set(matches.map(m => m.status)))

  const handleExport = async (e: React.MouseEvent, matchId: string) => {
    e.stopPropagation()
    try {
      const matchRes = await fetchApi(`${API_BASE}/api/matches/${matchId}`)
      const matchData = await matchRes.json()
      
      const eventsRes = await fetchApi(`${API_BASE}/api/matches/${matchId}/events?limit=10000`)
      const eventsData = await eventsRes.json()
      
      const fullData = {
        ...matchData,
        events: Array.isArray(eventsData) ? eventsData : eventsData.events ?? []
      }
      
      const blob = new Blob([JSON.stringify(fullData, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `match_${matchId}.json`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error("Export failed:", err)
      alert("导出失败，请检查网络或后端状态")
    }
  }

  const handleEndMatch = async (e: React.MouseEvent, matchId: string) => {
    e.stopPropagation()
    setEndingMatchId(matchId)
    try {
      const resp = await fetchApi(`${API_BASE}/api/matches/${matchId}/end`, { method: 'POST' })
      if (!resp.ok) {
        const text = await resp.text()
        throw new Error(text || `HTTP ${resp.status}`)
      }
      alert(`比赛 ${matchId} 已结束`)
      loadMatches()
    } catch (err) {
      console.error('End failed:', err)
      alert('结束比赛失败，请检查后端日志')
    } finally {
      setEndingMatchId(null)
    }
  }

  const handleShowAnalytics = async (e: React.MouseEvent, matchId: string) => {
    e.stopPropagation()
    setAnalyticsMatchId(matchId)
    setAnalyticsLoading(true)
    setAnalyticsData(null)
    try {
      const resp = await fetchApi(`${API_BASE}/api/matches/${matchId}/analytics`)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      setAnalyticsData(data.analytics ?? null)
    } catch (err) {
      console.error('Analytics fetch failed:', err)
      alert('获取分析数据失败')
      setAnalyticsMatchId(null)
    } finally {
      setAnalyticsLoading(false)
    }
  }

  const formatSeconds = (s: number | null): string => {
    if (s === null) return '—'
    if (s < 60) return `${s.toFixed(0)}s`
    if (s < 3600) return `${(s / 60).toFixed(1)}min`
    return `${(s / 3600).toFixed(1)}h`
  }

  const handlePlayerCodeExport = async (e: React.MouseEvent, matchId: string) => {
    e.stopPropagation()
    setExportingCodeMatchId(matchId)
    try {
      const resp = await fetchApi(`${API_BASE}/api/matches/${matchId}/player-code-export`)
      if (!resp.ok) {
        const contentType = resp.headers.get('content-type') || ''
        let detail = `HTTP ${resp.status}`
        if (contentType.includes('application/json')) {
          const payload = await resp.json()
          detail = typeof payload?.detail === 'string' ? payload.detail : JSON.stringify(payload)
        } else {
          const text = await resp.text()
          if (text) detail = text
        }
        throw new Error(detail)
      }

      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `match_${matchId}_player_code_export.zip`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error('Player code export failed:', err)
      alert(`导出选手代码/复盘材料失败：${err instanceof Error ? err.message : '请检查后端状态'}`)
    } finally {
      setExportingCodeMatchId(null)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-semibold">历史比赛</h2>
        <div className="flex items-center gap-4">
          <select 
            value={statusFilter} 
            onChange={(e) => setStatusFilter(e.target.value)}
            className="bg-slate-700 px-3 py-2 rounded-md text-sm border-none focus:ring-1 focus:ring-cyan-500"
          >
            <option value="All">所有状态</option>
            {uniqueStatuses.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <button className="px-3 py-2 rounded-md bg-slate-700 hover:bg-slate-600 transition-colors" onClick={loadMatches}>刷新</button>
        </div>
      </div>
      
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-700 text-left">
            <th className="py-2">名称</th>
            <th className="py-2">状态</th>
            <th className="py-2">玩家数</th>
            <th className="py-2">创建时间</th>
            <th className="py-2">操作</th>
          </tr>
        </thead>
        <tbody>
          {filteredMatches.map((m) => {
            const rowId = m.match_id ?? m.id ?? ''
            const createdStr = m.created_at ?? m.createdAt ?? ''
            const isActive = !isTerminalStatus(m.status)
            const resourcesDestroyed = (m.resource_destroyed ?? m.resourceDestroyed) ?? false
            const canEnd = m.can_end ?? m.canEnd ?? !resourcesDestroyed
            const finishedStr = m.finished_at ?? m.finishedAt ?? ''
            const statusLabel = isActive
              ? m.status
              : resourcesDestroyed
                ? `${m.status} · 已清理`
                : finishedStr
                  ? `${m.status} · 待清理`
                  : m.status
            return (
              <tr 
                key={rowId} 
                ref={rowId === highlightedMatchId ? highlightedRowRef : null}
                className={`border-b border-slate-700 cursor-pointer transition-colors ${
                  rowId === highlightedMatchId
                    ? 'bg-cyan-900/40 ring-1 ring-cyan-500/60'
                    : 'hover:bg-slate-700/40'
                }`}
                onClick={() => navigate(isActive ? `/arena/${rowId}` : `/replay/${rowId}`)}
              >
                <td className="py-3">{m.name ?? rowId}</td>
                <td className="py-3">
                  <span className={`px-2 py-1 rounded text-xs ${
                    m.status === 'finished' ? 'bg-green-900/50 text-green-400' :
                    m.status === 'aborted' || m.status === 'error' ? 'bg-red-900/50 text-red-400' :
                    'bg-blue-900/50 text-blue-400'
                  }`}>
                    {statusLabel}
                  </span>
                </td>
                <td className="py-3">{m.player_count ?? m.playerCount ?? '-'}</td>
                <td className="py-3">{createdStr ? new Date(createdStr).toLocaleString() : '-'}</td>
                <td className="py-3 flex gap-2 items-center">
                  <button 
                    onClick={(e) => handleExport(e, rowId)}
                    className="px-3 py-1 bg-slate-600 hover:bg-cyan-600 text-white rounded text-xs transition-colors"
                  >
                    导出 JSON
                  </button>
                  {m.status === 'finished' && (
                    <button
                      onClick={(e) => handleShowAnalytics(e, rowId)}
                      className="px-3 py-1 bg-cyan-700 hover:bg-cyan-600 text-white rounded text-xs transition-colors"
                    >
                      分析
                    </button>
                  )}
                  {m.status === 'finished' && (
                    <button
                      onClick={(e) => handlePlayerCodeExport(e, rowId)}
                      disabled={exportingCodeMatchId === rowId}
                      className="px-3 py-1 bg-violet-700 hover:bg-violet-600 disabled:opacity-50 text-white rounded text-xs transition-colors"
                    >
                      {exportingCodeMatchId === rowId ? '导出中...' : '导出选手代码/复盘材料'}
                    </button>
                  )}
                  {isActive && (
                    <button 
                      onClick={(e) => {
                        e.stopPropagation()
                        navigate(`/arena/${rowId}`)
                      }}
                      className="px-3 py-1 bg-blue-600 hover:bg-blue-500 text-white rounded text-xs transition-colors"
                    >
                      进入观战
                    </button>
                  )}
                  {canEnd && (
                    <button
                      onClick={(e) => handleEndMatch(e, rowId)}
                      disabled={endingMatchId === rowId}
                      className="px-3 py-1 bg-amber-700 hover:bg-amber-600 disabled:opacity-50 text-white rounded text-xs transition-colors"
                    >
                      {endingMatchId === rowId ? '结束中...' : '结束比赛'}
                    </button>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      {filteredMatches.length === 0 && (
        <div className="text-center text-slate-400 py-8">暂无比赛数据</div>
      )}

      {/* 赛后分析弹窗 */}
      {analyticsMatchId && (
        <div
          className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4"
          onClick={() => { setAnalyticsMatchId(null); setAnalyticsData(null) }}
        >
          <div
            className="bg-slate-800 border border-slate-600 rounded-lg max-w-4xl w-full max-h-[85vh] overflow-y-auto p-6 space-y-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold">赛后分析 — {analyticsMatchId}</h3>
              <button
                onClick={() => { setAnalyticsMatchId(null); setAnalyticsData(null) }}
                className="text-slate-400 hover:text-slate-200 text-xl"
              >
                ✕
              </button>
            </div>

            {analyticsLoading && <div className="text-center text-slate-400 py-8">加载中…</div>}

            {analyticsData && (
              <>
                {/* 汇总 */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div className="bg-slate-700/50 rounded-md p-3">
                    <div className="text-xs text-slate-400">总提交</div>
                    <div className="text-xl font-semibold">{analyticsData.summary.total_submissions}</div>
                  </div>
                  <div className="bg-slate-700/50 rounded-md p-3">
                    <div className="text-xs text-slate-400">成功利用</div>
                    <div className="text-xl font-semibold text-emerald-400">{analyticsData.summary.total_successful}</div>
                  </div>
                  <div className="bg-slate-700/50 rounded-md p-3">
                    <div className="text-xs text-slate-400">最快利用</div>
                    <div className="text-xl font-semibold text-cyan-400">
                      {formatSeconds(analyticsData.summary.fastest_exploit_seconds)}
                    </div>
                  </div>
                  <div className="bg-slate-700/50 rounded-md p-3">
                    <div className="text-xs text-slate-400">有/无利用选手</div>
                    <div className="text-xl font-semibold">
                      {analyticsData.summary.players_with_exploit}/{analyticsData.summary.players_without_exploit}
                    </div>
                  </div>
                </div>

                {/* 选手分析表 */}
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-600 text-left text-slate-300">
                      <th className="py-2">选手</th>
                      <th className="py-2 text-right">首次利用</th>
                      <th className="py-2 text-right">攻陷槽位</th>
                      <th className="py-2 text-right">提交</th>
                      <th className="py-2 text-right">成功率</th>
                      <th className="py-2 text-right">得分/提交</th>
                      <th className="py-2 text-right">总分</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analyticsData.players.map((p) => (
                      <tr key={p.player_id} className="border-b border-slate-700/50">
                        <td className="py-2">
                          <div className="font-medium">{p.display_name}</div>
                          {p.model && <div className="text-xs text-slate-500">{p.model}</div>}
                        </td>
                        <td className="py-2 text-right font-mono text-cyan-300">
                          {formatSeconds(p.time_to_first_exploit_seconds)}
                        </td>
                        <td className="py-2 text-right">
                          <div className="flex flex-wrap justify-end gap-1">
                            {p.attack_slots_captured.map((s) => (
                              <span key={s} className="px-1.5 py-0.5 bg-emerald-900/50 text-emerald-300 rounded text-xs">
                                {s}
                              </span>
                            ))}
                            {p.attack_slots_captured.length === 0 && <span className="text-slate-500">—</span>}
                          </div>
                        </td>
                        <td className="py-2 text-right">{p.submissions_made}</td>
                        <td className="py-2 text-right">{(p.submission_success_rate * 100).toFixed(0)}%</td>
                        <td className="py-2 text-right font-mono">{p.score_per_submission.toFixed(0)}</td>
                        <td className="py-2 text-right font-mono font-semibold">{p.total_score}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default HistoryPage
