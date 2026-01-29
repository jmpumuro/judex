import { FC, ReactNode } from 'react'
import Sidebar from './Sidebar'

interface LayoutProps {
  children: ReactNode
}

const Layout: FC<LayoutProps> = ({ children }) => {
  return (
    <div className="h-screen bg-black text-white flex overflow-hidden">
      <Sidebar />
      <main className="main-content">
        {children}
      </main>
    </div>
  )
}

export default Layout
