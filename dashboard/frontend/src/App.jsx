import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import FriendDetail from './pages/FriendDetail'
import NewFriend from './pages/NewFriend'

function App() {
  return (
    <Router>
      <div className="min-h-screen bg-gray-900">
        <header className="bg-gray-800 shadow-lg border-b border-gray-700">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex items-center justify-between h-16">
              <div className="flex items-center">
                <Link to="/" className="flex items-center">
                  <span className="text-2xl mr-2">🤖</span>
                  <h1 className="text-xl font-bold text-white">Hermes Friends</h1>
                </Link>
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
          </Routes>
        </main>
      </div>
    </Router>
  )
}

export default App
