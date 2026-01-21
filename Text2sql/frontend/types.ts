
export type Role = 'user' | 'model';

export type ChartType = 'bar' | 'line' | 'pie' | 'table';
export type DisplayType = 'table' | 'chart' | 'both'; // 显示类型：仅表格、仅图表、两者都显示

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
  token?: string; // JWT Token (Mock)
}

export interface SqlResult {
  columns: string[];
  data: any[];
  chartTypeSuggestion: ChartType;
  summary: string;
  visualizationConfig?: VisualizationConfig; // Python生成的可视化配置
  displayType?: DisplayType; // 显示类型（默认：'both'，保持向后兼容）
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

// 可用的模型选项
export const AVAILABLE_MODELS = [
  { value: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash', provider: 'Google' },
  { value: 'gpt-4o', label: 'GPT-4o', provider: 'OpenAI' }
] as const;

export type ModelOption = typeof AVAILABLE_MODELS[number];