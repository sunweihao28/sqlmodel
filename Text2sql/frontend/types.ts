

export type Role = 'user' | 'model';

export type ChartType = 'bar' | 'line' | 'pie' | 'table';

export interface User {
  id: string;
  name: string;
  email: string;
  avatar?: string;
  token?: string; // JWT Token (Mock)
}

export interface SqlResult {
  columns: string[];
  data: any[];
  chartTypeSuggestion: ChartType;
  summary: string;
}

export interface Message {
  id: string;
  role: Role;
  content: string;
  timestamp: number;
  // Extras for model responses
  sqlQuery?: string;
  executionResult?: SqlResult;
  isThinking?: boolean;
}

export interface Session {
  id: string;
  title: string;
  messages: Message[];
  updatedAt: number;
}

export interface DbConfig {
  type: 'postgres' | 'mysql' | 'sqlite'; // Added sqlite
  host: string;
  port: string;
  database: string;
  user: string;
  password: string;
  uploadedPath?: string; // Name of the file on the server
  fileId?: number; // Added: The ID of the file in the backend database
}

export interface AppSettings {
  language: 'en' | 'zh';
  model: string;
  customBaseUrl?: string; 
  customApiKey?: string;
  
  // Removed backendUrl
  useSimulationMode: boolean;
  dbConfig: DbConfig;
}

export const AVAILABLE_MODELS = [
  { id: 'gemini-2.5-flash', name: 'Gemini 2.5 Flash', provider: 'Google' },
  { id: 'gemini-3-pro-preview', name: 'Gemini 3.0 Pro', provider: 'Google' },
  { id: 'deepseek-r1', name: 'DeepSeek R1', provider: 'DeepSeek' },
  { id: 'qwen-max', name: 'Qwen Max', provider: 'Alibaba' },
  { id: 'doubao-pro', name: 'Doubao Pro', provider: 'ByteDance' },
];
