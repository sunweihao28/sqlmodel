
import React from 'react';
import ReactMarkdown from 'react-markdown';
import { Bot, User, Database, Terminal, BarChart3 } from 'lucide-react';
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

  return (
    <div className={`flex gap-4 p-6 ${isUser ? 'bg-transparent' : 'bg-[#1E1F20]/50'} rounded-none transition-colors`}>
      <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${isUser ? 'bg-secondary text-white' : 'bg-gradient-to-tr from-blue-500 to-cyan-400 text-white'}`}>
        {isUser ? <User size={18} /> : <Bot size={18} />}
      </div>
      
      <div className="flex-1 overflow-hidden space-y-4">
        <div className="prose prose-invert prose-sm max-w-none text-text">
          <ReactMarkdown>{message.content}</ReactMarkdown>
        </div>

        {message.sqlQuery && (
          <div className="bg-[#0d1117] rounded-xl border border-secondary overflow-hidden mt-3">
            <div className="flex items-center gap-2 px-4 py-2 bg-[#161b22] border-b border-secondary text-xs font-mono text-subtext">
              <Terminal size={14} className="text-accent" />
              <span>{t.generatedSql}</span>
            </div>
            <pre className="p-4 overflow-x-auto text-sm font-mono text-green-400">
              <code>{message.sqlQuery}</code>
            </pre>
          </div>
        )}

        {message.executionResult && (
          <div className="border border-secondary rounded-xl p-1 bg-surface/30">
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
