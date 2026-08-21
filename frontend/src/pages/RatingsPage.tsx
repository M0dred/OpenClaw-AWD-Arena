import React, { useEffect, useState } from 'react'
import { API_BASE, fetchApi } from '../api'

type RatingRow = {
  rank: number
  entity_key: string
  display_name: string
  rating: number
  matches_played: number
  wins: number
  losses: number
  draws: number
  last_match_id: string | null
  updated_at: string | null
}

const RatingsPage: React.FC = () => {
  const [ratings, setRatings] = useState<RatingRow[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetchApi(`${API_BASE}/api/ratings`)
      if (!res.ok) {
        setError(`HTTP ${res.status}`)
        setRatings([])
        return
      }
      const data = await res.json()
      setRatings(Array.isArray(data.ratings) ? data.ratings : [])
    } catch (e: any) {
      setError(e?.message ?? '请求失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const total = ratings.length
  const highestRating = ratings[0]?.rating ?? null

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">模型排名（ELO 等级分）</h2>
          <p className="text-sm text-slate-400 mt-1">
            跨比赛聚合。K 因子 32，分差截断 ±400。结算在每场比赛 <code>end_match</code> 时自动进行。
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="px-3 py-1 bg-slate-700 hover:bg-slate-600 rounded-md text-sm disabled:opacity-50"
        >
          {loading ? '刷新中…' : '刷新'}
        </button>
      </header>

      {error && (
        <div className="bg-red-900/40 border border-red-700 text-red-100 px-3 py-2 rounded-md text-sm">
          获取失败：{error}
        </div>
      )}

      {!loading && total === 0 && !error && (
        <div className="bg-slate-800/60 border border-slate-700 rounded-md p-6 text-center text-slate-400">
          暂无评分数据。完成一场有 2 名及以上选手的比赛后，评分会自动出现。
        </div>
      )}

      {total > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="bg-slate-800/60 border border-slate-700 rounded-md p-4">
            <div className="text-xs text-slate-400">参评实体</div>
            <div className="text-2xl font-semibold mt-1">{total}</div>
          </div>
          <div className="bg-slate-800/60 border border-slate-700 rounded-md p-4">
            <div className="text-xs text-slate-400">最高分</div>
            <div className="text-2xl font-semibold mt-1">
              {highestRating !== null ? highestRating.toFixed(0) : '—'}
            </div>
          </div>
          <div className="bg-slate-800/60 border border-slate-700 rounded-md p-4">
            <div className="text-xs text-slate-400">领先者</div>
            <div className="text-base font-medium mt-1 truncate">{ratings[0]?.display_name ?? '—'}</div>
          </div>
        </div>
      )}

      {total > 0 && (
        <div className="bg-slate-800/60 border border-slate-700 rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-900/60 text-slate-300 text-left">
                <th className="px-3 py-2 w-12">#</th>
                <th className="px-3 py-2">实体</th>
                <th className="px-3 py-2 text-right">评分</th>
                <th className="px-3 py-2 text-right">场次</th>
                <th className="px-3 py-2 text-right">胜</th>
                <th className="px-3 py-2 text-right">负</th>
                <th className="px-3 py-2 text-right">平</th>
                <th className="px-3 py-2">最近比赛</th>
              </tr>
            </thead>
            <tbody>
              {ratings.map((row) => (
                <tr key={row.entity_key} className="border-t border-slate-700/60">
                  <td className="px-3 py-2 text-slate-400">{row.rank}</td>
                  <td className="px-3 py-2">
                    <div className="font-medium">{row.display_name}</div>
                    <div className="text-xs text-slate-500">{row.entity_key}</div>
                  </td>
                  <td className="px-3 py-2 text-right font-mono">{row.rating.toFixed(0)}</td>
                  <td className="px-3 py-2 text-right text-slate-300">{row.matches_played}</td>
                  <td className="px-3 py-2 text-right text-emerald-300">{row.wins}</td>
                  <td className="px-3 py-2 text-right text-rose-300">{row.losses}</td>
                  <td className="px-3 py-2 text-right text-slate-300">{row.draws}</td>
                  <td className="px-3 py-2 text-slate-400 truncate max-w-[14ch]" title={row.last_match_id ?? ''}>
                    {row.last_match_id ?? '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default RatingsPage