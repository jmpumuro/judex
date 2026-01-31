import { FC } from 'react'
import { NavLink } from 'react-router-dom'
import { Video, Radio, Clock, BarChart3, Settings } from 'lucide-react'

const navItems = [
  { path: '/pipeline', label: 'PIPELINE', icon: Video },
  { path: '/live-feed', label: 'LIVE FEED', icon: Radio },
  { path: '/live-events', label: 'LIVE EVENTS', icon: Clock },
  { path: '/analytics', label: 'ANALYTICS', icon: BarChart3 },
  { path: '/settings', label: 'SETTINGS', icon: Settings },
]

const Sidebar: FC = () => {
  return (
    <aside className="sidebar group">
      {/* Logo */}
      <div className="sidebar-brand">
        <span className="sidebar-brand-icon group-hover:hidden">◆</span>
        <span className="sidebar-brand-text hidden group-hover:block">JUDEX</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-5">
        {navItems.map(({ path, label, icon: Icon }) => (
          <NavLink
            key={path}
            to={path}
            className={({ isActive }) =>
              `sidebar-link ${isActive ? 'active' : ''}`
            }
            data-label={label}
          >
            <span className="sidebar-icon">
              <Icon size={18} />
            </span>
            <span className="sidebar-text">{label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-4 py-4 border-t border-gray-800 text-xs text-gray-600">
        <div className="sidebar-brand-icon group-hover:hidden text-center">v1</div>
        <div className="hidden group-hover:block">
          <p>Judex v2.0.0</p>
          <p className="mt-1">Vision Evaluation</p>
        </div>
      </div>
    </aside>
  )
}

export default Sidebar
