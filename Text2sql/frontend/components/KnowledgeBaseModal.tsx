
import React, { useState, useEffect } from 'react';
import { X, Upload, Trash2, FileText, Loader2, BookOpen, AlertTriangle } from 'lucide-react';
import { api } from '../services/api';
import { RagDocument, AppSettings } from '../types';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  language: 'en' | 'zh';
  settings: AppSettings;
}

const KnowledgeBaseModal: React.FC<Props> = ({ isOpen, onClose, language, settings }) => {
  const [documents, setDocuments] = useState<RagDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');

  const isZh = language === 'zh';

  useEffect(() => {
    if (isOpen) {
      loadDocuments();
    }
  }, [isOpen]);

  const loadDocuments = async () => {
    setLoading(true);
    try {
      const docs = await api.getRagDocuments();
      setDocuments(docs);
      setError('');
    } catch (err: any) {
      console.error("Failed to load docs", err);
      setError(isZh ? "加载文档失败，请检查后端。" : "Failed to load documents.");
    } finally {
      setLoading(false);
    }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!settings.customApiKey) {
      setError(isZh ? "上传前请先在设置中配置 API Key (OpenAI)，因为需要进行 Embedding。" : "Please configure API Key (OpenAI) in settings first for Embedding.");
      return;
    }

    setUploading(true);
    setError('');
    try {
      // [修改] 传递 settings 中的 Key 和 URL
      await api.uploadRagDocument(
        file, 
        settings.customApiKey, 
        settings.customBaseUrl
      );
      await loadDocuments();
    } catch (err: any) {
      console.error("Upload failed", err);
      setError(isZh ? `上传失败: ${err.message}` : `Upload failed: ${err.message}`);
    } finally {
      setUploading(false);
      e.target.value = ''; // Reset input
    }
  };

  const handleDelete = async (docId: string) => {
    if (!window.confirm(isZh ? "确定删除此文档吗？" : "Delete this document?")) return;
    
    try {
      await api.deleteRagDocument(docId);
      setDocuments(prev => prev.filter(d => d.id !== docId));
    } catch (err: any) {
      setError(isZh ? "删除失败" : "Delete failed");
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-surface border border-secondary rounded-2xl w-full max-w-2xl shadow-2xl flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-secondary">
          <h2 className="text-xl font-semibold text-text flex items-center gap-2">
            <BookOpen size={20} className="text-accent" />
            {isZh ? "知识库管理 (RAG)" : "Knowledge Base (RAG)"}
          </h2>
          <button onClick={onClose} className="text-subtext hover:text-white transition-colors">
            <X size={24} />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto flex-1">
          
          <div className="mb-6 p-4 bg-blue-900/20 border border-blue-800/50 rounded-lg text-sm text-subtext">
            <p className="mb-2 font-semibold text-blue-200">
               {isZh ? "关于知识库" : "About Knowledge Base"}
            </p>
            <p>
              {isZh 
                ? "上传业务文档（PDF, Word, Markdown, Excel, JSON）以增强 AI 的准确性。上传后，AI 在回答问题时会自动检索相关信息。" 
                : "Upload documents (PDF, Word, Markdown, Excel, JSON) to enhance AI accuracy. The AI will retrieve relevant info when answering."}
            </p>
            {!settings.customApiKey && (
               <div className="mt-2 flex items-center gap-2 text-yellow-400">
                  <AlertTriangle size={14} />
                  <span>{isZh ? "注意：需配置 API Key 才能建立索引" : "Note: API Key required for indexing"}</span>
               </div>
            )}
          </div>

          {/* Upload Area */}
          <div className="mb-6">
            <label className={`flex flex-col items-center justify-center w-full h-32 border-2 border-dashed rounded-xl cursor-pointer transition-colors ${uploading ? 'border-accent bg-accent/10 opacity-50 pointer-events-none' : 'border-secondary hover:border-accent hover:bg-[#2a2b2d]'}`}>
                <div className="flex flex-col items-center justify-center pt-5 pb-6">
                    {uploading ? (
                        <Loader2 className="w-8 h-8 text-accent animate-spin mb-2" />
                    ) : (
                        <Upload className="w-8 h-8 text-subtext mb-2" />
                    )}
                    <p className="text-sm text-subtext">
                        {uploading 
                          ? (isZh ? "正在建立索引 (Embedding)..." : "Indexing (Embedding)...") 
                          : (isZh ? "点击上传文档 (.pdf, .docx, .md, .xlsx, .json)" : "Click to upload (.pdf, .docx, .md, .xlsx, .json)")}
                    </p>
                </div>
                <input type="file" className="hidden" accept=".pdf,.docx,.md,.txt,.json,.xlsx,.xls" onChange={handleUpload} disabled={uploading} />
            </label>
            {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
          </div>

          {/* Document List */}
          <h3 className="text-sm font-medium text-text mb-3">{isZh ? "已索引文档" : "Indexed Documents"}</h3>
          
          {loading ? (
             <div className="flex justify-center py-8"><Loader2 className="animate-spin text-subtext" /></div>
          ) : documents.length === 0 ? (
             <div className="text-center py-8 text-subtext text-sm italic border border-secondary border-dashed rounded-lg">
                {isZh ? "暂无文档" : "No documents yet"}
             </div>
          ) : (
            <div className="space-y-2">
              {documents.map(doc => (
                <div key={doc.id} className="flex items-center justify-between p-3 bg-[#2a2b2d] rounded-lg border border-transparent hover:border-secondary transition-colors group">
                   <div className="flex items-center gap-3 overflow-hidden">
                      <div className="w-8 h-8 rounded bg-blue-500/20 flex items-center justify-center text-blue-400 shrink-0">
                         <FileText size={16} />
                      </div>
                      <span className="text-sm text-text truncate">{doc.name}</span>
                   </div>
                   <button 
                     onClick={() => handleDelete(doc.id)}
                     className="p-2 text-subtext hover:text-red-400 hover:bg-red-400/10 rounded transition-colors opacity-0 group-hover:opacity-100"
                     title="Delete"
                   >
                      <Trash2 size={16} />
                   </button>
                </div>
              ))}
            </div>
          )}

        </div>
      </div>
    </div>
  );
};

export default KnowledgeBaseModal;