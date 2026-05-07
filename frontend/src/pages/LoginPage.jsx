import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Navigate } from 'react-router-dom';
import { login, register } from '../api';
import { useAuth } from '../context/AuthContext';

export default function LoginPage() {
  const { user, loading, loginUser } = useAuth();
  const navigate = useNavigate();

  if (!loading && user) return <Navigate to="/" replace />;
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isRegister, setIsRegister] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit(e) {
    e.preventDefault();
    if (!username || !password) {
      setError('用户名和密码不能为空');
      return;
    }
    setError('');
    try {
      const fn = isRegister ? register : login;
      const { token, user } = await fn(username, password);
      loginUser(token, user);
      navigate('/', { replace: true });
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="login-page">
      <form className="login-form" onSubmit={handleSubmit}>
        <h1>股息率择时信号</h1>
        <p className="login-subtitle">{isRegister ? '注册新账号' : '登录'}</p>

        {error && <p className="login-error">{error}</p>}

        <label htmlFor="login-username">用户名</label>
        <input
          id="login-username"
          type="text"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="输入用户名"
          autoFocus
        />

        <label htmlFor="login-password">密码</label>
        <input
          id="login-password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="输入密码"
        />

        <button type="submit">{isRegister ? '注册' : '登录'}</button>

        <p className="login-toggle">
          {isRegister ? (
            <>已有账号？ <a href="#" onClick={(e) => { e.preventDefault(); setIsRegister(false); }}>去登录</a></>
          ) : (
            <>没有账号？ <a href="#" onClick={(e) => { e.preventDefault(); setIsRegister(true); }}>去注册</a></>
          )}
        </p>
      </form>
    </div>
  );
}
