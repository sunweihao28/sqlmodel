
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

export type MessageStatus = 'thinking' | 'pending_approval' | 'executing' | 'executed' | 'error';

export interface Message {
  id: string;
  role: Role;
  content: string;
  timestamp: number;
  
  // Extras for model responses
  status?: MessageStatus;
  sqlQuery?: string;
  executionResult?: SqlResult;
  error?: string;
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
