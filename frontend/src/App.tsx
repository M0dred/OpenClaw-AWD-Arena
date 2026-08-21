import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import ConfigPage from './pages/ConfigPage'
import ArenaPage from './pages/ArenaPage'
import HistoryPage from './pages/HistoryPage'
import LoopMatchesPage from './pages/LoopMatchesPage'
import ReplayPage from './pages/ReplayPage'
import RatingsPage from './pages/RatingsPage'

const App: React.FC = () => {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/config" />} />
        <Route path="/config" element={<ConfigPage />} />
        <Route path="/arena/:matchId" element={<ArenaPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/loops" element={<LoopMatchesPage />} />
        <Route path="/replay/:matchId" element={<ReplayPage />} />
        <Route path="/ratings" element={<RatingsPage />} />
      </Routes>
    </Layout>
  )
}

export default App
