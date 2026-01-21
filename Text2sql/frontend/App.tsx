
import React, { useState, useRef, useEffect } from 'react';
import { 
  Settings, Plus, MessageSquare, Send, Upload, LayoutGrid, 
  Database, Loader2, Menu, Sparkles, LogOut, User as UserIcon,
  Bot
} from 'lucide-react';
import { generateSessionTitle } from './services/geminiService';
import SettingsModal from './components/SettingsModal';
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
       // 验证模型是否在可用选项中，如果不在则使用默认值
       const validModel = AVAILABLE_MODELS.some(m => m.value === parsed.model)
         ? parsed.model
         : 'gemini-2.5-flash';
       return { ...parsed, model: validModel };
     }

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
    try {
      const savedUser = localStorage.getItem('current_user');
      if (savedUser) {
        const parsedUser = JSON.parse(savedUser);
        // 验证用户数据完整性
        if (parsedUser && parsedUser.token && parsedUser.email) {
          return parsedUser;
        }
      }
    } catch (error) {
      console.warn('Failed to restore user session:', error);
      // 清除损坏的数据
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

  // 流式生成相关状态
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamController, setStreamController] = useState<AbortController | null>(null);
  
  const scrollRef = useRef<HTMLDivElement>(null);
  const currentSession = sessions.find(s => s.id === currentSessionId)!;

  // --- Effects ---
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [currentSession?.messages, isProcessing]);

  // 在应用启动时验证token有效性
  useEffect(() => {
    const validateTokenOnLoad = async () => {
      if (!user) return;

      try {
        // 尝试一个轻量级的API调用来验证token
        const response = await fetch('http://localhost:8000/api/auth/me', {
          method: 'GET',
          headers: {
            'Authorization': `Bearer ${user.token}`,
          },
        });

        if (!response.ok) {
          console.warn('Token validation failed on app load, clearing user session');
          localStorage.removeItem('current_user');
          setUser(null);
          setSessions([{
            id: '1', title: t.newAnalysis, messages: [], updatedAt: Date.now()
          }]);
        }
      } catch (error) {
        // 如果无法连接服务器，暂时保留用户状态
        console.warn('Token validation failed due to network error, keeping user session:', error);
      }
    };

    validateTokenOnLoad();
  }, []); // 只在应用启动时执行一次

  // --- Auth Handlers ---
  const handleLogin = (newUser: User) => {
    console.log('User logged in:', { ...newUser, token: newUser.token ? '[HIDDEN]' : 'MISSING' });
    setUser(newUser);
    localStorage.setItem('current_user', JSON.stringify(newUser));
  };

  const handleLogout = () => {
    console.log('User logged out');
    setUser(null);
    localStorage.removeItem('current_user');
    setSessions([{
        id: '1', title: t.newAnalysis, messages: [], updatedAt: Date.now()
    }]);
  };

  const handleLanguageChange = (lang: 'en' | 'zh') => {
      setSettings(prev => ({...prev, language: lang}));
  };

  // 中断流式生成（支持摘要和Agent分析）
  const stopStreaming = () => {
    if (streamController) {
      streamController.abort();
      setStreamController(null);
      setIsStreaming(false);
      setIsProcessing(false);

      // 更新最后一条模型消息，标记为已中断
      setSessions(prev => prev.map(s => s.id === currentSessionId ? {
        ...s,
        messages: s.messages.map((m, index, arr) => {
          // 找到最后一条模型消息
          if (m.role === 'model' && index === arr.length - 1) {
            return { ...m, content: m.content + "\n\n*[生成已中断]*", status: 'error' as const };
          }
          // 或者是摘要消息
          if (m.id === currentSessionId + '_summary') {
            return { ...m, content: m.content + "\n\n*[生成已中断]*" };
          }
          return m;
        })
      } : s));
    }
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

  // Agent流式分析 - 模型自主决定工具调用
  const handleSendMessage = async () => {
    if (!input.trim() || isProcessing || isStreaming) return;
    
    // 检查是否有数据库文件
    if (!settings.dbConfig.fileId) {
      alert(settings.language === 'zh' 
        ? '请先上传数据库文件' 
        : 'Please upload a database file first');
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
        setSessions(prev => prev.map(s => s.id === currentSessionId ? { ...s, title: newTitle } : s));
      });
    }

    // 创建初始模型消息用于流式更新
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

    // 添加初始消息
    setSessions(prev => prev.map(s => s.id === currentSessionId ? { 
      ...s, 
      messages: [...updatedMessages, botMsg]
    } : s));

    // 停止之前的流式请求（如果有）
    if (streamController) {
      streamController.abort();
    }

    // 创建新的中断控制器
    const controller = new AbortController();
    setStreamController(controller);
    setIsStreaming(true);
    setIsProcessing(true);

    let contentText = initialContent;
    const toolStatus: Record<string, string> = {}; // 记录工具调用状态
    let hasReceivedText = false; // 跟踪是否收到过文本内容
    let hasReceivedToolCall = false; // 跟踪是否收到过工具调用
    let hasReceivedToolResult = false; // 跟踪是否收到过工具执行结果

    try {
      // 使用流式Agent分析
      const stopStream = api.agentAnalyzeStream(
        userMsg.content,
        settings.dbConfig.fileId!,
        currentSession.messages,
        settings.customApiKey,
        settings.customBaseUrl,
        settings.model,
        12, // maxToolRounds
        // onText: 实时接收文本
        (text: string) => {
          hasReceivedText = true; // 标记已收到文本
          // 如果contentText还是初始提示，则替换它；否则追加
          if (contentText === initialContent) {
            // 检查新文本是否已经有图标，如果没有则添加
            const hasIcon = /^[🔧📊✅❌💡📝🤔]/.test(text.trim());
            if (!hasIcon) {
              // 为分析结果添加图标
              const iconPrefix = settings.language === 'zh' 
                ? '💡 ' 
                : '💡 ';
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
        // onToolCall: 工具调用开始
        (tool: string, status: string, sqlCode?: string) => {
          hasReceivedToolCall = true; // 标记已收到工具调用
          toolStatus[tool] = status;
          // 如果contentText还是初始提示，先清除它
          if (contentText === initialContent) {
            contentText = "";
          }
          
          let toolCallText = settings.language === 'zh' 
            ? `\n\n🔧 **正在执行**: ${tool === 'sql_inter' ? 'SQL查询' : tool === 'python_inter' ? 'Python代码分析' : tool === 'extract_data' ? '数据提取' : tool}...` 
            : `\n\n🔧 **Executing**: ${tool === 'sql_inter' ? 'SQL Query' : tool === 'python_inter' ? 'Python Analysis' : tool === 'extract_data' ? 'Data Extraction' : tool}...`;
          
          // 如果是SQL查询，显示SQL代码
          if (tool === 'sql_inter' && sqlCode) {
            toolCallText += `\n\n\`\`\`sql\n${sqlCode}\n\`\`\``;
          }
          
          contentText = contentText + toolCallText;
          setSessions(prev => prev.map(s => s.id === currentSessionId ? {
            ...s,
            messages: s.messages.map(m => m.id === botMsgId ? {
              ...m,
              content: contentText,
              // 如果是SQL查询，保存SQL代码以便后续显示
              sqlQuery: (tool === 'sql_inter' && sqlCode) ? sqlCode : m.sqlQuery,
              status: 'executing' as const
            } : m)
          } : s));
        },
        // onToolResult: 工具执行结果
        (tool: string, result: string, status: string) => {
          hasReceivedToolResult = true; // 标记已收到工具执行结果
          // 移除之前的"正在执行"文本，替换为结果
          const toolCallPattern = settings.language === 'zh' 
            ? new RegExp(`🔧 \\*\\*正在执行\\*\\*: [^\\n]+${tool === 'sql_inter' ? 'SQL查询' : tool === 'python_inter' ? 'Python代码分析' : tool === 'extract_data' ? '数据提取' : tool}\\.\\.\\.`, 'g')
            : new RegExp(`🔧 \\*\\*Executing\\*\\*: [^\\n]+${tool === 'sql_inter' ? 'SQL Query' : tool === 'python_inter' ? 'Python Analysis' : tool === 'extract_data' ? 'Data Extraction' : tool}\\.\\.\\.`, 'g');
          
          contentText = contentText.replace(toolCallPattern, '');
          
          // 如果contentText还是初始提示，先清除它
          if (contentText === initialContent) {
            contentText = "";
          }
          
          if (status === 'success') {
            // 特殊处理：如果是python_inter工具，检查是否返回可视化配置
            if (tool === 'python_inter') {
              try {
                const parsed = JSON.parse(result);
                if (parsed.type === 'visualization_config' && parsed.config) {
                  const vizConfig = parsed.config;
                  
                  // 验证配置格式
                  if (vizConfig.type && vizConfig.data && Array.isArray(vizConfig.data)) {
                    // 更新消息，添加可视化配置到executionResult
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
                          visualizationConfig: vizConfig,  // 存储完整配置（包含 displayType）
                          displayType: vizConfig.displayType || 'both'  // 传递 displayType
                        },
                        status: Object.keys(toolStatus).length > 0 ? 'executing' as const : 'thinking' as const
                      } : m)
                    } : s));
                    
                    delete toolStatus[tool];
                    return; // 提前返回
                  }
                }
              } catch (e) {
                // 不是JSON或不是可视化配置，继续正常处理
              }
            }
            
            // 特殊处理：如果是sql_inter工具，只显示执行结果，不进行可视化
            if (tool === 'sql_inter') {
              try {
                const sqlResult = JSON.parse(result);
                if (sqlResult.columns && sqlResult.rows && Array.isArray(sqlResult.rows)) {
                  // 只显示执行结果信息，不进行可视化
                  const rowCount = sqlResult.row_count || sqlResult.rows.length;
                  const toolResultText = settings.language === 'zh'
                    ? `\n\n✅ SQL查询执行成功，返回 ${rowCount} 条结果`
                    : `\n\n✅ SQL query executed successfully, returned ${rowCount} rows`;
                  contentText += toolResultText;
                  
                  // 更新消息，不添加executionResult（不进行可视化）
                  setSessions(prev => prev.map(s => s.id === currentSessionId ? {
                    ...s,
                    messages: s.messages.map(m => m.id === botMsgId ? {
                      ...m,
                      content: contentText,
                      // 不设置executionResult，这样前端不会显示可视化
                      status: Object.keys(toolStatus).length > 0 ? 'executing' as const : 'thinking' as const
                    } : m)
                  } : s));
                  
                  delete toolStatus[tool];
                  return; // 提前返回，不执行后面的通用处理
                }
              } catch (e) {
                console.error('Failed to parse SQL result:', e);
                // 如果解析失败，fallback到普通显示
              }
            }
            
            // 其他工具或解析失败的情况：显示格式化预览
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
        // onError: 错误处理
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
        // onComplete: 完成
        () => {
          // 改进的完成逻辑：基于标志位判断
          if (!hasReceivedText && !hasReceivedToolCall && !hasReceivedToolResult) {
            // 完全没有收到任何内容，说明可能有错误
            contentText = settings.language === 'zh' 
              ? '❌ 分析完成，但未收到响应内容。' 
              : '❌ Analysis completed, but no response content received.';
          } else if (!hasReceivedText && hasReceivedToolResult) {
            // 收到了工具调用和执行结果，但没有收到文本回答
            // 检查contentText是否为空或只有初始提示
            if (!contentText || contentText === initialContent || contentText.trim() === '') {
              // 工具已执行但没有最终回答，添加提示
              const toolHint = settings.language === 'zh'
                ? '\n\n✅ 分析已完成。工具执行成功，但未生成文本回答。'
                : '\n\n✅ Analysis completed. Tools executed successfully, but no text response was generated.';
              contentText = (contentText === initialContent ? '' : contentText) + toolHint;
            }
          } else if (contentText === initialContent) {
            // 仍然是最初的提示，但有内容，替换掉
            // 这种情况理论上不应该发生，但作为兜底处理
            if (hasReceivedText) {
              // 如果确实收到过文本，不应该还是initialContent，但为了安全起见
              contentText = settings.language === 'zh' 
                ? '✅ 分析完成。' 
                : '✅ Analysis completed.';
            }
          } else {
            // 检查最终内容是否有图标，如果没有则添加
            const hasIcon = /^[🔧📊✅❌💡📝🤔]/.test(contentText.trim());
            if (!hasIcon && contentText.trim() && contentText !== initialContent) {
              const iconPrefix = settings.language === 'zh' 
                ? '💡 ' 
                : '💡 ';
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
        // signal: 中断信号
        controller.signal
      );

      // 保存停止函数以便用户中断
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

        // 停止之前的流式请求（如果有）
        if (streamController) {
          streamController.abort();
        }

        // 移除之前的summary消息（如果存在），避免重复
        setSessions(prev => prev.map(s => s.id === currentSessionId ? {
          ...s,
          messages: s.messages.filter(m => m.id !== currentSessionId + '_summary')
        } : s));

        // 创建中断控制器
        const controller = new AbortController();
        setStreamController(controller);
        setIsStreaming(true);

        // 创建初始摘要消息（先创建，再开始流式更新）
        const summaryMessageId = currentSessionId + '_summary';
        const summaryMessage: Message = {
          id: summaryMessageId,
          role: 'model',
          content: "",  // 初始为空，通过流式更新
          timestamp: Date.now()
        };

        // 先添加消息到列表
        setSessions(prev => prev.map(s => s.id === currentSessionId ? {
          ...s,
          messages: [...s.messages, summaryMessage]
        } : s));

        let summaryText = "";
        let hasError = false;

        try {
          // 流式获取摘要
          const stopStream = api.getDbSummaryStream(
            result.id,
            settings.customApiKey,
            settings.customBaseUrl,
            settings.model,
            // 实时接收chunk - 打字机效果
            (chunk: string) => {
              summaryText += chunk;
              // 实时更新UI
              setSessions(prev => prev.map(s => s.id === currentSessionId ? {
                ...s,
                messages: s.messages.map(m =>
                  m.id === summaryMessageId ?
                    { ...m, content: summaryText } : m
                )
              } : s));
            },
            // 错误处理
            (error: string) => {
              console.error("Summary stream error:", error);
              hasError = true;
              summaryText = settings.language === 'zh'
                ? `摘要生成失败: ${error}`
                : `Summary generation failed: ${error}`;
              // 更新消息内容
              setSessions(prev => prev.map(s => s.id === currentSessionId ? {
                ...s,
                messages: s.messages.map(m =>
                  m.id === summaryMessageId ?
                    { ...m, content: summaryText } : m
                )
              } : s));
              setIsStreaming(false);
              setStreamController(null);
            },
            // 完成处理
            () => {
              setIsStreaming(false);
              setStreamController(null);
            },
            // 中断信号
            controller.signal
          );
        } catch (sumErr) {
          console.error("Summary failed", sumErr);
          hasError = true;
          summaryText = settings.language === 'zh'
            ? "文件上传成功。请提问以开始分析。"
            : "File uploaded. Ask questions to analyze.";
          // 更新消息内容
          setSessions(prev => prev.map(s => s.id === currentSessionId ? {
            ...s,
            messages: s.messages.map(m =>
              m.id === summaryMessageId ?
                { ...m, content: summaryText } : m
            )
          } : s));
          setIsStreaming(false);
          setStreamController(null);
        }
        
        if (currentSession.messages.length === 0) {
           setSessions(prev => prev.map(s => s.id === currentSessionId ? { ...s, title: file.name } : s));
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
                title="选择AI模型"
                style={{
                  backgroundImage: `url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6,9 12,15 18,9'%3e%3c/polyline%3e%3c/svg%3e")`,
                  backgroundRepeat: 'no-repeat',
                  backgroundPosition: 'right 2px center',
                  backgroundSize: '16px',
                  paddingRight: '24px'
                }}
              >
                {AVAILABLE_MODELS.map((model) => (
                  <option
                    key={model.value}
                    value={model.value}
                    className="bg-[#2a2b2d] text-text hover:bg-[#353638]"
                  >
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

          {/* 流式生成状态指示器 - 只在数据库摘要生成时显示 */}
          {isStreaming && !settings.dbConfig.fileId && (
            <div className="flex items-center gap-3 p-4 mx-4 mb-4 bg-[#2a2b2d] rounded-lg border border-accent/30">
              <div className="w-6 h-6 rounded-full bg-accent flex items-center justify-center">
                <Loader2 size={14} className="animate-spin text-white" />
              </div>
              <div className="flex-1">
                <div className="text-sm text-text font-medium">
                  {settings.language === 'zh' ? '正在生成数据库摘要...' : 'Generating database summary...'}
                </div>
                <div className="text-xs text-subtext">
                  {settings.language === 'zh' ? '内容将实时显示' : 'Content will appear in real-time'}
                </div>
              </div>
              <button
                onClick={stopStreaming}
                className="px-3 py-1.5 text-xs font-medium text-red-400 hover:text-red-300 bg-red-400/10 hover:bg-red-400/20 rounded-md border border-red-400/20 hover:border-red-400/30 transition-colors"
              >
                {settings.language === 'zh' ? '停止生成' : 'Stop'}
              </button>
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
                <MessageBubble 
                    key={msg.id} 
                    message={msg} 
                    language={settings.language} 
                />
              ))}
              {/* 只在没有模型消息显示思考/执行状态时才显示独立的加载指示器 */}
              {isProcessing && !currentSession?.messages.some(m => 
                m.role === 'model' && (m.status === 'thinking' || m.status === 'executing')
              ) && (
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
