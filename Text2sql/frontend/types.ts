
export type Role = 'user' | 'model';

export type ChartType = 'bar' | 'line' | 'pie' | 'table';
export type DisplayType = 'table' | 'chart' | 'both'; 

export interface VisualizationConfig {
  type: ChartType;  // 图表类型
  title?: string;   // 图表标题
  displayType?: DisplayType; // 显示类型（默认：'both'，保持向后兼容）
  xAxis?: {
    key: string;    // X轴数据字段名
    label?: string; // X轴标签
  };
  yAxis?: {
    key?: string;   // Y轴数据字段名（可选，用于多系列）
    label?: string; // Y轴标签
  };
  data: any[];      // 图表数据（对象数组）
  series?: Array<{  // 数据系列（用于多系列图表）
    key: string;    // 数据字段名
    name?: string;  // 系列名称
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
}

export interface AppSettings {
  language: 'en' | 'zh';
  model: string;
  customBaseUrl?: string;
  customApiKey?: string;
  useSimulationMode: boolean;
  useRag: boolean; // [新增]
  dbConfig: DbConfig;
}

// [新增] RAG Document
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