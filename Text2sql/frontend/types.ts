
export type Role = 'user' | 'model';

export type ChartType = 'bar' | 'line' | 'pie' | 'table';
export type DisplayType = 'table' | 'chart' | 'both'; 

export interface VisualizationConfig {
  type: ChartType;
  title?: string;
  displayType?: DisplayType;
  xAxis?: {
    key: string;
    label?: string;
  };
  yAxis?: {
    key?: string;
    label?: string;
  };
  data: any[];
  series?: Array<{
    key: string;
    name?: string;
  }>;
}

export interface User {
  id: string;
  name: string;
  email: string;
  avatar?: string;
  token?: string;
}

export interface SqlResult {
  columns: string[];
  data: any[];
  chartTypeSuggestion: ChartType;
  summary: string;
  visualizationConfig?: VisualizationConfig;
  displayType?: DisplayType;
}

export type MessageStatus = 'thinking' | 'pending_approval' | 'executing' | 'executed' | 'error';

export interface Message {
  id: string;
  role: Role;
  content: string;
  timestamp: number;
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
  fileId?: number;
  connectionId?: number; // [Added]
  backendId?: string;
}

export interface DbConfig {
  type: 'postgres' | 'mysql' | 'sqlite';
  host: string;
  port: string;
  database: string;
  user: string;
  password: string;
  uploadedPath?: string;
  fileId?: number;
  connectionId?: number; // [Added]
}

export interface AppSettings {
  language: 'en' | 'zh';
  model: string;
  customBaseUrl?: string;
  customApiKey?: string;
  useSimulationMode: boolean;
  useRag: boolean;
  enableMemory: boolean; // [New]
  dbConfig: DbConfig;
}

export interface RagDocument {
  id: string;
  name: string;
}

// 可用的模型选项
export const AVAILABLE_MODELS = [
  { value: 'gpt-4o', label: 'GPT-4o', provider: 'OpenAI' },
  { value: 'gpt-5.2', label: 'GPT-5.2', provider: 'OpenAI' },
  { value: 'gemini-3-flash-preview', label: 'gemini-3-flash-preview', provider: 'Google' },
  { value: 'deepseek-v3.2', label: 'DeepSeek V3.2', provider: 'DeepSeek' }
] as const;

export type ModelOption = typeof AVAILABLE_MODELS[number];