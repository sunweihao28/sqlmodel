

import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Bot, User, Database, Terminal, Loader2, AlertTriangle, Copy, Check } from 'lucide-react';
import { Message } from '../types';
import DataVisualizer from './DataVisualizer';
import { translations } from '../i18n';

interface Props {
  message: Message;
  language: 'en' | 'zh';
}

const MessageBubble: React.FC<Props> = ({ message, language }) => {
  const isUser = message.role === 'user';
  const t = translations[language];
  const [copied, setCopied] = useState(false);

  const isPending = message.status === 'pending_approval';
  const isExecuting = message.status === 'executing';
  const isError = message.status === 'error';

  const handleCopy = () => {
    if (message.sqlQuery) {
      navigator.clipboard.writeText(message.sqlQuery);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  // 自定义图片组件：隐藏无法加载的图片
  const ImageComponent = ({ src, alt, ...props }: any) => {
    const [imageError, setImageError] = useState(false);
    
    // 如果图片加载失败，不显示任何内容
    if (imageError) {
      return null;
    }
    
    return (
      <img
        {...props}
        src={src}
        alt={alt}
        onError={() => setImageError(true)}
        style={{ display: imageError ? 'none' : 'block' }}
      />
    );
  };

  return (
    <div className={`flex gap-4 p-6 ${isUser ? 'bg-transparent' : 'bg-[#1E1F20]/50'} rounded-none transition-colors`}>
      <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${isUser ? 'bg-secondary text-white' : 'bg-gradient-to-tr from-blue-500 to-cyan-400 text-white'}`}>
        {isUser ? <User size={18} /> : <Bot size={18} />}
      </div>
      
      <div className="flex-1 overflow-hidden space-y-4">
        {/* Main Text Content */}
        <div className="prose prose-invert prose-sm max-w-none text-text">
          <ReactMarkdown
            components={{
              img: ImageComponent,
            }}
          >
            {message.content}
          </ReactMarkdown>
        </div>

        {/* SQL Block (Always shown if available) */}
        {message.sqlQuery && (
          <div className={`bg-[#0d1117] rounded-xl border ${isError ? 'border-red-500/50' : 'border-secondary'} overflow-hidden mt-3 relative group`}>
            <div className="flex items-center justify-between px-4 py-2 bg-[#161b22] border-b border-secondary">
               <div className="flex items-center gap-2 text-xs font-mono text-subtext">
                  <Terminal size={14} className="text-accent" />
                  <span>{t.generatedSql}</span>
               </div>
               <button 
                 onClick={handleCopy}
                 className="text-subtext hover:text-white transition-colors p-1"
                 title="Copy SQL"
               >
                 {copied ? <Check size={14} className="text-green-400" /> : <Copy size={14} />}
               </button>
            </div>
            <pre className="p-4 overflow-x-auto text-sm font-mono text-green-400">
              <code>{message.sqlQuery}</code>
            </pre>
            
            {/* 执行状态显示 */}
            {isExecuting && (
                <div className="absolute inset-0 bg-black/50 backdrop-blur-[1px] flex items-center justify-center">
                    <div className="flex items-center gap-2 text-accent font-medium text-sm bg-[#1E1F20] px-4 py-2 rounded-full border border-secondary shadow-xl">
                        <Loader2 size={16} className="animate-spin" />
                        {t.executing}
                    </div>
                </div>
            )}
          </div>
        )}
        
        {/* Error Message */}
        {isError && message.error && (
            <div className="flex items-start gap-3 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-300 text-sm">
                <AlertTriangle size={16} className="shrink-0 mt-0.5" />
                <div>
                    <div className="font-semibold mb-1">{t.executionError}</div>
                    <div>{message.error}</div>
                </div>
            </div>
        )}

        {/* 思考状态提示 - 只在内容为空且状态为thinking时显示（避免与初始思考内容重复） */}
        {message.status === 'thinking' && !message.content && (
            <div className="flex items-center gap-2 text-xs text-blue-400/80 bg-blue-500/5 px-3 py-2 rounded-lg border border-blue-500/10 mt-2">
                <Loader2 size={12} className="animate-spin" />
                {language === 'zh' ? '正在思考中...' : 'Thinking...'}
            </div>
        )}

        {/* Execution Results */}
        {message.executionResult && (
          <div className="border border-secondary rounded-xl p-1 bg-surface/30 animate-in fade-in slide-in-from-bottom-4 duration-500">
             <div className="flex items-center gap-2 px-4 py-2 text-xs font-medium text-accent uppercase tracking-wider">
               <Database size={14} /> {t.resultAnalysis}
             </div>
             <DataVisualizer result={message.executionResult} language={language} />
          </div>
        )}
      </div>
    </div>
  );
};

export default MessageBubble;