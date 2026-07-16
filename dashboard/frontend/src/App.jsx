import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import FriendDetail from './pages/FriendDetail'
import NewFriend from './pages/NewFriend'
import BudgetGroups from './pages/BudgetGroups'
import Usage from './pages/Usage'

function NavLink({ to, children }) {
  const location = useLocation()
  const isActive = location.pathname === to
  return (
    <Link
      to={to}
      className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
        isActive ? 'bg-gray-700 text-white' : 'text-gray-400 hover:text-white hover:bg-gray-700'
      }`}
    >
      {children}
    </Link>
  )
}

function App() {
  return (
    <Router>
      <div className="min-h-screen bg-gray-900">
        <header className="bg-gray-800 shadow-lg border-b border-gray-700">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex items-center justify-between h-16">
              <div className="flex items-center space-x-6">
                <Link to="/" className="flex items-center">
                  <span className="text-2xl mr-2">🤖</span>
                  <h1 className="text-xl font-bold text-white">Hermes</h1>
                </Link>
                <nav className="flex items-center space-x-1">
                  <NavLink to="/">Friends</NavLink>
                  <NavLink to="/budget-groups">Budget Groups</NavLink>
                  <NavLink to="/usage">Usage</NavLink>
                </nav>
              </div>
              <div className="flex items-center space-x-4">
                <Link
                  to="/friends/new"
                  className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors font-medium"
                >
                  + New Friend
                </Link>
              </div>
            </div>
          </div>
        </header>

        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/friends/new" element={<NewFriend />} />
            <Route path="/friends/:name" element={<FriendDetail />} />
            <Route path="/budget-groups" element={<BudgetGroups />} />
            <Route path="/usage" element={<Usage />} />
          </Routes>
        </main>
      </div>
    </Router>
  )
}

export default App
