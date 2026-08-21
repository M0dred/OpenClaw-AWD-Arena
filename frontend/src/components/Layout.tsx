import React, { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'

const Layout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const loc = useLocation()
  const active = (path: string) => loc.pathname.startsWith(path)
  
  const [apiKey, setApiKey] = useState('')
  
  useEffect(() => {
    setApiKey(localStorage.getItem('REFEREE_API_KEY') || '')
  }, [])
  
  const handleApiKeyChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value
    setApiKey(val)
    localStorage.setItem('REFEREE_API_KEY', val)
  }

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100">
      
      <header className="px-6 py-4 border-b border-slate-800 bg-slate-800/60 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
          <nav className="flex gap-4 items-center">
            <Link to="/config" className={`px-3 py-2 rounded-md text-sm font-medium ${active('/config') ? 'bg-slate-700' : 'hover:bg-slate-700'}`}>
              配置大厅
            </Link>
            <Link to="/history" className={`px-3 py-2 rounded-md text-sm font-medium ${active('/history') ? 'bg-slate-700' : 'hover:bg-slate-700'}`}>
              历史比赛
            </Link>
            <Link to="/loops" className={`px-3 py-2 rounded-md text-sm font-medium ${active('/loops') ? 'bg-slate-700' : 'hover:bg-slate-700'}`}>
              循环比赛
            </Link>
            <Link to="/ratings" className={`px-3 py-2 rounded-md text-sm font-medium ${active('/ratings') ? 'bg-slate-700' : 'hover:bg-slate-700'}`}>
              模型排名
            </Link>
          </nav>
          <div className="flex items-center gap-2">
            <span className="text-sm text-slate-400">API Key:</span>
            <input 
              type="password" 
              value={apiKey}
              onChange={handleApiKeyChange}
              placeholder="Referee API Key" 
              className="px-2 py-1 rounded-md bg-slate-800 border border-slate-700 text-sm focus:outline-none focus:border-cyan-500"
            />
          </div>
        </div>
      </header>
      <main className="p-6 max-w-7xl mx-auto">{children}</main>
    </div>
  )
}

export default Layout
