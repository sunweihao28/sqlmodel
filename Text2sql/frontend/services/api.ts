
import { User, SqlResult } from '../types';

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
    // FormData is required for OAuth2PasswordRequestForm in FastAPI
    const formData = new URLSearchParams();
    formData.append('username', email); // OAuth2 expects 'username' (we use email)
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
        id: email, // Use email as ID
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

      // After registration, auto-login
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

    // Headers for upload (do NOT set Content-Type, browser sets it with boundary)
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

      return await response.json(); // Returns { id, filename, file_path, ... }
    } catch (error) {
      console.error("Upload API Error:", error);
      throw error;
    }
  },

  // Get Summary
  getDbSummary: async (fileId: number, apiKey?: string): Promise<string> => {
    try {
      const response = await fetch(`${API_URL}/chat/summary`, {
          method: 'POST',
          headers: getHeaders(),
          body: JSON.stringify({
              file_id: fileId,
              api_key: apiKey || null
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

  // Chat / Analyze Data
  analyzeData: async (message: string, fileId: number, apiKey?: string): Promise<{ answer: string, sql: string, columns: string[], data: any[] }> => {
    try {
        const response = await fetch(`${API_URL}/chat/analyze`, {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({
                message,
                file_id: fileId,
                api_key: apiKey || null
            })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Analysis failed');
        }

        return await response.json();
    } catch (error) {
        console.error("Analysis API Error:", error);
        throw error;
    }
  }
};
