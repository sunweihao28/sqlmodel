export interface TableSchema {
  tableName: string;
  columns: string[];
  description?: string;
}

export enum ChartType {
  BAR = 'bar',
  LINE = 'line',
  PIE = 'pie',
  TABLE = 'table'
}

export interface SqlResult {
  sql: string;
  data: any[];
  explanation: string;
  chartType: ChartType;
  xAxisKey?: string;
  dataKeys?: string[];
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  sqlResult?: SqlResult;
  isLoading?: boolean;
}

export interface AppState {
  apiKey: string;
  schema: TableSchema[];
  chatHistory: Message[];
  isSidebarOpen: boolean;
}