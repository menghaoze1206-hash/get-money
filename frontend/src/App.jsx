import { Routes, Route, Link, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import DashboardPage from './pages/DashboardPage';
import FundDetailPage from './pages/FundDetailPage';
import LoginPage from './pages/LoginPage';

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <p className="page-status">加载中...</p>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function AppNav() {
  const { user, logout } = useAuth();
  return (
    <header className="app-header">
      <Link to="/" className="app-title">股息率择时信号</Link>
      {user && (
        <div className="app-nav">
          <span className="app-user">{user.username}</span>
          <button className="btn-logout" onClick={logout}>退出</button>
        </div>
      )}
    </header>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppInner />
    </AuthProvider>
  );
}

function AppInner() {
  const { loading } = useAuth();
  return (
    <div className="app">
      <AppNav />
      <main className="app-main">
        {loading ? (
          <p className="page-status">加载中...</p>
        ) : (
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
            <Route path="/fund/:id" element={<ProtectedRoute><FundDetailPage /></ProtectedRoute>} />
          </Routes>
        )}
      </main>
    </div>
  );
}
