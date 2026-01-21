
import React, { useState } from 'react';
import { Mail, Lock, User as UserIcon, ArrowRight, Loader2, Sparkles, ServerCrash } from 'lucide-react';
import { User } from '../types';
import { translations } from '../i18n';
import { api } from '../services/api';

interface Props {
  onLogin: (user: User) => void;
  language: 'en' | 'zh';
  onLanguageChange: (lang: 'en' | 'zh') => void;
}

const AuthPage: React.FC<Props> = ({ onLogin, language, onLanguageChange }) => {
  const [isLogin, setIsLogin] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  
  const t = translations[language];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    // Simple validation
    if (!email.includes('@')) {
      setError(language === 'zh' ? '邮箱格式无效' : 'Invalid email format');
      setIsLoading(false);
      return;
    }

    try {
        let user: User;
        
        if (isLogin) {
            // Login Flow
            user = await api.login(email, password);
        } else {
            // Register Flow
            if (!name.trim()) {
                throw new Error(language === 'zh' ? '请输入姓名' : 'Full Name is required');
            }
            user = await api.register(email, password, name);
        }

        onLogin(user);

    } catch (err: any) {
        console.error("Auth error:", err);
        let msg = err.message || "Authentication failed";
        
        // Translate common backend errors
        if (msg === "Incorrect username or password") {
            msg = language === 'zh' ? "账号或密码错误" : "Incorrect email or password";
        } else if (msg.includes("already registered")) {
            msg = language === 'zh' ? "该邮箱已被注册" : "Email already registered";
        } else if (msg.includes("Could not connect")) {
             msg = language === 'zh' ? "连接后端失败，请确认 Python 服务已启动 (port 8000)" : "Could not connect to backend. Is Python running on port 8000?";
        }
        
        setError(msg);
    } finally {
        setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center p-4 relative overflow-hidden">
      
      {/* Background Decor */}
      <div className="absolute top-0 left-0 w-full h-full overflow-hidden z-0 pointer-events-none">
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-blue-600/10 rounded-full blur-[100px]"></div>
        <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-purple-600/10 rounded-full blur-[100px]"></div>
      </div>

      <div className="z-10 w-full max-w-md">
        
        {/* Logo Area */}
        <div className="flex flex-col items-center mb-8">
           <div className="w-12 h-12 rounded-xl bg-gradient-to-tr from-blue-600 to-cyan-500 flex items-center justify-center text-white font-bold text-2xl mb-4 shadow-lg shadow-blue-900/20">
            <Sparkles size={24} />
          </div>
          <h1 className="text-3xl font-bold text-text mb-2">DataNexus AI</h1>
          <p className="text-subtext text-center text-sm max-w-xs">{t.authDesc}</p>
        </div>

        {/* Card */}
        <div className="bg-surface border border-secondary rounded-2xl p-8 shadow-2xl backdrop-blur-sm">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-semibold text-text">
              {isLogin ? t.welcomeBack : t.createAccount}
            </h2>
            
            <button 
              onClick={() => onLanguageChange(language === 'en' ? 'zh' : 'en')}
              className="text-xs text-subtext hover:text-white border border-secondary rounded px-2 py-1 transition-colors"
            >
              {language === 'en' ? '中文' : 'EN'}
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            
            {!isLogin && (
              <div className="space-y-1">
                <label className="text-xs font-medium text-subtext ml-1">{t.fullName}</label>
                <div className="relative">
                  <UserIcon className="absolute left-3 top-1/2 -translate-y-1/2 text-subtext" size={18} />
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="w-full bg-[#131314] border border-secondary rounded-lg py-2.5 pl-10 pr-4 text-text text-sm focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent transition-all"
                    placeholder="John Doe"
                    required={!isLogin}
                  />
                </div>
              </div>
            )}

            <div className="space-y-1">
              <label className="text-xs font-medium text-subtext ml-1">{t.email}</label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-subtext" size={18} />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full bg-[#131314] border border-secondary rounded-lg py-2.5 pl-10 pr-4 text-text text-sm focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent transition-all"
                  placeholder="name@example.com"
                  required
                />
              </div>
            </div>

            <div className="space-y-1">
               <label className="text-xs font-medium text-subtext ml-1">{t.password}</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-subtext" size={18} />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full bg-[#131314] border border-secondary rounded-lg py-2.5 pl-10 pr-4 text-text text-sm focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent transition-all"
                  placeholder={language === 'zh' ? "设置密码 (本地明文存储)" : "Enter password"}
                  required
                />
              </div>
            </div>

            {error && (
              <div className="flex items-start gap-2 text-red-400 text-xs bg-red-400/10 p-3 rounded border border-red-400/20">
                <ServerCrash size={14} className="shrink-0 mt-0.5" />
                <span className="flex-1 text-left">{error}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={isLoading}
              className="w-full bg-accent hover:bg-blue-600 text-white font-medium py-2.5 rounded-lg transition-all flex items-center justify-center gap-2 mt-2"
            >
              {isLoading ? (
                <Loader2 size={20} className="animate-spin" />
              ) : (
                <>
                  {isLogin ? t.signIn : t.signUp}
                  <ArrowRight size={18} />
                </>
              )}
            </button>
          </form>

          <div className="mt-6 text-center">
            <p className="text-sm text-subtext">
              {isLogin ? t.noAccount : t.hasAccount}{' '}
              <button
                onClick={() => {
                   setIsLogin(!isLogin);
                   setError('');
                }}
                className="text-accent hover:underline font-medium"
              >
                {isLogin ? t.signUp : t.signIn}
              </button>
            </p>
          </div>
          
          <div className="mt-4 pt-4 border-t border-secondary/50 text-center flex flex-col gap-1">
              <p className="text-[10px] text-green-400 font-mono">
                 Backend: Localhost:8000 (SQLite)
              </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AuthPage;
