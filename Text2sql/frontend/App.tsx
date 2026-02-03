
import React, { useState, useRef, useEffect } from 'react';
import { 
  Settings, Plus, MessageSquare, Send, Upload, LayoutGrid, 
  Database, Loader2, Menu, Sparkles, LogOut, User as UserIcon,
  Bot, Trash2, BookOpen, Brain, RefreshCw, CheckCircle
} from 'lucide-react';
import { generateSessionTitle } from './services/geminiService';
import SettingsModal from './components/SettingsModal';
import KnowledgeBaseModal from './components/KnowledgeBaseModal';
import MessageBubble from './components/MessageBubble';
import AuthPage from './components/AuthPage';
import { Session, Message, AppSettings, User, AVAILABLE_MODELS, SqlResult, ChartType, SQL_PLACEHOLDER, CHART_PLACEHOLDER } from './types';
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
       return { ...parsed, model: validModel, useRag: parsed.useRag ?? false, enableMemory: parsed.enableMemory ?? false, sqlCheck: parsed.sqlCheck ?? false, sqlExpert: parsed.sqlExpert ?? false };
     }

     return {
      language: 'zh',
      model: 'gemini-2.5-flash',
      customBaseUrl: '',
      customApiKey: '',
      useSimulationMode: true,
      useRag: false,
      enableMemory: false,
      sqlCheck: false,
      sqlExpert: false,
      dbConfig: {
        type: 'postgres',
        host: 'localhost',
        port: '5432',
        database: '',
        user: '',
        password: '',
        uploadedPath: '',
        fileId: undefined,
        connectionId: undefined
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
  const [isKbOpen, setIsKbOpen] = useState(false); 
  const [isRefreshingMemory, setIsRefreshingMemory] = useState(false); // [New]

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
        connectionId: s.connectionId,
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
      // Reset current active DB config on load (user needs to select session)
      setSettings(prev => ({
        ...prev,
        dbConfig: { ...prev.dbConfig, fileId: undefined, uploadedPath: '', connectionId: undefined }
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
          let sqlQuery = msg.sqlQuery;
          let executionResult = undefined;
          let status = msg.status || 'executed';

          if (msg.steps && Array.isArray(msg.steps)) {
              const sqlStep = msg.steps.find((s: any) => s.tool === 'sql_inter');
              // Only override if sqlQuery not already set by metadata
              if (sqlStep && sqlStep.input && !sqlQuery) {
                  sqlQuery = sqlStep.input;
              }
              // If we have a pending step, set status
              if (sqlStep && sqlStep.status === 'pending_approval') {
                  status = 'pending_approval';
                  sqlQuery = sqlStep.input; // Ensure query is set
              }
          }

          let executionResults: any[] | undefined;
          if (msg.vizConfig) {
              const single = {
                  columns: msg.vizConfig.data && msg.vizConfig.data.length > 0 ? Object.keys(msg.vizConfig.data[0]) : [],
                  data: msg.vizConfig.data || [],
                  chartTypeSuggestion: msg.vizConfig.type,
                  summary: msg.vizConfig.title || 'Visualization',
                  visualizationConfig: msg.vizConfig,
                  displayType: msg.vizConfig.displayType || 'both'
              };
              executionResult = single;
              executionResults = [single];
          }

          return { ...msg, sqlQuery, executionResult, executionResults, status };
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
        // When switching session, apply its DB config to global settings temporarily so new messages use it
        if (session) {
            setSettings(prev => ({
                ...prev,
                dbConfig: { 
                    ...prev.dbConfig, 
                    fileId: session.fileId, 
                    connectionId: session.connectionId,
                    // Clear uploaded path if it's a connection session to update UI
                    uploadedPath: session.connectionId ? '' : prev.dbConfig.uploadedPath 
                }
            }));
        }
    } else if (currentSessionId === '1') {
        // Keep current settings as is, or reset? 
        // Better to keep them so user can start new chat with current config.
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
        dbConfig: { ...prev.dbConfig, fileId: undefined, uploadedPath: '', connectionId: undefined }
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
  
  const handleRefreshMemory = async () => {
      if (isRefreshingMemory) return;
      setIsRefreshingMemory(true);
      try {
          await api.refreshMemory(settings.customApiKey, settings.customBaseUrl, settings.model);
          alert(settings.language === 'zh' ? '长期记忆已刷新！' : 'Long-term memory refreshed!');
      } catch (e: any) {
          alert(settings.language === 'zh' ? `刷新失败: ${e.message}` : `Refresh failed: ${e.message}`);
      } finally {
          setIsRefreshingMemory(false);
      }
  };

  const handleNewSession = async () => {
    setCurrentSessionId('1');
    if (window.innerWidth < 768) setIsSidebarOpen(false);
  };
  
  // Reusable function to process stream callbacks
  // [Fix] Added preserveInitialContent to allow appending instead of replacing
  const createStreamCallbacks = (sessionId: string, msgId: string, initialContent: string, preserveInitialContent: boolean = false) => {
      let contentText = initialContent;
      const toolStatus: Record<string, string> = {};
      let hasReceivedText = false;
      let hasReceivedToolCall = false;
      let hasReceivedToolResult = false;
      
      return {
          onText: (text: string) => {
              hasReceivedText = true;
              
              // Only clear initial content if we are NOT preserving it (e.g. initial thinking msg)
              if (!preserveInitialContent && contentText === initialContent) {
                const hasIcon = /^[🔧📊✅❌💡📝🤔📚🧠]/.test(text.trim());
                if (!hasIcon) {
                  const iconPrefix = settings.language === 'zh' ? '💡 ' : '💡 ';
                  contentText = iconPrefix + text;
                } else {
                  contentText = text;
                }
              } else {
                contentText += text;
              }
              
              setSessions(prev => prev.map(s => s.id === sessionId ? {
                ...s,
                messages: s.messages.map(m => m.id === msgId ? {
                  ...m,
                  content: contentText,
                  status: 'thinking' as const
                } : m)
              } : s));
          },
          onToolCall: (tool: string, status: string, sqlCode?: string) => {
              hasReceivedToolCall = true;
              toolStatus[tool] = status;
              
              // If confirmation needed, stop thinking and show button
              if (status === 'pending_approval') {
                  if (!preserveInitialContent && contentText === initialContent) contentText = "";
                  contentText += "\n\n" + SQL_PLACEHOLDER + "\n\n";
                  setSessions(prev => prev.map(s => s.id === sessionId ? {
                    ...s,
                    messages: s.messages.map(m => m.id === msgId ? {
                      ...m,
                      content: contentText,
                      sqlQuery: sqlCode,
                      status: 'pending_approval' as const
                    } : m)
                  } : s));
                  // The backend stream ends here automatically
                  return;
              }

              if (!preserveInitialContent && contentText === initialContent) {
                contentText = "";
              }
              
              let toolCallText = settings.language === 'zh' 
                ? `\n\n🔧 **正在执行**: ${tool === 'sql_inter' ? 'SQL查询' : tool === 'python_inter' ? 'Python代码分析' : tool === 'extract_data' ? '数据提取' : tool}...` 
                : `\n\n🔧 **Executing**: ${tool === 'sql_inter' ? 'SQL Query' : tool === 'python_inter' ? 'Python Analysis' : tool === 'extract_data' ? 'Data Extraction' : tool}...`;
              
              // 自动执行时也用占位符嵌入 SQL，由 MessageBubble 在占位符位置渲染一块显示，避免重复
              if (tool === 'sql_inter' && sqlCode) {
                toolCallText += "\n\n" + SQL_PLACEHOLDER + "\n\n";
              }
              
              contentText = contentText + toolCallText;
              setSessions(prev => prev.map(s => s.id === sessionId ? {
                ...s,
                messages: s.messages.map(m => m.id === msgId ? {
                  ...m,
                  content: contentText,
                  sqlQuery: (tool === 'sql_inter' && sqlCode) ? sqlCode : m.sqlQuery,
                  status: 'executing' as const
                } : m)
              } : s));
          },
          onToolResult: (tool: string, result: string, status: string) => {
              hasReceivedToolResult = true;
              const toolCallPattern = settings.language === 'zh' 
                ? new RegExp(`🔧 \\*\\*正在执行\\*\\*: [^\\n]+${tool === 'sql_inter' ? 'SQL查询' : tool === 'python_inter' ? 'Python代码分析' : tool === 'extract_data' ? '数据提取' : tool}\\.\\.\\.`, 'g')
                : new RegExp(`🔧 \\*\\*Executing\\*\\*: [^\\n]+${tool === 'sql_inter' ? 'SQL Query' : tool === 'python_inter' ? 'Python Analysis' : tool === 'extract_data' ? 'Data Extraction' : tool}\\.\\.\\.`, 'g');
              
              // Only replace if we are sure it's just the status text
              if (!preserveInitialContent) {
                   contentText = contentText.replace(toolCallPattern, '');
              }
              
              if (!preserveInitialContent && contentText === initialContent) contentText = "";
              
              if (status === 'success') {
                if (tool === 'python_inter') {
                  try {
                    const parsed = JSON.parse(result);
                    const configs: any[] = Array.isArray(parsed.configs) ? parsed.configs : (parsed.config ? [parsed.config] : []);
                    if (parsed.type === 'visualization_config' && configs.length > 0) {
                      const newResults: SqlResult[] = [];
                      for (const vizConfig of configs) {
                        let vizData = vizConfig.data;
                        if (vizData && !Array.isArray(vizData) && typeof vizData === 'object') {
                          const keys = Object.keys(vizData);
                          if (keys.length > 0) {
                            const rowCount = vizData[keys[0]]?.length || 0;
                            const newData: any[] = [];
                            for (let i = 0; i < rowCount; i++) {
                              const row: any = {};
                              keys.forEach(k => { row[k] = vizData[k][i]; });
                              newData.push(row);
                            }
                            vizData = newData;
                            vizConfig.data = newData;
                          }
                        }
                        if (vizConfig.type && vizData && Array.isArray(vizData)) {
                          const columns = vizData.length > 0 ? Object.keys(vizData[0]) : [];
                          newResults.push({
                            columns,
                            data: vizData,
                            chartTypeSuggestion: vizConfig.type,
                            summary: vizConfig.title || (settings.language === 'zh' ? '可视化图表' : 'Visualization'),
                            visualizationConfig: vizConfig,
                            displayType: vizConfig.displayType || 'both'
                          });
                        }
                      }
                      if (newResults.length > 0) {
                        for (let i = 0; i < newResults.length; i++) {
                          contentText += '\n\n' + CHART_PLACEHOLDER + '\n\n';
                        }
                        setSessions(prev => prev.map(s => s.id === sessionId ? {
                          ...s,
                          messages: s.messages.map(m => m.id === msgId ? {
                            ...m,
                            content: contentText,
                            executionResults: [...(m.executionResults || (m.executionResult ? [m.executionResult] : [])), ...newResults],
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
                      
                      setSessions(prev => prev.map(s => s.id === sessionId ? {
                        ...s,
                        messages: s.messages.map(m => m.id === msgId ? {
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
              setSessions(prev => prev.map(s => s.id === sessionId ? {
                ...s,
                messages: s.messages.map(m => m.id === msgId ? {
                  ...m,
                  content: contentText,
                  status: Object.keys(toolStatus).length > 0 ? 'executing' as const : 'thinking' as const
                } : m)
              } : s));
          },
          onError: (error: string) => {
              console.error("Agent stream error:", error);
              setSessions(prev => prev.map(s => s.id === sessionId ? {
                ...s,
                messages: s.messages.map(m => m.id === msgId ? {
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
          onComplete: () => {
              if (!hasReceivedText && !hasReceivedToolCall && !hasReceivedToolResult) {
                // If it's a resume stream (confirmation), it's ok if we received nothing new if the result was just injected
                if (!preserveInitialContent) {
                    contentText = settings.language === 'zh' 
                    ? '❌ 分析完成，但未收到响应内容。' 
                    : '❌ Analysis completed, but no response content received.';
                }
              } else if (!hasReceivedText && hasReceivedToolResult) {
                 if (!contentText || contentText === initialContent || contentText.trim() === '') {
                  const toolHint = settings.language === 'zh'
                    ? '\n\n✅ 分析已完成。工具执行成功，但未生成文本回答。'
                    : '\n\n✅ Analysis completed. Tools executed successfully, but no text response was generated.';
                  contentText = (contentText === initialContent ? '' : contentText) + toolHint;
                }
              } else if (contentText === initialContent && !preserveInitialContent) {
                 if (hasReceivedText) {
                  contentText = settings.language === 'zh' ? '✅ 分析完成。' : '✅ Analysis completed.';
                }
              }
              
              // Only mark as executed if not pending approval
              setSessions(prev => {
                  const currentSess = prev.find(s => s.id === sessionId);
                  const currentMsg = currentSess?.messages.find(m => m.id === msgId);
                  if (currentMsg?.status === 'pending_approval') return prev;
                  
                  return prev.map(s => s.id === sessionId ? {
                    ...s,
                    messages: s.messages.map(m => m.id === msgId ? {
                      ...m,
                      content: contentText,
                      status: 'executed' as const
                    } : m)
                  } : s);
              });
              
              setIsStreaming(false);
              setIsProcessing(false);
              setStreamController(null);
          }
      };
  };

  const handleSendMessage = async () => {
    if (!input.trim() || isProcessing || isStreaming) return;
    
    // Check if any DB source is configured
    if (!settings.dbConfig.fileId && !settings.dbConfig.connectionId) {
      alert(settings.language === 'zh' ? '请先上传数据库文件或在设置中连接数据库' : 'Please upload a database file or connect to a database in settings');
      setIsSettingsOpen(true);
      return;
    }

    // 1. If this is the placeholder session ('1'), create a real one now
    let activeSessionId = currentSessionId;
    if (currentSessionId === '1') {
        try {
            const newSession = await api.createSession(
                settings.dbConfig.fileId, 
                input.substring(0, 20),
                settings.dbConfig.connectionId
            );
            
            // Transform to local session
            const newLocalSession: Session = {
                id: newSession.id,
                title: newSession.title,
                messages: [],
                updatedAt: Date.now(),
                fileId: settings.dbConfig.fileId,
                connectionId: settings.dbConfig.connectionId
            };
            
            setSessions(prev => [prev[0], newLocalSession, ...prev.slice(1)]);
            setCurrentSessionId(newSession.id);
            activeSessionId = newSession.id;
        } catch (e) {
            alert("Failed to create session");
            return;
        }
    }
    
    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input,
      timestamp: Date.now()
    };

    // Optimistic update for UI
    setSessions(prev => prev.map(s => s.id === activeSessionId ? { 
        ...s, 
        messages: [...s.messages, userMsg] 
    } : s));
    
    setInput('');
    const activeSession = sessions.find(s => s.id === activeSessionId) || { messages: [] };
    const updatedHistory = [...activeSession.messages, userMsg];

    // Generate title if it's the first real message
    if (activeSession.messages.length === 0) {
      generateSessionTitle(userMsg.content, settings.language).then(newTitle => {
        setSessions(prev => prev.map(s => s.id === activeSessionId ? { ...s, title: newTitle } : s));
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

    setSessions(prev => prev.map(s => s.id === activeSessionId ? { 
      ...s, 
      messages: [...updatedHistory, botMsg]
    } : s));

    if (streamController) {
      streamController.abort();
    }

    const controller = new AbortController();
    setStreamController(controller);
    setIsStreaming(true);
    setIsProcessing(true);

    const callbacks = createStreamCallbacks(activeSessionId, botMsgId, initialContent, false); // False: New message

    try {
      api.agentAnalyzeStream(
        userMsg.content,
        activeSessionId, 
        settings.dbConfig.fileId, 
        updatedHistory,
        settings.customApiKey,
        settings.customBaseUrl,
        settings.model,
        12, 
        callbacks.onText,
        callbacks.onToolCall,
        callbacks.onToolResult,
        callbacks.onError,
        callbacks.onComplete,
        controller.signal,
        settings.useRag,
        settings.dbConfig.connectionId,
        settings.enableMemory,
        !settings.sqlCheck, // allow_auto_execute: false when SQL检查 ON
        settings.sqlExpert // use_sql_expert
      );
    } catch (error: any) {
      console.error("Agent analysis error:", error);
      callbacks.onError(error.message || String(error));
    }
  };

  const handleConfirmSql = async (messageId: string, sql: string) => {
      const currentSess = sessions.find(s => s.id === currentSessionId);
      const originalMsg = currentSess?.messages.find(m => m.id === messageId);
      const originalContent = originalMsg?.content || "";

      // 1. Update UI to executing state
      setSessions(prev => prev.map(s => s.id === currentSessionId ? {
          ...s,
          messages: s.messages.map(m => m.id === messageId ? {
              ...m,
              status: 'executing',
              sqlQuery: sql, // Update with edited SQL
              content: m.content + (settings.language === 'zh' ? "\n\n🚀 用户确认执行..." : "\n\n🚀 User confirmed execution...")
          } : m)
      } : s));

      const controller = new AbortController();
      setStreamController(controller);
      setIsStreaming(true);
      setIsProcessing(true);
      
      // [Fix] Pass true for preserveInitialContent to allow appending
      const updatedInitialContent = originalContent + (settings.language === 'zh' ? "\n\n🚀 用户确认执行..." : "\n\n🚀 User confirmed execution...");
      const callbacks = createStreamCallbacks(currentSessionId, messageId, updatedInitialContent, true); 

      try {
          api.confirmSql(
              currentSessionId,
              sql,
              settings.customApiKey,
              settings.customBaseUrl,
              settings.model,
              callbacks.onText,
              callbacks.onToolCall,
              callbacks.onToolResult,
              callbacks.onError,
              callbacks.onComplete,
              controller.signal
          );
      } catch (e: any) {
           callbacks.onError(e.message);
      }
  };
  
  const handleRejectSql = (messageId: string) => {
       setSessions(prev => prev.map(s => s.id === currentSessionId ? {
          ...s,
          messages: s.messages.map(m => m.id === messageId ? {
              ...m,
              status: 'error',
              content: m.content + (settings.language === 'zh' ? "\n\n❌ 用户拒绝执行。" : "\n\n❌ User rejected execution.")
          } : m)
      } : s));
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
            fileId: result.id,
            connectionId: undefined // Reset conn ID when file uploaded
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
          api.getDbSummaryStream(
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
             <span className={`w-2 h-2 rounded-full ${settings.dbConfig.fileId || settings.dbConfig.connectionId ? 'bg-green-500' : 'bg-gray-500'}`} />
             {settings.dbConfig.fileId 
               ? (settings.language === 'zh' ? '已连接文件' : 'File Connected') 
               : settings.dbConfig.connectionId
                 ? (settings.language === 'zh' ? '已连接数据库' : 'DB Connected')
                 : t.envConnected}
          </div>
        </header>

        {/* Chat Area */}
        <div className="flex-1 overflow-y-auto" ref={scrollRef}>
          {/* Streaming Indicator */}
          {isStreaming && !settings.dbConfig.fileId && !settings.dbConfig.connectionId && (
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
                <MessageBubble 
                    key={msg.id} 
                    message={msg} 
                    language={settings.language}
                    onConfirmSql={handleConfirmSql}
                    onRejectSql={handleRejectSql}
                />
              ))}
              {isProcessing && !currentSession?.messages.some(m => m.role === 'model' && (m.status === 'thinking' || m.status === 'executing' || m.status === 'pending_approval')) && (
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
                
                {/* Memory Toggle [New] */}
                <div className="flex items-center gap-1">
                    <button 
                      onClick={() => setSettings(s => ({...s, enableMemory: !s.enableMemory}))}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                        settings.enableMemory 
                          ? 'bg-amber-500/20 text-amber-300 border border-amber-500/50' 
                          : 'bg-[#2a2b2d] text-subtext border border-transparent hover:bg-[#353638]'
                      }`}
                      title={settings.language === 'zh' ? "启用/禁用长期记忆" : "Enable/Disable Long-term Memory"}
                    >
                      <Brain size={14} />
                      <span>{settings.language === 'zh' ? '记忆' : 'Memory'} {settings.enableMemory ? 'ON' : 'OFF'}</span>
                    </button>
                    {settings.enableMemory && (
                        <button 
                            onClick={handleRefreshMemory} 
                            disabled={isRefreshingMemory}
                            className={`p-1.5 rounded-lg bg-[#2a2b2d] text-subtext hover:text-white transition-colors ${isRefreshingMemory ? 'animate-spin opacity-50' : ''}`}
                            title={settings.language === 'zh' ? '刷新记忆' : 'Refresh Memory'}
                        >
                            <RefreshCw size={12} />
                        </button>
                    )}
                </div>

                {/* SQL检查 Toggle */}
                <button
                  onClick={() => setSettings(s => ({ ...s, sqlCheck: !s.sqlCheck }))}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    settings.sqlCheck
                      ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/50'
                      : 'bg-[#2a2b2d] text-subtext border border-transparent hover:bg-[#353638]'
                  }`}
                  title={settings.language === 'zh' ? "开启后需先检查 SQL 再执行" : "When ON, SQL must be checked before execution"}
                >
                  <CheckCircle size={14} />
                  <span>{settings.language === 'zh' ? 'SQL检查' : 'SQL Check'} {settings.sqlCheck ? 'ON' : 'OFF'}</span>
                </button>

                {/* SQL专家 Toggle */}
                <button
                  onClick={() => setSettings(s => ({ ...s, sqlExpert: !s.sqlExpert }))}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    settings.sqlExpert
                      ? 'bg-amber-500/20 text-amber-300 border border-amber-500/50'
                      : 'bg-[#2a2b2d] text-subtext border border-transparent hover:bg-[#353638]'
                  }`}
                  title={settings.language === 'zh' ? "开启后使用增强 SQL 生成（仅上传的 SQLite 文件，需 OpenAI 兼容 API）" : "When ON, use enhanced SQL generation (SQLite upload only, OpenAI-compatible API)"}
                >
                  <Sparkles size={14} />
                  <span>{settings.language === 'zh' ? 'SQL专家' : 'SQL Expert'} {settings.sqlExpert ? 'ON' : 'OFF'}</span>
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