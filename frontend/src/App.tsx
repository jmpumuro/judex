import { FC } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from '@/components/layout/Layout'
import Pipeline from '@/pages/Pipeline'
import LiveFeed from '@/pages/LiveFeed'
import LiveEvents from '@/pages/LiveEvents'
import Analytics from '@/pages/Analytics'
import Settings from '@/pages/Settings'

const App: FC = () => {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/pipeline" replace />} />
        <Route path="/pipeline" element={<Pipeline />} />
        <Route path="/live-feed" element={<LiveFeed />} />
        <Route path="/live-events" element={<LiveEvents />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/pipeline" replace />} />
      </Routes>
    </Layout>
  )
}

export default App
