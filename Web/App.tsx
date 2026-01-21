import React, { useState, useEffect, useRef } from 'react';
import { 
  Send, Database, History, LayoutDashboard, Settings, 
  ChevronLeft, ChevronRight, Plus, Sparkles, AlertCircle, PlayCircle
} from 'lucide-react';
import { generateSqlAndData } from './services/geminiService';
import SqlPreview from './components/SqlPreview';
import DataVisualizer from './components/DataVisualizer';
import { Message, TableSchema } from './types';

// Default Schema Example (E-commerce)
const DEFAULT_SCHEMA: TableSchema[] = [
  {
    tableName: 'orders',
    columns: ['order_id', 'user_id', 'order_date', 'total_amount', 'status'],
    description: 'All customer orders'
  },
  {
    tableName: 'users',
    columns: ['user_id', 'username', 'email', 'country', 'signup_date'],
    description: 'Registered users'
  },
  {
    tableName: 'products',
    columns: ['product_id', 'name', 'category', 'price', 'stock_quantity'],
    description: 'Product inventory'
  },
  {
    tableName: 'order_items',
    columns: ['item_id', 'order_id', 'product_id', 'quantity', 'unit_price'],
    description: 'Items within an order'
  }
];

const App = () => {
  const [apiKey, setApiKey] = useState<string>('');
  const [schema, setSchema] = useState<TableSchema[]>(DEFAULT_SCHEMA);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState('');
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [showSettings, setShowSettings] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Handle sending a message
  const handleSend = async () => {
    if (!inputText.trim()) return;
    if (!apiKey) {
      setShowSettings(true);
      return;
    }

    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: inputText,
      timestamp: Date.now()
    };

    setMessages(prev => [...prev, userMsg]);
    setInputText('');
    setIsLoading(true);

    try {
      const result = await generateSqlAndData(apiKey, schema, userMsg.content);
      
      const assistantMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: result.explanation,
        timestamp: Date.now(),
        sqlResult: result
      };
      
      setMessages(prev => [...prev, assistantMsg]);
    } catch (error: any) {
      const errorMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `Error: ${error.message}`,
        timestamp: Date.now()
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex h-screen bg-[#131314] text-[#e3e3e3] overflow-hidden">
      
      {/* Sidebar */}
      <div 
        className={`${
          isSidebarOpen ? 'w-64' : 'w-0'
        } bg-[#1e1f20] border-r border-[#444746] transition-all duration-300 flex flex-col overflow-hidden`}
      >
        <div className="p-4 flex items-center gap-2 border-b border-[#444746]">
          <Database className="w-5 h-5 text-[#a8c7fa]" />
          <h1 className="font-semibold text-sm tracking-wide">SQL GENIUS</h1>
        </div>

        <div className="flex-1 overflow-y-auto p-2">
          <div className="mb-6">
            <h2 className="text-xs font-medium text-gray-500 uppercase px-2 mb-2">Database Schema</h2>
            {schema.map((table) => (
              <div key={table.tableName} className="px-2 py-1.5 hover:bg-[#2d2e2f] rounded cursor-pointer group">
                <div className="flex items-center gap-2 text-sm text-[#e3e3e3]">
                  <LayoutDashboard size={14} className="text-[#a8c7fa]" />
                  <span>{table.tableName}</span>
                </div>
                <div className="text-[10px] text-gray-500 pl-6 hidden group-hover:block truncate">
                  {table.columns.join(', ')}
                </div>
              </div>
            ))}
             <button 
                className="w-full mt-2 text-xs flex items-center justify-center gap-1 py-1.5 border border-dashed border-[#444746] rounded text-gray-400 hover:text-white hover:border-gray-400 transition"
                onClick={() => alert("功能开发中：支持导入自定义 Schema")}
             >
               <Plus size={12} /> Import Schema
             </button>
          </div>

          <div>
             <h2 className="text-xs font-medium text-gray-500 uppercase px-2 mb-2">History</h2>
             {messages.filter(m => m.role === 'user').map(m => (
               <div key={m.id} className="px-2 py-2 text-xs text-gray-400 hover:bg-[#2d2e2f] rounded truncate cursor-pointer">
                 {m.content}
               </div>
             ))}
          </div>
        </div>

        <div className="p-4 border-t border-[#444746]">
          <button 
            onClick={() => setShowSettings(!showSettings)}
            className="flex items-center gap-2 text-sm text-gray-400 hover:text-white transition"
          >
            <Settings size={16} />
            Settings
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col h-full relative">
        
        {/* Header */}
        <header className="h-14 border-b border-[#444746] flex items-center px-4 justify-between bg-[#131314]">
          <button 
            onClick={() => setIsSidebarOpen(!isSidebarOpen)}
            className="p-1.5 hover:bg-[#2d2e2f] rounded-full text-gray-400"
          >
            {isSidebarOpen ? <ChevronLeft size={20} /> : <ChevronRight size={20} />}
          </button>
          
          <div className="flex items-center gap-2 bg-[#2d2e2f] px-3 py-1.5 rounded-full">
            <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
            <span className="text-xs font-medium text-gray-300">Agent Active • Gemini 2.5 Flash</span>
          </div>

          <div className="w-8"></div> {/* Spacer */}
        </header>

        {/* Chat Area */}
        <main className="flex-1 overflow-y-auto p-4 md:p-8 scroll-smooth">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center max-w-2xl mx-auto opacity-80">
              <div className="w-16 h-16 bg-[#1e1f20] rounded-2xl flex items-center justify-center mb-6 shadow-lg border border-[#444746]">
                <Sparkles className="w-8 h-8 text-[#a8c7fa]" />
              </div>
              <h2 className="text-2xl font-semibold mb-2 bg-gradient-to-r from-[#a8c7fa] to-[#669df6] bg-clip-text text-transparent">
                How can I help you analyze data?
              </h2>
              <p className="text-gray-400 mb-8 max-w-md">
                I can transform your natural language questions into SQL, execute them, and visualize the results.
              </p>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full">
                {['Show total sales by category', 'List top 5 users by spend', 'Daily order trend for last month', 'Products with low stock'].map((q) => (
                  <button 
                    key={q}
                    onClick={() => setInputText(q)}
                    className="p-4 bg-[#1e1f20] border border-[#444746] rounded-xl text-sm text-left hover:bg-[#2d2e2f] hover:border-[#669df6] transition-all group"
                  >
                    <span className="group-hover:text-[#a8c7fa]">{q}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="max-w-4xl mx-auto space-y-8 pb-10">
              {messages.map((msg) => (
                <div key={msg.id} className={`flex gap-4 ${msg.role === 'assistant' ? 'bg-[#18191a] -mx-4 p-4 md:rounded-xl md:mx-0' : ''}`}>
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
                    msg.role === 'user' ? 'bg-[#2d2e2f] text-white' : 'bg-gradient-to-br from-[#4c8df6] to-[#a8c7fa] text-[#131314]'
                  }`}>
                    {msg.role === 'user' ? 'U' : <Sparkles size={16} />}
                  </div>
                  
                  <div className="flex-1 min-w-0">
                    <div className="prose prose-invert max-w-none text-sm leading-relaxed">
                      {msg.role === 'user' ? (
                        <p className="text-lg font-medium">{msg.content}</p>
                      ) : (
                        <div>
                          <p className="mb-4 text-gray-300">{msg.content}</p>
                          {msg.sqlResult && (
                            <div className="space-y-6 animate-fade-in">
                              <SqlPreview sql={msg.sqlResult.sql} />
                              <div className="bg-[#1e1f20] border border-[#444746] rounded-xl p-4">
                                <div className="flex items-center gap-2 mb-4">
                                  <PlayCircle size={16} className="text-[#a8c7fa]" />
                                  <span className="text-xs font-bold uppercase tracking-wider text-gray-400">Result Visualization</span>
                                </div>
                                <DataVisualizer result={msg.sqlResult} />
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
              {isLoading && (
                 <div className="flex gap-4 bg-[#18191a] p-4 rounded-xl max-w-4xl mx-auto">
                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#4c8df6] to-[#a8c7fa] flex items-center justify-center animate-pulse">
                      <Sparkles size={16} className="text-[#131314]" />
                    </div>
                    <div className="flex flex-col gap-2">
                       <div className="h-4 w-32 bg-[#2d2e2f] rounded animate-pulse"></div>
                       <div className="h-20 w-full md:w-96 bg-[#2d2e2f] rounded animate-pulse"></div>
                    </div>
                 </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </main>

        {/* Input Area */}
        <div className="p-4 bg-[#131314] border-t border-[#444746]">
          <div className="max-w-4xl mx-auto relative">
             <input
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              placeholder={apiKey ? "Ask a question about your data..." : "Please configure your API Key first"}
              className="w-full bg-[#1e1f20] border border-[#444746] text-white rounded-full py-4 pl-6 pr-14 focus:outline-none focus:ring-2 focus:ring-[#669df6] transition shadow-lg placeholder-gray-500"
              disabled={isLoading}
            />
            <button
              onClick={handleSend}
              disabled={!inputText.trim() || isLoading || !apiKey}
              className="absolute right-2 top-2 p-2 bg-[#a8c7fa] text-[#131314] rounded-full hover:bg-[#8ab4f8] disabled:opacity-50 disabled:cursor-not-allowed transition"
            >
              <Send size={20} />
            </button>
          </div>
          <p className="text-center text-[10px] text-gray-500 mt-2">
             AI can make mistakes. Please double check the generated SQL.
          </p>
        </div>

        {/* Settings Modal */}
        {showSettings && (
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-[#1e1f20] border border-[#444746] rounded-2xl p-6 w-full max-w-md shadow-2xl">
              <h3 className="text-xl font-semibold mb-4 text-white">Settings</h3>
              
              <div className="mb-6">
                <label className="block text-xs font-medium text-gray-400 mb-2 uppercase">Google Gemini API Key</label>
                <div className="relative">
                  <input 
                    type="password" 
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder="AIza..."
                    className="w-full bg-[#131314] border border-[#444746] rounded-lg p-3 text-white focus:border-[#669df6] focus:outline-none"
                  />
                  {!apiKey && (
                    <div className="mt-2 flex items-center gap-2 text-yellow-500 text-xs">
                      <AlertCircle size={12} />
                      <span>Required to generate SQL</span>
                    </div>
                  )}
                </div>
                <p className="text-[10px] text-gray-500 mt-2">
                  Your key is stored only in the browser's memory and used directly with the Gemini API.
                </p>
              </div>

              <div className="flex justify-end">
                <button 
                  onClick={() => setShowSettings(false)}
                  className="px-4 py-2 bg-[#a8c7fa] text-[#131314] rounded-lg font-medium hover:bg-[#8ab4f8] transition"
                >
                  Done
                </button>
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  );
};

export default App;