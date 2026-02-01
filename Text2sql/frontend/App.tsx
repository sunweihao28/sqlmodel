
import React, { useState, useRef, useEffect } from 'react';
import { 
  Settings, Plus, MessageSquare, Send, Upload, LayoutGrid, 
  Database, Loader2, Menu, Sparkles, LogOut, User as UserIcon,
  Bot, Trash2, BookOpen
} from 'lucide-react';
import { generateSessionTitle } from './services/geminiService';
import SettingsModal from './components/SettingsModal';
import KnowledgeBaseModal from './components/KnowledgeBaseModal'; // Import
import MessageBubble from './components/MessageBubble';
import AuthPage from './components/AuthPage';
import { Session, Message, AppSettings, User, AVAILABLE_MODELS, SqlResult, ChartType } from './types';
import { translations } from './i18n';
import { api } from './services/api';

function App() {
  // Settings with Defaults
  const [settings, setSettings] = useState<AppSettings>(() => {
     const savedSettings = localStorage.getItem('app_settings');
     if (savedSettings) {
       const parsed = JSON.parse(savedSettings);
       const validModel = AVAILABLE_MODELS.some(m => m.value === parsed.model)
         ? parsed.model
         : 'gemini-2.5-flash';
       // Ensure useRag exists
       return { ...parsed, model: validModel, useRag: parsed.useRag ?? false };
     }

     return {
      language: 'zh',
      model: 'gemini-2.5-flash',
      customBaseUrl: '',
      customApiKey: '',
      useSimulationMode: true,
      useRag: false, // Default RAG off
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

  useEffect(() => {
    localStorage.setItem('app_settings', JSON.stringify(settings));
  }, [settings]);

  // Auth State
  const [user, setUser] = useState<User | null>(() => {
    try {
      const savedUser = localStorage.getItem('current_user');
      if (savedUser) {
        const parsedUser = JSON.parse(savedUser);
        if (parsedUser && parsedUser.token && parsedUser.email) {
          return parsedUser;
        }
      }
    } catch (error) {
      console.warn('Failed to restore user session:', error);
      localStorage.removeItem('current_user');
    }
    return null;
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
  const [isKbOpen, setIsKbOpen] = useState(false); // Knowledge Base Modal

  const [isStreaming, setIsStreaming] = useState(false);
  const [streamController, setStreamController] = useState<AbortController | null>(null);
  
  const scrollRef = useRef<HTMLDivElement>(null);
  const currentSession = sessions.find(s => s.id === currentSessionId) || sessions[0];

  // --- Helpers for Backend Sync ---
  const loadSessions = async () => {
    try {
      const remoteSessions = await api.getSessions();
      const formattedRemoteSessions: Session[] = remoteSessions.map((s: any) => ({
        id: s.id,
        title: s.title,
        updatedAt: s.updatedAt,
        fileId: s.fileId,
        messages: []
      }));
      
      const placeholderSession: Session = {
        id: '1', 
        title: t.newAnalysis, 
        messages: [], 
        updatedAt: Date.now()
      };

      setSessions([placeholderSession, ...formattedRemoteSessions]);
      setCurrentSessionId('1');
      setSettings(prev => ({
        ...prev,
        dbConfig: { ...prev.dbConfig, fileId: undefined, uploadedPath: '' }
      }));

    } catch (e) {
      console.error("Failed to load sessions:", e);
      setSessions([{
        id: '1', title: t.newAnalysis, messages: [], updatedAt: Date.now()
      }]);
      setCurrentSessionId('1');
    }
  };

  const loadSessionMessages = async (sessionId: string) => {
    if (sessionId === '1') return;
    setIsProcessing(true);
    try {
      const msgs = await api.getSessionMessages(sessionId);
      const hydratedMsgs = msgs.map((msg: any) => {
          let sqlQuery = undefined;
          let executionResult = undefined;

          if (msg.steps && Array.isArray(msg.steps)) {
              const sqlStep = msg.steps.find((s: any) => s.tool === 'sql_inter');
              if (sqlStep && sqlStep.input) {
                  sqlQuery = sqlStep.input;
              }
          }

          if (msg.vizConfig) {
              executionResult = {
                  columns: msg.vizConfig.data && msg.vizConfig.data.length > 0 ? Object.keys(msg.vizConfig.data[0]) : [],
                  data: msg.vizConfig.data || [],
                  chartTypeSuggestion: msg.vizConfig.type,
                  summary: msg.vizConfig.title || 'Visualization',
                  visualizationConfig: msg.vizConfig,
                  displayType: msg.vizConfig.displayType || 'both'
              };
          }

          return { ...msg, sqlQuery, executionResult };
      });
      setSessions(prev => prev.map(s => s.id === sessionId ? { ...s, messages: hydratedMsgs } : s));
    } catch (e) {
      console.error("Failed to load messages:", e);
    } finally {
      setIsProcessing(false);
    }
  };

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [currentSession?.messages, isProcessing]);

  useEffect(() => {
    const validateTokenOnLoad = async () => {
      if (user) {
        loadSessions();
      }
      if (!user) return;
      try {
        const response = await fetch('http://localhost:8000/api/auth/me', {
          method: 'GET',
          headers: {
            'Authorization': `Bearer ${user.token}`,
          },
        });
        if (!response.ok) {
          localStorage.removeItem('current_user');
          setUser(null);
          setSessions([{
            id: '1', title: t.newAnalysis, messages: [], updatedAt: Date.now()
          }]);
          setCurrentSessionId('1');
        }
      } catch (error) {
        console.warn('Token validation failed due to network error', error);
      }
    };
    validateTokenOnLoad();
  }, [user]);

  useEffect(() => {
    if (currentSessionId && currentSessionId !== '1') {
        const session = sessions.find(s => s.id === currentSessionId);
        if (session && session.messages.length === 0) {
            loadSessionMessages(currentSessionId);
        }
        if (session && session.fileId) {
            setSettings(prev => ({
                ...prev,
                dbConfig: { ...prev.dbConfig, fileId: session.fileId }
            }));
        }
    } else if (currentSessionId === '1') {
        setSettings(prev => ({
            ...prev,
            dbConfig: { ...prev.dbConfig, fileId: undefined, uploadedPath: '' }
        }));
    }
  }, [currentSessionId]);

  const handleLogin = (newUser: User) => {
    setUser(newUser);
    localStorage.setItem('current_user', JSON.stringify(newUser));
  };

  const handleLogout = () => {
    setUser(null);
    localStorage.removeItem('current_user');
    setSessions([{
        id: '1', title: t.newAnalysis, messages: [], updatedAt: Date.now()
    }]);
    setCurrentSessionId('1');
    setSettings(prev => ({
        ...prev,
        dbConfig: { ...prev.dbConfig, fileId: undefined, uploadedPath: '' }
    }));
  };

  const handleLanguageChange = (lang: 'en' | 'zh') => {
      setSettings(prev => ({...prev, language: lang}));
  };

  const handleDeleteSession = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (sessionId === '1') return;
    if (!window.confirm(settings.language === 'zh' ? '确定要删除此会话吗？' : 'Delete this session?')) return;
    if (sessionId === currentSessionId) {
        setCurrentSessionId('1');
    }
    setSessions(prev => prev.filter(s => s.id !== sessionId));
    try {
        await api.deleteSession(sessionId);
    } catch (error) {
        console.error("Failed to delete session:", error);
    }
  };

  const stopStreaming = () => {
    if (streamController) {
      streamController.abort();
      setStreamController(null);
      setIsStreaming(false);
      setIsProcessing(false);
      setSessions(prev => prev.map(s => s.id === currentSessionId ? {
        ...s,
        messages: s.messages.map((m, index, arr) => {
          if (m.role === 'model' && index === arr.length - 1) {
            return { ...m, content: m.content + "\n\n*[生成已中断]*", status: 'error' as const };
          }
          if (m.id === currentSessionId + '_summary') {
            return { ...m, content: m.content + "\n\n*[生成已中断]*" };
          }
          return m;
        })
      } : s));
    }
  };

  const handleNewSession = async () => {
    setCurrentSessionId('1');
    if (window.innerWidth < 768) setIsSidebarOpen(false);
  };

  const handleSendMessage = async () => {
    if (!input.trim() || isProcessing || isStreaming) return;
    
    if (!settings.dbConfig.fileId) {
      alert(settings.language === 'zh' ? '请先上传数据库文件' : 'Please upload a database file first');
      return;
    }
    
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

    if (isFirstMessage) {
      generateSessionTitle(userMsg.content, settings.language).then(newTitle => {
        if (currentSessionId !== '1') {
             setSessions(prev => prev.map(s => s.id === currentSessionId ? { ...s, title: newTitle } : s));
        }
      });
    }

    const botMsgId = (Date.now() + 1).toString();
    const initialContent = settings.language === 'zh' 
      ? "🤔 正在分析您的问题，思考最佳解决方案..." 
      : "🤔 Analyzing your question and thinking about the best solution...";
    const botMsg: Message = {
      id: botMsgId,
      role: 'model',
      content: initialContent,
      status: 'thinking',
      timestamp: Date.now()
    };

    setSessions(prev => prev.map(s => s.id === currentSessionId ? { 
      ...s, 
      messages: [...updatedMessages, botMsg]
    } : s));

    if (streamController) {
      streamController.abort();
    }

    const controller = new AbortController();
    setStreamController(controller);
    setIsStreaming(true);
    setIsProcessing(true);

    let contentText = initialContent;
    const toolStatus: Record<string, string> = {};
    let hasReceivedText = false;
    let hasReceivedToolCall = false;
    let hasReceivedToolResult = false;

    try {
      const stopStream = api.agentAnalyzeStream(
        userMsg.content,
        currentSessionId, 
        settings.dbConfig.fileId!,
        currentSession.messages,
        settings.customApiKey,
        settings.customBaseUrl,
        settings.model,
        12, 
        (text: string) => {
          hasReceivedText = true;
          if (contentText === initialContent) {
            const hasIcon = /^[🔧📊✅❌💡📝🤔📚]/.test(text.trim());
            if (!hasIcon) {
              const iconPrefix = settings.language === 'zh' ? '💡 ' : '💡 ';
              contentText = iconPrefix + text;
            } else {
              contentText = text;
            }
          } else {
            contentText += text;
          }
          setSessions(prev => prev.map(s => s.id === currentSessionId ? {
            ...s,
            messages: s.messages.map(m => m.id === botMsgId ? {
              ...m,
              content: contentText,
              status: 'thinking' as const
            } : m)
          } : s));
        },
        (tool: string, status: string, sqlCode?: string) => {
          hasReceivedToolCall = true;
          toolStatus[tool] = status;
          if (contentText === initialContent) {
            contentText = "";
          }
          
          let toolCallText = settings.language === 'zh' 
            ? `\n\n🔧 **正在执行**: ${tool === 'sql_inter' ? 'SQL查询' : tool === 'python_inter' ? 'Python代码分析' : tool === 'extract_data' ? '数据提取' : tool}...` 
            : `\n\n🔧 **Executing**: ${tool === 'sql_inter' ? 'SQL Query' : tool === 'python_inter' ? 'Python Analysis' : tool === 'extract_data' ? 'Data Extraction' : tool}...`;
          
          if (tool === 'sql_inter' && sqlCode) {
            toolCallText += `\n\n\`\`\`sql\n${sqlCode}\n\`\`\``;
          }
          
          contentText = contentText + toolCallText;
          setSessions(prev => prev.map(s => s.id === currentSessionId ? {
            ...s,
            messages: s.messages.map(m => m.id === botMsgId ? {
              ...m,
              content: contentText,
              sqlQuery: (tool === 'sql_inter' && sqlCode) ? sqlCode : m.sqlQuery,
              status: 'executing' as const
            } : m)
          } : s));
        },
        (tool: string, result: string, status: string) => {
          hasReceivedToolResult = true;
          const toolCallPattern = settings.language === 'zh' 
            ? new RegExp(`🔧 \\*\\*正在执行\\*\\*: [^\\n]+${tool === 'sql_inter' ? 'SQL查询' : tool === 'python_inter' ? 'Python代码分析' : tool === 'extract_data' ? '数据提取' : tool}\\.\\.\\.`, 'g')
            : new RegExp(`🔧 \\*\\*Executing\\*\\*: [^\\n]+${tool === 'sql_inter' ? 'SQL Query' : tool === 'python_inter' ? 'Python Analysis' : tool === 'extract_data' ? 'Data Extraction' : tool}\\.\\.\\.`, 'g');
          
          contentText = contentText.replace(toolCallPattern, '');
          
          if (contentText === initialContent) contentText = "";
          
          if (status === 'success') {
            if (tool === 'python_inter') {
              try {
                const parsed = JSON.parse(result);
                if (parsed.type === 'visualization_config' && parsed.config) {
                  const vizConfig = parsed.config;
                  if (vizConfig.type && vizConfig.data && Array.isArray(vizConfig.data)) {
                    const columns = vizConfig.data.length > 0 ? Object.keys(vizConfig.data[0]) : [];
                    contentText += settings.language === 'zh'
                      ? `\n\n📊 已生成可视化配置，图表将在下方显示`
                      : `\n\n📊 Visualization config generated, chart will be displayed below`;
                    
                    setSessions(prev => prev.map(s => s.id === currentSessionId ? {
                      ...s,
                      messages: s.messages.map(m => m.id === botMsgId ? {
                        ...m,
                        content: contentText,
                        executionResult: {
                          columns: columns,
                          data: vizConfig.data,
                          chartTypeSuggestion: vizConfig.type,
                          summary: vizConfig.title || (settings.language === 'zh' ? '可视化图表' : 'Visualization'),
                          visualizationConfig: vizConfig,
                          displayType: vizConfig.displayType || 'both'
                        },
                        status: Object.keys(toolStatus).length > 0 ? 'executing' as const : 'thinking' as const
                      } : m)
                    } : s));
                    delete toolStatus[tool];
                    return;
                  }
                }
              } catch (e) { }
            }
            
            if (tool === 'sql_inter') {
              try {
                const sqlResult = JSON.parse(result);
                if (sqlResult.columns && sqlResult.rows && Array.isArray(sqlResult.rows)) {
                  const rowCount = sqlResult.row_count || sqlResult.rows.length;
                  const toolResultText = settings.language === 'zh'
                    ? `\n\n✅ SQL查询执行成功，返回 ${rowCount} 条结果`
                    : `\n\n✅ SQL query executed successfully, returned ${rowCount} rows`;
                  contentText += toolResultText;
                  
                  setSessions(prev => prev.map(s => s.id === currentSessionId ? {
                    ...s,
                    messages: s.messages.map(m => m.id === botMsgId ? {
                      ...m,
                      content: contentText,
                      status: Object.keys(toolStatus).length > 0 ? 'executing' as const : 'thinking' as const
                    } : m)
                  } : s));
                  delete toolStatus[tool];
                  return;
                }
              } catch (e) { }
            }
            
            const resultPreview = result.length > 300 ? result.substring(0, 300) + '\n...' : result;
            const toolResultText = settings.language === 'zh'
              ? `\n\n✅ **${tool}** 执行成功：\n\`\`\`\n${resultPreview}\n\`\`\``
              : `\n\n✅ **${tool}** executed successfully:\n\`\`\`\n${resultPreview}\n\`\`\``;
            contentText += toolResultText;
          } else {
            const toolErrorText = settings.language === 'zh'
              ? `\n\n❌ **${tool}** 执行失败: ${result}`
              : `\n\n❌ **${tool}** execution failed: ${result}`;
            contentText += toolErrorText;
          }
          
          delete toolStatus[tool];
          setSessions(prev => prev.map(s => s.id === currentSessionId ? {
            ...s,
            messages: s.messages.map(m => m.id === botMsgId ? {
              ...m,
              content: contentText,
              status: Object.keys(toolStatus).length > 0 ? 'executing' as const : 'thinking' as const
            } : m)
          } : s));
        },
        (error: string) => {
          console.error("Agent stream error:", error);
          setSessions(prev => prev.map(s => s.id === currentSessionId ? {
            ...s,
            messages: s.messages.map(m => m.id === botMsgId ? {
              ...m,
              content: contentText + (settings.language === 'zh' 
                ? `\n\n❌ 分析出错: ${error}` 
                : `\n\n❌ Analysis error: ${error}`),
              status: 'error' as const,
              error: error
            } : m)
          } : s));
          setIsStreaming(false);
          setIsProcessing(false);
          setStreamController(null);
        },
        () => {
          if (!hasReceivedText && !hasReceivedToolCall && !hasReceivedToolResult) {
            contentText = settings.language === 'zh' 
              ? '❌ 分析完成，但未收到响应内容。' 
              : '❌ Analysis completed, but no response content received.';
          } else if (!hasReceivedText && hasReceivedToolResult) {
             if (!contentText || contentText === initialContent || contentText.trim() === '') {
              const toolHint = settings.language === 'zh'
                ? '\n\n✅ 分析已完成。工具执行成功，但未生成文本回答。'
                : '\n\n✅ Analysis completed. Tools executed successfully, but no text response was generated.';
              contentText = (contentText === initialContent ? '' : contentText) + toolHint;
            }
          } else if (contentText === initialContent) {
             if (hasReceivedText) {
              contentText = settings.language === 'zh' ? '✅ 分析完成。' : '✅ Analysis completed.';
            }
          } else {
            const hasIcon = /^[🔧📊✅❌💡📝🤔📚]/.test(contentText.trim());
            if (!hasIcon && contentText.trim() && contentText !== initialContent) {
              const iconPrefix = settings.language === 'zh' ? '💡 ' : '💡 ';
              contentText = iconPrefix + contentText;
            }
          }
          
          setSessions(prev => prev.map(s => s.id === currentSessionId ? {
            ...s,
            messages: s.messages.map(m => m.id === botMsgId ? {
              ...m,
              content: contentText,
              status: 'executed' as const
            } : m)
          } : s));
          setIsStreaming(false);
          setIsProcessing(false);
          setStreamController(null);
        },
        controller.signal,
        settings.useRag // Pass useRag flag
      );
      setStreamController(controller);

    } catch (error: any) {
      console.error("Agent analysis error:", error);
      setSessions(prev => prev.map(s => s.id === currentSessionId ? {
        ...s,
        messages: s.messages.map(m => m.id === botMsgId ? {
          ...m,
          content: settings.language === 'zh' 
            ? `分析失败: ${error.message || error}` 
            : `Analysis failed: ${error.message || error}`,
          status: 'error' as const,
          error: error.message || String(error)
        } : m)
      } : s));
      setIsStreaming(false);
      setIsProcessing(false);
      setStreamController(null);
    }
  };


  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    setIsProcessing(true); 
    
    try {
        const result = await api.uploadFile(file);
        const sessionMeta = await api.createSession(result.id, file.name);
        
        const newRealSession: Session = {
            id: sessionMeta.id, 
            title: file.name,
            messages: [], 
            updatedAt: Date.now(),
            fileId: result.id
        };

        const freshPlaceholder: Session = {
            id: '1', title: t.newAnalysis, messages: [], updatedAt: Date.now()
        };

        setSessions(prev => [freshPlaceholder, newRealSession, ...prev.filter(s => s.id !== '1')]);
        setCurrentSessionId(newRealSession.id);
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

        if (streamController) streamController.abort();
        const controller = new AbortController();
        setStreamController(controller);
        setIsStreaming(true);

        const summaryMessageId = newRealSession.id + '_summary';
        const summaryMessage: Message = {
          id: summaryMessageId,
          role: 'model',
          content: "",  
          timestamp: Date.now()
        };

        setSessions(prev => prev.map(s => s.id === newRealSession.id ? {
          ...s,
          messages: [...s.messages, summaryMessage]
        } : s));

        let summaryText = "";
        try {
          const stopStream = api.getDbSummaryStream(
            result.id,
            settings.customApiKey,
            settings.customBaseUrl,
            settings.model,
            (chunk: string) => {
              summaryText += chunk;
              setSessions(prev => prev.map(s => s.id === newRealSession.id ? {
                ...s,
                messages: s.messages.map(m => m.id === summaryMessageId ? { ...m, content: summaryText } : m)
              } : s));
            },
            (error: string) => {
              console.error("Summary error:", error);
              summaryText = settings.language === 'zh' ? `摘要生成失败: ${error}` : `Summary failed: ${error}`;
              setSessions(prev => prev.map(s => s.id === newRealSession.id ? {
                ...s,
                messages: s.messages.map(m => m.id === summaryMessageId ? { ...m, content: summaryText } : m)
              } : s));
              setIsStreaming(false);
              setStreamController(null);
            },
            () => {
              setIsStreaming(false);
              setStreamController(null);
            },
            controller.signal,
            newRealSession.id
          );
        } catch (sumErr) {
          setIsStreaming(false);
          setStreamController(null);
        }

    } catch (error: any) {
        alert(settings.language === 'zh' ? `上传失败: ${error.message}` : `Upload failed: ${error.message}`);
    } finally {
        setIsUploading(false);
        setIsProcessing(false);
        e.target.value = '';
    }
  };

  if (!user) {
    return (
      <AuthPage 
        onLogin={handleLogin} 
        language={settings.language} 
        onLanguageChange={handleLanguageChange}
      />
    );
  }

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

        <div className="p-3 min-w-64 flex flex-col gap-2">
          <button 
            onClick={handleNewSession}
            className={`w-full flex items-center gap-2 px-4 py-3 rounded-full text-sm font-medium transition-colors ${
                currentSessionId === '1'
                  ? 'bg-accent text-white hover:bg-blue-600'
                  : 'bg-[#2a2b2d] text-primary hover:bg-[#353638]'
            }`}
          >
            <Plus size={18} /> {t.newAnalysis}
          </button>
          
          {/* Knowledge Base Button */}
           <button 
            onClick={() => setIsKbOpen(true)}
            className="w-full flex items-center gap-2 px-4 py-3 rounded-full text-sm font-medium transition-colors bg-[#2a2b2d] text-subtext hover:bg-[#353638] hover:text-white"
          >
            <BookOpen size={18} /> {settings.language === 'zh' ? '知识库管理' : 'Knowledge Base'}
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-1 min-w-64">
          <div className="text-xs font-medium text-subtext px-4 py-2 uppercase tracking-wider">{t.recent}</div>
          {sessions.filter(s => s.id !== '1').map(session => (
            <div
              key={session.id}
              className={`group w-full rounded-lg text-sm flex items-center transition-colors relative ${
                session.id === currentSessionId 
                  ? 'bg-[#004A77] text-white' 
                  : 'text-subtext hover:bg-[#2a2b2d] hover:text-white'
              }`}
            >
              <button
                onClick={() => setCurrentSessionId(session.id)}
                className="flex-1 flex items-center gap-3 px-4 py-3 text-left overflow-hidden"
              >
                <MessageSquare size={16} className="shrink-0" />
                <span className="truncate">{session.title}</span>
              </button>
              
              <button
                onClick={(e) => handleDeleteSession(session.id, e)}
                className={`p-2 mr-2 rounded hover:bg-red-500/20 hover:text-red-400 transition-colors ${
                    session.id === currentSessionId ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
                }`}
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>

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
            <div className="flex items-center gap-2 bg-[#2a2b2d] rounded-lg px-3 py-1.5 border border-transparent focus-within:border-accent transition-colors">
              <Bot size={16} className="text-subtext" />
              <select
                value={settings.model}
                onChange={(e) => setSettings(s => ({...s, model: e.target.value}))}
                className="bg-[#2a2b2d] text-sm text-text font-medium outline-none cursor-pointer border-none rounded-md px-1 py-0.5 focus:ring-0 focus:outline-none appearance-none"
              >
                {AVAILABLE_MODELS.map((model) => (
                  <option key={model.value} value={model.value} className="bg-[#2a2b2d] text-text">
                    {model.label}
                  </option>
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
          {/* ... existing streaming indicator logic ... */}
          {isStreaming && !settings.dbConfig.fileId && (
            <div className="flex items-center gap-3 p-4 mx-4 mb-4 bg-[#2a2b2d] rounded-lg border border-accent/30">
              <Loader2 size={14} className="animate-spin text-white" />
              <div className="flex-1 text-sm">{settings.language === 'zh' ? '正在生成摘要...' : 'Generating summary...'}</div>
              <button onClick={stopStreaming} className="text-red-400 text-xs">Stop</button>
            </div>
          )}

          {currentSession?.messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center p-8 text-center text-subtext">
              <div className="w-16 h-16 bg-[#2a2b2d] rounded-2xl flex items-center justify-center mb-6 text-accent">
                <Sparkles size={32} />
              </div>
              <h1 className="text-2xl font-semibold text-text mb-2">
                 {t.greeting}, {user.name.split(' ')[0]}
              </h1>
              <p className="max-w-md mb-8">{t.greetingSub}</p>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-2xl w-full">
                <button 
                  onClick={() => setInput(settings.language === 'zh' ? "按月显示各地区总销售额的柱状图" : "Show total sales by region as a bar chart")} 
                  className="p-4 bg-[#1E1F20] border border-secondary rounded-xl hover:bg-[#2a2b2d] hover:border-accent text-left transition-all"
                >
                  <span className="font-medium text-text block mb-1">{t.suggestion1}</span>
                  <span className="text-xs">{t.suggestion1Sub}</span>
                </button>
                <button 
                   onClick={() => setInput(settings.language === 'zh' ? "识别前3名最有价值客户" : "Identify top 3 customers")} 
                   className="p-4 bg-[#1E1F20] border border-secondary rounded-xl hover:bg-[#2a2b2d] hover:border-accent text-left transition-all"
                >
                  <span className="font-medium text-text block mb-1">{t.suggestion2}</span>
                  <span className="text-xs">{t.suggestion2Sub}</span>
                </button>
              </div>
            </div>
          ) : (
            <div className="max-w-4xl mx-auto py-6">
              {currentSession?.messages.map(msg => (
                <MessageBubble key={msg.id} message={msg} language={settings.language} />
              ))}
              {isProcessing && !currentSession?.messages.some(m => m.role === 'model' && (m.status === 'thinking' || m.status === 'executing')) && (
                <div className="flex gap-4 p-6 bg-[#1E1F20]/50">
                  <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-blue-500 to-cyan-400 flex items-center justify-center shrink-0">
                    <Loader2 size={18} className="animate-spin text-white" />
                  </div>
                  <div className="flex flex-col gap-2">
                    <div className="text-sm text-subtext animate-pulse">{t.processing}</div>
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

                {/* RAG Toggle */}
                <button 
                  onClick={() => setSettings(s => ({...s, useRag: !s.useRag}))}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    settings.useRag 
                      ? 'bg-purple-500/20 text-purple-300 border border-purple-500/50' 
                      : 'bg-[#2a2b2d] text-subtext border border-transparent hover:bg-[#353638]'
                  }`}
                  title={settings.language === 'zh' ? "启用/禁用知识库检索" : "Enable/Disable RAG"}
                >
                  <BookOpen size={14} />
                  <span>RAG {settings.useRag ? 'ON' : 'OFF'}</span>
                </button>
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
      <KnowledgeBaseModal
        isOpen={isKbOpen}
        onClose={() => setIsKbOpen(false)}
        language={settings.language}
        settings={settings}
      />
      </main>
    </div>
  );
}

export default App;