
import { User, SqlResult, Message } from '../types';

// Points to your local FastAPI backend
const API_URL = 'http://localhost:8000/api';

const getHeaders = () => {
  const userStr = localStorage.getItem('current_user');
  if (!userStr) return {};
  const user = JSON.parse(userStr);
  return {
    'Authorization': `Bearer ${user.token}`,
    'Content-Type': 'application/json'
  };
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
      console.error("Upload API Error:", error);
      throw error;
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
      console.error("Summary API Error:", error);
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
        console.error("Generation API Error:", error);
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
        console.error("Execution API Error:", error);
        throw error;
    }
  }
};
