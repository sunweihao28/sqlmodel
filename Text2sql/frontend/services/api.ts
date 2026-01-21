
import { User, SqlResult, Message } from '../types';

// Points to your local FastAPI backend
export const API_URL = 'http://localhost:8000/api';

const getHeaders = (): Record<string, string> => {
  try {
    const base: Record<string, string> = { 'Content-Type': 'application/json' };
    const userStr = localStorage.getItem('current_user');
    if (!userStr) {
      console.warn('No user data found in localStorage');
      return base;
    }

    const user = JSON.parse(userStr);
    if (!user || !user.token) {
      console.warn('Invalid user data - missing token:', user);
      return base;
    }

    return {
      ...base,
      Authorization: `Bearer ${user.token}`,
    };
  } catch (error) {
    console.error('Error reading user data from localStorage:', error);
    return { 'Content-Type': 'application/json' };
  }
};

export const api = {
  // Login
  login: async (email: string, password: string): Promise<User> => {
    const formData = new URLSearchParams();
    formData.append('username', email); 
    formData.append('password', password);

    try {
      const response = await fetch(`${API_URL}/auth/token`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Login failed');
      }

      const data = await response.json();
      
      return {
        id: email, 
        name: data.user_name,
        email: data.user_email,
        token: data.access_token,
        avatar: `https://api.dicebear.com/7.x/avataaars/svg?seed=${data.user_email}`
      };
    } catch (error: any) {
       console.error("Login API Error:", error);
       if (error.message && error.message.includes("Failed to fetch")) {
         throw new Error("Could not connect to backend. Please ensure 'python main.py' is running on port 8000.");
       }
       throw error;
    }
  },

  // Register
  register: async (email: string, password: string, fullName: string): Promise<User> => {
    try {
      const response = await fetch(`${API_URL}/auth/register`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          email,
          password,
          full_name: fullName
        }),
      });

      if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.detail || 'Registration failed');
      }

      return api.login(email, password);
    } catch (error: any) {
        console.error("Register API Error:", error);
        if (error.message && error.message.includes("Failed to fetch")) {
           throw new Error("Could not connect to backend. Please ensure 'python main.py' is running on port 8000.");
        }
        throw error;
    }
  },

  // Upload File
  uploadFile: async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);

    const userStr = localStorage.getItem('current_user');
    const headers: Record<string, string> = {};
    if (userStr) {
        const user = JSON.parse(userStr);
        headers['Authorization'] = `Bearer ${user.token}`;
    }

    try {
      const response = await fetch(`${API_URL}/files/upload`, {
        method: 'POST',
        headers: headers,
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Upload failed');
      }

      return await response.json(); 
    } catch (error) {
      handleApiError(error, "Upload");
    }
  },

  // Get Summary
  getDbSummary: async (fileId: number, apiKey?: string, baseUrl?: string, model?: string): Promise<string> => {
    try {
      const response = await fetch(`${API_URL}/chat/summary`, {
          method: 'POST',
          headers: getHeaders(),
          body: JSON.stringify({
              file_id: fileId,
              api_key: apiKey || null,
              base_url: baseUrl || null,
              model: model || null
          })
      });

      if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.detail || 'Summary generation failed');
      }

      const data = await response.json();
      return data.summary;
    } catch (error) {
      handleApiError(error, "Summary");
      throw error;
    }
  },

  // STEP 1: Generate SQL Draft (Human-in-the-loop)
  generateSqlDraft: async (message: string, history: Message[], fileId: number, apiKey?: string, baseUrl?: string, model?: string): Promise<string> => {
    const formattedHistory = history.slice(-10).map(msg => ({
        role: msg.role,
        content: msg.content
    }));

    try {
        const response = await fetch(`${API_URL}/chat/generate`, {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({
                message,
                file_id: fileId,
                history: formattedHistory,
                api_key: apiKey || null,
                base_url: baseUrl || null,
                model: model || null
            })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Generation failed');
        }

        const data = await response.json();
        return data.sql;
    } catch (error) {
        handleApiError(error, "Generation");
        throw error;
    }
  },

  // STEP 2: Execute SQL
  executeSql: async (sql: string, originalMessage: string, fileId: number, apiKey?: string, baseUrl?: string, model?: string): Promise<{ answer: string, sql: string, columns: string[], data: any[] }> => {
    try {
        const response = await fetch(`${API_URL}/chat/execute`, {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({
                sql,
                message: originalMessage,
                file_id: fileId,
                api_key: apiKey || null,
                base_url: baseUrl || null,
                model: model || null
            })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Execution failed');
        }

        return await response.json();
    } catch (error) {
        handleApiError(error, "Execution");
        throw error;
    }
  },

  // Stream Summary (流式获取摘要)
  getDbSummaryStream: (
    fileId: number,
    apiKey?: string,
    baseUrl?: string,
    model?: string,
    onChunk?: (chunk: string) => void,
    onError?: (error: string) => void,
    onComplete?: () => void,
    signal?: AbortSignal
  ): (() => void) => {
    const controller = signal instanceof AbortController ? signal : new AbortController();

    fetch(`${API_URL}/chat/summary/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...getHeaders(),
      },
      body: JSON.stringify({
        file_id: fileId,
        api_key: apiKey || null,
        base_url: baseUrl || null,
        model: model || null,
      }),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok || !response.body) {
          const msg = `HTTP ${response.status}`;
          onError?.(msg);
          return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const parts = buffer.split('\n\n');
          buffer = parts.pop() || '';

          for (const part of parts) {
            const line = part.trim();
            if (!line.startsWith('data:')) continue;

            const payload = line.slice(5).trim();
            if (payload === '[DONE]') {
              onComplete?.();
              controller.abort();
              return;
            }

            try {
              const data = JSON.parse(payload);
              if (data.chunk) onChunk?.(data.chunk);
              else if (data.error) onError?.(data.error);
            } catch (e: any) {
              onError?.(`Parse error: ${e?.message || e}`);
            }
          }
        }

        onComplete?.();
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        onError?.(err?.message || String(err));
      });

    // 返回取消函数
    return () => controller.abort();
  },

  // Agent流式分析 (Agent Analysis with Streaming)
  agentAnalyzeStream: (
    message: string,
    fileId: number,
    history: Message[],
    apiKey?: string,
    baseUrl?: string,
    model?: string,
    maxToolRounds?: number,
    onText?: (text: string) => void,
    onToolCall?: (tool: string, status: string, sqlCode?: string) => void,
    onToolResult?: (tool: string, result: string, status: string) => void,
    onError?: (error: string) => void,
    onComplete?: () => void,
    signal?: AbortSignal
  ): (() => void) => {
    const controller = signal instanceof AbortController ? signal : new AbortController();

    fetch(`${API_URL}/chat/agent/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...getHeaders(),
      },
      body: JSON.stringify({
        message,
        file_id: fileId,
        history: history.map(m => ({ role: m.role, content: m.content })),
        api_key: apiKey || null,
        base_url: baseUrl || null,
        model: model || null,
        max_tool_rounds: maxToolRounds || 12
      }),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok || !response.body) {
          const msg = `HTTP ${response.status}`;
          onError?.(msg);
          return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        while (true) {
          const { value, done } = await reader.read();
          
          if (value) {
            buffer += decoder.decode(value, { stream: true });
            const parts = buffer.split('\n\n');
            buffer = parts.pop() || '';

            for (const part of parts) {
              const line = part.trim();
              if (!line.startsWith('data:')) continue;

              const payload = line.slice(5).trim();
              if (payload === '[DONE]') {
                onComplete?.();
                return;
              }

              try {
                const event = JSON.parse(payload);
                switch (event.type) {
                  case 'text':
                    onText?.(event.content);
                    break;
                case 'tool_call':
                  onToolCall?.(event.tool, event.status, event.sql_code);
                  break;
                  case 'tool_result':
                    onToolResult?.(event.tool, event.result, event.status);
                    break;
                  case 'error':
                    onError?.(event.error);
                    break;
                  case 'done':
                    onComplete?.();
                    break;
                }
              } catch (e: any) {
                console.error('Failed to parse SSE event:', e);
                onError?.(`Parse error: ${e?.message || e}`);
              }
            }
          }
          
          if (done) {
            // 处理剩余的buffer
            if (buffer.trim()) {
              const line = buffer.trim();
              if (line.startsWith('data:')) {
                const payload = line.slice(5).trim();
                if (payload === '[DONE]') {
                  onComplete?.();
                  return;
                }
                try {
                  const event = JSON.parse(payload);
                  if (event.type === 'done') {
                    onComplete?.();
                    return;
                  }
                } catch (e) {
                  // 忽略解析错误
                }
              }
            }
            // 如果流结束了但没有收到done事件，也调用onComplete
            onComplete?.();
            break;
          }
        }
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        onError?.(err?.message || String(err));
      });

    // 返回取消函数
    return () => controller.abort();
  },
};

// 全局错误处理函数
const handleApiError = (error: any, operation: string) => {
  console.error(`${operation} API Error:`, error);

  // 检查是否是认证错误
  if (error.message && error.message.includes("401")) {
    console.warn("Authentication token expired or invalid, clearing user session");
    localStorage.removeItem('current_user');
    // 触发页面刷新来重新初始化应用状态
    window.location.reload();
    return;
  }

  if (error.message && error.message.includes("Failed to fetch")) {
    throw new Error("Could not connect to backend. Please ensure 'python main.py' is running on port 8000.");
  }
  throw error;
};
