
import { User, Session, Message, RagDocument, DbConfig } from '../types';

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

  // Connect Database (New)
  saveDatabaseConnection: async (config: DbConfig) => {
      try {
          const response = await fetch(`${API_URL}/db/connect`, {
              method: 'POST',
              headers: getHeaders(),
              body: JSON.stringify({
                  type: config.type,
                  host: config.host,
                  port: config.port,
                  database: config.database,
                  user: config.user,
                  password: config.password
              })
          });

          if (!response.ok) {
              const errorData = await response.json().catch(() => ({}));
              throw new Error(errorData.detail || 'Connection failed');
          }
          return await response.json(); // Returns {id, message}
      } catch (error) {
          handleApiError(error, "Connect DB");
      }
  },

  // --- RAG APIs ---
  uploadRagDocument: async (file: File, apiKey?: string, baseUrl?: string) => {
    const formData = new FormData();
    formData.append('file', file);
    if (apiKey) formData.append('api_key', apiKey);
    if (baseUrl) formData.append('base_url', baseUrl);

    const userStr = localStorage.getItem('current_user');
    const headers: Record<string, string> = {};
    if (userStr) {
        const user = JSON.parse(userStr);
        headers['Authorization'] = `Bearer ${user.token}`;
    }

    try {
      const response = await fetch(`${API_URL}/rag/upload`, {
        method: 'POST',
        headers: headers,
        body: formData,
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: "Upload failed" }));
        throw new Error(err.detail || 'Upload failed');
      }
      return await response.json();
    } catch (error) {
      handleApiError(error, "Upload Doc");
      throw error;
    }
  },

  getRagDocuments: async (): Promise<RagDocument[]> => {
    try {
      const response = await fetch(`${API_URL}/rag/documents`, {
        headers: getHeaders()
      });
      if (!response.ok) throw new Error('Failed to fetch documents');
      return await response.json();
    } catch (error) {
      handleApiError(error, "Get Docs");
      throw error;
    }
  },

  deleteRagDocument: async (docId: string) => {
    try {
      const response = await fetch(`${API_URL}/rag/documents/${docId}`, {
        method: 'DELETE',
        headers: getHeaders()
      });
      if (!response.ok) throw new Error('Failed to delete document');
      return await response.json();
    } catch (error) {
      handleApiError(error, "Delete Doc");
      throw error;
    }
  },

  // --- Session Management ---

  getSessions: async (): Promise<Session[]> => {
    try {
        const response = await fetch(`${API_URL}/chat/sessions`, {
          headers: getHeaders()
        });
        if (!response.ok) throw new Error('Failed to fetch sessions');
        return await response.json();
    } catch (error) {
        handleApiError(error, "Get Sessions");
        throw error;
    }
  },

  createSession: async (fileId?: number, title?: string, connectionId?: number): Promise<Session> => {
    try {
        const response = await fetch(`${API_URL}/chat/sessions`, {
          method: 'POST',
          headers: getHeaders(),
          body: JSON.stringify({ file_id: fileId, connection_id: connectionId, title })
        });
        if (!response.ok) throw new Error('Failed to create session');
        return await response.json();
    } catch (error) {
        handleApiError(error, "Create Session");
        throw error;
    }
  },

  deleteSession: async (sessionId: string) => {
    try {
        const response = await fetch(`${API_URL}/chat/sessions/${sessionId}`, {
          method: 'DELETE',
          headers: getHeaders()
        });
        if (!response.ok) throw new Error('Failed to delete session');
        return await response.json();
    } catch (error) {
        handleApiError(error, "Delete Session");
        throw error;
    }
  },

  getSessionMessages: async (sessionId: string): Promise<Message[]> => {
    try {
        const response = await fetch(`${API_URL}/chat/sessions/${sessionId}/messages`, {
          headers: getHeaders()
        });
        if (!response.ok) throw new Error('Failed to fetch messages');
        return await response.json();
    } catch (error) {
        handleApiError(error, "Get Messages");
        throw error;
    }
  },

  generateSqlDraft: async (
    query: string,
    history: Message[],
    fileId?: number,
    apiKey?: string,
    baseUrl?: string,
    model?: string,
    connectionId?: number
  ): Promise<string> => {
    try {
      const response = await fetch(`${API_URL}/chat/generate_sql`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({
          message: query,
          history: history.map(m => ({ role: m.role, content: m.content })),
          file_id: fileId,
          connection_id: connectionId,
          api_key: apiKey || null,
          base_url: baseUrl || null,
          model: model || null
        })
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to generate SQL');
      }

      const data = await response.json();
      return data.sql;
    } catch (error) {
      handleApiError(error, "Generate SQL");
      throw error;
    }
  },

  executeSql: async (
    sql: string,
    originalMessage: string,
    fileId?: number,
    apiKey?: string,
    baseUrl?: string,
    model?: string,
    connectionId?: number
  ): Promise<any> => {
    try {
      const response = await fetch(`${API_URL}/chat/execute_sql`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({
          sql: sql,
          message: originalMessage,
          file_id: fileId,
          connection_id: connectionId,
          api_key: apiKey || null,
          base_url: baseUrl || null,
          model: model || null
        })
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to execute SQL');
      }

      return await response.json();
    } catch (error) {
      handleApiError(error, "Execute SQL");
      throw error;
    }
  },

  getDbSummaryStream: (
    fileId?: number,
    apiKey?: string,
    baseUrl?: string,
    model?: string,
    onChunk?: (chunk: string) => void,
    onError?: (error: string) => void,
    onComplete?: () => void,
    signal?: AbortSignal,
    sessionId?: string,
    connectionId?: number
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
        connection_id: connectionId,
        api_key: apiKey || null,
        base_url: baseUrl || null,
        model: model || null,
        session_id: sessionId || null
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

    return () => controller.abort();
  },

  agentAnalyzeStream: (
    message: string,
    sessionId: string,
    fileId: number | undefined,
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
    signal?: AbortSignal,
    useRag: boolean = false,
    connectionId?: number,
    enableMemory: boolean = false,
    allowAutoExecute: boolean = true,
    useSqlExpert: boolean = false
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
        session_id: sessionId,
        file_id: fileId,
        connection_id: connectionId,
        history: history.map(m => ({ role: m.role, content: m.content })),
        api_key: apiKey || null,
        base_url: baseUrl || null,
        model: model || null,
        max_tool_rounds: maxToolRounds || 12,
        use_rag: useRag,
        enable_memory: enableMemory,
        allow_auto_execute: allowAutoExecute,
        use_sql_expert: useSqlExpert
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
            onComplete?.();
            break;
          }
        }
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        onError?.(err?.message || String(err));
      });

    return () => controller.abort();
  },
  
  // Refresh Memory [New Method]
  refreshMemory: async (apiKey?: string, baseUrl?: string, model?: string) => {
      try {
          const response = await fetch(`${API_URL}/chat/memory/refresh`, {
              method: 'POST',
              headers: getHeaders(),
              body: JSON.stringify({
                  api_key: apiKey || null,
                  base_url: baseUrl || null,
                  model: model || null
              })
          });

          if (!response.ok) {
              const errorData = await response.json().catch(() => ({}));
              throw new Error(errorData.detail || 'Memory refresh failed');
          }
          return await response.json();
      } catch (error) {
          handleApiError(error, "Refresh Memory");
      }
  },

  // Confirm SQL and Resume
  confirmSql: (
    sessionId: string,
    sql: string,
    apiKey?: string,
    baseUrl?: string,
    model?: string,
    onText?: (text: string) => void,
    onToolCall?: (tool: string, status: string, sqlCode?: string) => void,
    onToolResult?: (tool: string, result: string, status: string) => void,
    onError?: (error: string) => void,
    onComplete?: () => void,
    signal?: AbortSignal
  ): (() => void) => {
    const controller = signal instanceof AbortController ? signal : new AbortController();

    fetch(`${API_URL}/chat/agent/confirm`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...getHeaders(),
      },
      body: JSON.stringify({
        session_id: sessionId,
        sql: sql,
        api_key: apiKey || null,
        base_url: baseUrl || null,
        model: model || null
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
                if (event.type === 'text') onText?.(event.content);
                else if (event.type === 'tool_call') onToolCall?.(event.tool, event.status, event.sql_code);
                else if (event.type === 'tool_result') onToolResult?.(event.tool, event.result, event.status);
                else if (event.type === 'error') onError?.(event.error);
              } catch(e) {}
            }
          }
          if (done) {
            onComplete?.();
            break;
          }
        }
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        onError?.(err?.message || String(err));
      });

    return () => controller.abort();
  },
};

const handleApiError = (error: any, operation: string) => {
  console.error(`${operation} API Error:`, error);
  if (error.message && error.message.includes("401")) {
    console.warn("Authentication token expired or invalid, clearing user session");
    localStorage.removeItem('current_user');
    window.location.reload();
    return;
  }
  if (error.message && error.message.includes("Failed to fetch")) {
    throw new Error("Could not connect to backend. Please ensure 'python main.py' is running on port 8000.");
  }
  throw error;
};