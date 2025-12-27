
import React, { useState, useRef, useEffect } from 'react';
import { 
  Settings, Plus, MessageSquare, Send, Upload, LayoutGrid, 
  Database, Loader2, Menu, Sparkles, LogOut, User as UserIcon
} from 'lucide-react';
import { generateSqlAndAnalysis, generateSessionTitle } from './services/geminiService';
import SettingsModal from './components/SettingsModal';
import MessageBubble from './components/MessageBubble';
import AuthPage from './components/AuthPage';
import { Session, Message, AppSettings, AVAILABLE_MODELS, User } from './types';
import { translations } from './i18n';
import { api } from './services/api';

function App() {
  // Settings with Defaults
  const [settings, setSettings] = useState<AppSettings>(() => {
     const savedSettings = localStorage.getItem('app_settings');
     if (savedSettings) return JSON.parse(savedSettings);

     return {
      language: 'zh',
      model: 'gemini-2.5-flash',
      customBaseUrl: '',
      customApiKey: '',
      useSimulationMode: true, // Default to true until file is uploaded
      dbConfig: {
        type: 'postgres',
        host: 'localhost',
        port: '5432',
        database: '',
        user: '',
        password: '',
        uploadedPath: ''
      }
    };
  });

  // Save settings on change
  useEffect(() => {
    localStorage.setItem('app_settings', JSON.stringify(settings));
  }, [settings]);

  // Auth State
  const [user, setUser] = useState<User | null>(() => {
    const savedUser = localStorage.getItem('current_user');
    return savedUser ? JSON.parse(savedUser) : null;
  });

  const t = translations[settings.language];

  // --- App State ---
  const [sessions, setSessions] = useState<Session[]>([{
    id: '1', title: translations[settings.language].newAnalysis, messages: [], updatedAt: Date.now()
  }]);
  const [currentSessionId, setCurrentSessionId] = useState<string>('1');
  const [input, setInput] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  
  const scrollRef = useRef<HTMLDivElement>(null);
  const currentSession = sessions.find(s => s.id === currentSessionId)!;

  // --- Effects ---
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [currentSession?.messages, isProcessing]);

  // --- Auth Handlers ---
  const handleLogin = (newUser: User) => {
    setUser(newUser);
    localStorage.setItem('current_user', JSON.stringify(newUser));
  };

  const handleLogout = () => {
    setUser(null);
    localStorage.removeItem('current_user');
    // Reset sessions on logout
    setSessions([{
        id: '1', title: t.newAnalysis, messages: [], updatedAt: Date.now()
    }]);
  };

  const handleLanguageChange = (lang: 'en' | 'zh') => {
      setSettings(prev => ({...prev, language: lang}));
  };


  // --- Logic Handlers ---
  const handleNewSession = () => {
    const newId = Date.now().toString();
    setSessions(prev => [{
      id: newId,
      title: t.newAnalysis,
      messages: [],
      updatedAt: Date.now()
    }, ...prev]);
    setCurrentSessionId(newId);
    if (window.innerWidth < 768) setIsSidebarOpen(false);
  };

  const handleSendMessage = async () => {
    if (!input.trim() || isProcessing) return;
    
    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input,
      timestamp: Date.now()
    };

    const updatedMessages = [...currentSession.messages, userMsg];
    const isFirstMessage = currentSession.messages.length === 0;

    setSessions(prev => prev.map(s => s.id === currentSessionId ? { ...s, messages: updatedMessages } : s));
    setInput('');
    setIsProcessing(true);

    if (isFirstMessage) {
      generateSessionTitle(userMsg.content, settings.language).then(newTitle => {
        setSessions(prev => prev.map(s => s.id === currentSessionId ? { ...s, title: newTitle } : s));
      });
    }

    try {
      const response = await generateSqlAndAnalysis(
        userMsg.content, 
        currentSession.messages,
        settings
      );

      const botMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'model',
        content: response.text,
        sqlQuery: response.sql,
        executionResult: response.result,
        timestamp: Date.now()
      };

      setSessions(prev => prev.map(s => s.id === currentSessionId ? { 
        ...s, 
        messages: [...updatedMessages, botMsg]
      } : s));

    } catch (error) {
      console.error(error);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    setIsProcessing(true); // Show loader during analysis
    
    try {
        // 1. Upload the file
        const result = await api.uploadFile(file);
        
        // 2. Update settings locally first so we can use them immediately
        const newSettings = {
          ...settings,
          useSimulationMode: false,
          dbConfig: {
            ...settings.dbConfig,
            type: 'sqlite' as const,
            uploadedPath: result.file_path,
            database: result.filename,
            fileId: result.id
          }
        };
        setSettings(newSettings);

        // 3. Trigger Auto-Summary using the uploaded file ID
        // Note: We use result.id directly because state update is async
        let summaryText = "";
        try {
           summaryText = await api.getDbSummary(result.id, settings.customApiKey);
        } catch (sumErr) {
           console.error("Summary generation failed", sumErr);
           summaryText = settings.language === 'zh' 
             ? "文件上传成功，但自动分析失败。您现在可以提问了。" 
             : "File uploaded, but summary failed. You can ask questions now.";
        }

        // 4. Add the summary as a message from the bot
        const botMsg: Message = {
          id: Date.now().toString(),
          role: 'model',
          content: summaryText,
          timestamp: Date.now()
        };

        setSessions(prev => prev.map(s => s.id === currentSessionId ? { 
          ...s, 
          messages: [...s.messages, botMsg] 
        } : s));
        
        // Also update title if it's a new session
        if (currentSession.messages.length === 0) {
           setSessions(prev => prev.map(s => s.id === currentSessionId ? { ...s, title: file.name } : s));
        }

    } catch (error: any) {
        alert(settings.language === 'zh' ? `上传失败: ${error.message}` : `Upload failed: ${error.message}`);
    } finally {
        setIsUploading(false);
        setIsProcessing(false);
        // Clear the input value so the same file can be selected again if needed
        e.target.value = '';
    }
  };

  // --- Render Auth Page if not logged in ---
  if (!user) {
    return (
      <AuthPage 
        onLogin={handleLogin} 
        language={settings.language} 
        onLanguageChange={handleLanguageChange}
      />
    );
  }

  // --- Render Main App ---
  return (
    <div className="flex h-screen bg-background text-text overflow-hidden">
      
      {/* Sidebar */}
      <aside className={`${isSidebarOpen ? 'w-64' : 'w-0'} bg-[#1E1F20] border-r border-secondary transition-all duration-300 flex flex-col shrink-0 overflow-hidden`}>
        <div className="p-4 flex items-center gap-3 border-b border-secondary h-16 min-w-64">
          <div className="w-8 h-8 rounded-lg bg-accent flex items-center justify-center text-white font-bold shadow-lg shadow-blue-900/20">
            <Sparkles size={18} />
          </div>
          <span className="font-semibold text-lg tracking-tight truncate">DataNexus AI</span>
        </div>

        <div className="p-3 min-w-64">
          <button 
            onClick={handleNewSession}
            className="w-full flex items-center gap-2 px-4 py-3 bg-[#2a2b2d] hover:bg-[#353638] rounded-full text-sm font-medium transition-colors text-primary"
          >
            <Plus size={18} /> {t.newAnalysis}
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-1 min-w-64">
          <div className="text-xs font-medium text-subtext px-4 py-2 uppercase tracking-wider">{t.recent}</div>
          {sessions.map(session => (
            <button
              key={session.id}
              onClick={() => setCurrentSessionId(session.id)}
              className={`w-full text-left px-4 py-3 rounded-lg text-sm flex items-center gap-3 transition-colors ${
                session.id === currentSessionId 
                  ? 'bg-[#004A77] text-white' 
                  : 'text-subtext hover:bg-[#2a2b2d] hover:text-white'
              }`}
            >
              <MessageSquare size={16} />
              <span className="truncate">{session.title}</span>
            </button>
          ))}
        </div>

        {/* User Profile & Settings Area */}
        <div className="p-3 border-t border-secondary min-w-64 bg-[#161718]">
          <div className="flex items-center gap-3 px-3 py-3 mb-2 rounded-lg bg-[#2a2b2d]/50">
             <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-purple-500 to-pink-500 flex items-center justify-center text-xs font-bold text-white shrink-0">
                {user.name.charAt(0).toUpperCase()}
             </div>
             <div className="overflow-hidden">
                <div className="text-sm font-medium truncate">{user.name}</div>
                <div className="text-xs text-subtext truncate">{user.email}</div>
             </div>
          </div>
          
          <div className="grid grid-cols-2 gap-1">
             <button 
                onClick={() => setIsSettingsOpen(true)}
                className="flex items-center justify-center gap-2 px-3 py-2 text-xs font-medium text-subtext hover:text-white hover:bg-[#2a2b2d] rounded-lg transition-colors"
              >
                <Settings size={14} /> {t.settingsTitle}
              </button>
              <button 
                onClick={handleLogout}
                className="flex items-center justify-center gap-2 px-3 py-2 text-xs font-medium text-subtext hover:text-red-400 hover:bg-red-400/10 rounded-lg transition-colors"
              >
                <LogOut size={14} /> {t.logout}
              </button>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col h-full relative">
        
        {/* Header */}
        <header className="h-16 border-b border-secondary flex items-center justify-between px-6 bg-surface z-10">
          <div className="flex items-center gap-4">
            <button 
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              className="text-subtext hover:text-white transition-colors"
            >
              <Menu size={20} />
            </button>
            <div className="flex items-center gap-2 bg-[#2a2b2d] rounded-lg p-1">
              <span className="text-xs text-subtext pl-2">{t.model}:</span>
              <select 
                value={settings.model}
                onChange={(e) => setSettings(s => ({...s, model: e.target.value}))}
                className="bg-transparent text-sm text-text font-medium py-1 px-2 outline-none cursor-pointer"
              >
                {AVAILABLE_MODELS.map(m => (
                  <option key={m.id} value={m.id}>{m.name}</option>
                ))}
              </select>
            </div>
          </div>
          
          <div className="flex items-center gap-2 text-xs text-subtext">
             <span className={`w-2 h-2 rounded-full ${settings.dbConfig.uploadedPath ? 'bg-blue-500' : 'bg-gray-500'}`} />
             {settings.dbConfig.uploadedPath 
               ? (settings.language === 'zh' ? '已连接云端数据库' : 'Cloud DB Connected') 
               : t.envConnected}
          </div>
        </header>

        {/* Chat Area */}
        <div className="flex-1 overflow-y-auto" ref={scrollRef}>
          {currentSession?.messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center p-8 text-center text-subtext">
              <div className="w-16 h-16 bg-[#2a2b2d] rounded-2xl flex items-center justify-center mb-6 text-accent">
                <Sparkles size={32} />
              </div>
              <h1 className="text-2xl font-semibold text-text mb-2">
                 {t.greeting}, {user.name.split(' ')[0]}
              </h1>
              <p className="max-w-md mb-8">
                {t.greetingSub}
              </p>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-2xl w-full">
                <button 
                  onClick={() => setInput(settings.language === 'zh' ? "按月显示各地区总销售额的柱状图" : "Show total sales by region for the last month as a bar chart")} 
                  className="p-4 bg-[#1E1F20] border border-secondary rounded-xl hover:bg-[#2a2b2d] hover:border-accent text-left transition-all group"
                >
                  <span className="font-medium text-text block mb-1 group-hover:text-accent transition-colors">{t.suggestion1}</span>
                  <span className="text-xs">{t.suggestion1Sub}</span>
                </button>
                <button 
                   onClick={() => setInput(settings.language === 'zh' ? "识别前3名最有价值客户" : "Identify the top 3 customers by lifetime value")} 
                   className="p-4 bg-[#1E1F20] border border-secondary rounded-xl hover:bg-[#2a2b2d] hover:border-accent text-left transition-all group"
                >
                  <span className="font-medium text-text block mb-1 group-hover:text-accent transition-colors">{t.suggestion2}</span>
                  <span className="text-xs">{t.suggestion2Sub}</span>
                </button>
              </div>
            </div>
          ) : (
            <div className="max-w-4xl mx-auto py-6">
              {currentSession?.messages.map(msg => (
                <MessageBubble key={msg.id} message={msg} language={settings.language} />
              ))}
              {isProcessing && (
                <div className="flex gap-4 p-6 bg-[#1E1F20]/50">
                  <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-blue-500 to-cyan-400 flex items-center justify-center shrink-0">
                    <Loader2 size={18} className="animate-spin text-white" />
                  </div>
                  <div className="flex flex-col gap-2">
                    <div className="text-sm text-subtext animate-pulse">{t.processing}</div>
                    <div className="h-4 w-32 bg-secondary/50 rounded animate-pulse"></div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Input Area */}
        <div className="p-4 bg-background border-t border-secondary">
          <div className="max-w-4xl mx-auto bg-[#1E1F20] rounded-2xl border border-secondary p-2 flex flex-col gap-2 focus-within:ring-1 focus-within:ring-accent transition-all">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if(e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSendMessage();
                }
              }}
              placeholder={t.inputPlaceholder}
              className="w-full bg-transparent border-none outline-none text-text p-3 resize-none max-h-32 min-h-[50px]"
              rows={1}
            />
            <div className="flex items-center justify-between px-2 pb-1">
              <div className="flex items-center gap-2">
                <label className={`p-2 hover:bg-[#2a2b2d] rounded-lg cursor-pointer transition-colors relative group ${isUploading ? 'opacity-50 pointer-events-none' : 'text-subtext'}`}>
                  <input type="file" className="hidden" accept=".csv,.xlsx,.db,.sqlite" onChange={handleFileUpload} />
                  {isUploading ? <Loader2 size={20} className="animate-spin" /> : <Database size={20} />}
                  <span className="absolute -top-8 left-1/2 -translate-x-1/2 bg-black px-2 py-1 rounded text-xs opacity-0 group-hover:opacity-100 whitespace-nowrap pointer-events-none">
                    {t.upload}
                  </span>
                </label>
              </div>
              <button 
                onClick={handleSendMessage}
                disabled={!input.trim() || isProcessing}
                className={`p-2 rounded-lg transition-colors ${
                  input.trim() && !isProcessing
                    ? 'bg-text text-background hover:bg-white' 
                    : 'bg-[#2a2b2d] text-secondary cursor-not-allowed'
                }`}
              >
                <Send size={20} />
              </button>
            </div>
          </div>
          <div className="text-center mt-2">
             <p className="text-[10px] text-subtext">
               {t.disclaimer}
             </p>
          </div>
        </div>

      <SettingsModal 
        isOpen={isSettingsOpen} 
        onClose={() => setIsSettingsOpen(false)}
        settings={settings}
        onSave={(newSettings) => {
          setSettings(newSettings);
          setIsSettingsOpen(false);
        }}
      />
      </main>
    </div>
  );
}

export default App;
