import React from 'react';
import { Copy, Check } from 'lucide-react';

interface SqlPreviewProps {
  sql: string;
}

const SqlPreview: React.FC<SqlPreviewProps> = ({ sql }) => {
  const [copied, setCopied] = React.useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(sql);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="rounded-lg overflow-hidden border border-[#444746] bg-[#1e1f20] mt-4">
      <div className="flex justify-between items-center px-4 py-2 bg-[#2d2e2f] border-b border-[#444746]">
        <span className="text-xs font-mono text-[#a8c7fa]">POSTGRESQL</span>
        <button 
          onClick={handleCopy}
          className="text-gray-400 hover:text-white transition-colors"
          title="Copy SQL"
        >
          {copied ? <Check size={14} className="text-green-400" /> : <Copy size={14} />}
        </button>
      </div>
      <div className="p-4 overflow-x-auto">
        <pre className="text-sm font-mono text-[#e3e3e3] whitespace-pre-wrap">
          {sql}
        </pre>
      </div>
    </div>
  );
};

export default SqlPreview;