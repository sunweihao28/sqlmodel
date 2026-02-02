
import React, { useState } from 'react';
import { X, Save, Database, Server, Key, Globe, Languages, FileCheck, Trash2, CheckCircle, Loader2 } from 'lucide-react';
import { AppSettings, DbConfig } from '../types';
import { translations } from '../i18n';
import { api } from '../services/api';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  settings: AppSettings;
  onSave: (settings: AppSettings) => void;
}

const SettingsModal: React.FC<Props> = ({ isOpen, onClose, settings, onSave }) => {
  const [localSettings, setLocalSettings] = React.useState<AppSettings>(settings);
  const [activeTab, setActiveTab] = React.useState<'general' | 'database'>('general');
  const [isConnecting, setIsConnecting] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<'none' | 'success' | 'error'>('none');
  const [connectionMsg, setConnectionMsg] = useState('');
  
  const t = translations[localSettings.language || 'en'];

  if (!isOpen) return null;

  const handleDbChange = (key: keyof DbConfig, value: string) => {
    setLocalSettings(prev => ({
      ...prev,
      dbConfig: { ...prev.dbConfig, [key]: value }
    }));
    setConnectionStatus('none'); // Reset status on edit
  };

  const clearUploadedFile = () => {
     setLocalSettings(prev => ({
      ...prev,
      dbConfig: { ...prev.dbConfig, uploadedPath: '', fileId: undefined }
    }));
  };

  const handleTestConnection = async () => {
    setIsConnecting(true);
    setConnectionMsg('');
    setConnectionStatus('none');
    try {
        const result = await api.saveDatabaseConnection(localSettings.dbConfig);
        if (result && result.id) {
            setConnectionStatus('success');
            setConnectionMsg(localSettings.language === 'zh' ? '连接成功并已保存！' : 'Connected and saved!');
            setLocalSettings(prev => ({
                ...prev,
                dbConfig: { ...prev.dbConfig, connectionId: result.id, fileId: undefined, uploadedPath: '' }
            }));
        }
    } catch (error: any) {
        setConnectionStatus('error');
        setConnectionMsg(error.message);
    } finally {
        setIsConnecting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-surface border border-secondary rounded-2xl w-full max-w-2xl shadow-2xl flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-secondary">
          <h2 className="text-xl font-semibold text-text flex items-center gap-2">
            {t.settingsTitle}
          </h2>
          <button onClick={onClose} className="text-subtext hover:text-white transition-colors">
            <X size={24} />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex px-6 border-b border-secondary">
          <button
            onClick={() => setActiveTab('general')}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'general' 
                ? 'border-accent text-accent' 
                : 'border-transparent text-subtext hover:text-text'
            }`}
          >
            {t.modelApi}
          </button>
          <button
            onClick={() => setActiveTab('database')}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'database' 
                ? 'border-accent text-accent' 
                : 'border-transparent text-subtext hover:text-text'
            }`}
          >
            {t.dbConnection}
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto flex-1">
          {activeTab === 'general' ? (
            <div className="space-y-6">
              
              {/* Language Selection */}
              <div>
                <label className="block text-sm font-medium text-subtext mb-2 flex items-center gap-2">
                  <Languages size={16} /> {t.language}
                </label>
                <select 
                    value={localSettings.language}
                    onChange={(e) => setLocalSettings(prev => ({ ...prev, language: e.target.value as 'en' | 'zh' }))}
                    className="w-full bg-[#2a2b2d] border border-secondary rounded-lg px-4 py-2 text-text text-sm focus:outline-none focus:border-accent"
                  >
                    <option value="en">English</option>
                    <option value="zh">中文 (Chinese)</option>
                </select>
              </div>

              <hr className="border-secondary" />
              
              {/* Simulation Mode Info */}
              <div className="flex items-center gap-3 p-4 bg-blue-900/20 border border-blue-800/50 rounded-lg">
                <input
                  type="checkbox"
                  id="simMode"
                  checked={localSettings.useSimulationMode}
                  disabled
                  className="w-4 h-4 rounded border-gray-300 text-accent focus:ring-accent opacity-50"
                />
                <label htmlFor="simMode" className="text-sm text-text cursor-default">
                  <span className="font-semibold block">{t.simMode} (Legacy)</span>
                  <span className="text-subtext">{t.simModeDesc}</span>
                </label>
              </div>

              <hr className="border-secondary" />

              {/* Custom Model Config */}
              <div>
                <h3 className="text-sm font-medium text-white mb-4 flex items-center gap-2">
                   <Globe size={16} /> {t.customModelConfig}
                </h3>
                <div className="space-y-4">
                    <div>
                        <label className="block text-xs font-medium text-subtext mb-1 flex items-center gap-1">
                          <Globe size={12} /> {t.apiBaseUrl}
                        </label>
                        <input
                        type="text"
                        value={localSettings.customBaseUrl || ''}
                        onChange={(e) => setLocalSettings(prev => ({ ...prev, customBaseUrl: e.target.value }))}
                        placeholder="e.g., https://api.deepseek.com/v1"
                        className="w-full bg-[#2a2b2d] border border-secondary rounded-lg px-4 py-2 text-text text-sm focus:outline-none focus:border-accent"
                        />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-subtext mb-1 flex items-center gap-1">
                          <Key size={12} /> {t.apiKey}
                        </label>
                        <input
                        type="password"
                        value={localSettings.customApiKey || ''}
                        onChange={(e) => setLocalSettings(prev => ({ ...prev, customApiKey: e.target.value }))}
                        placeholder="sk-..."
                        className="w-full bg-[#2a2b2d] border border-secondary rounded-lg px-4 py-2 text-text text-sm focus:outline-none focus:border-accent"
                        />
                    </div>
                </div>
              </div>

            </div>
          ) : (
            <div className="space-y-6">
              
              {/* Upload File Status (SQLite Mode) */}
              {localSettings.dbConfig.uploadedPath && (
                <div className="p-4 bg-green-500/10 border border-green-500/30 rounded-lg flex items-center justify-between mb-4">
                    <div className="flex items-center gap-3">
                        <FileCheck className="text-green-400" size={20} />
                        <div>
                            <p className="text-sm font-medium text-green-200">{t.usingFile}</p>
                            <p className="text-xs text-green-400/80 break-all">{localSettings.dbConfig.uploadedPath}</p>
                        </div>
                    </div>
                    <button 
                        onClick={clearUploadedFile}
                        className="p-2 text-subtext hover:text-red-400 hover:bg-red-400/10 rounded-lg transition-colors"
                        title={t.clearFile}
                    >
                        <Trash2 size={16} />
                    </button>
                </div>
              )}

              {/* Database Connection Config (MySQL/PG) */}
              <div className={`space-y-4 ${localSettings.dbConfig.uploadedPath ? 'opacity-50 pointer-events-none grayscale' : ''}`}>
                <div className="flex items-center justify-between">
                    <label className="text-sm font-medium text-white">Local/Remote DB Connection</label>
                    {localSettings.dbConfig.connectionId && (
                        <span className="text-xs bg-green-900 text-green-300 px-2 py-1 rounded-full flex items-center gap-1">
                            <CheckCircle size={10} /> Active
                        </span>
                    )}
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-subtext mb-2">{t.dbType}</label>
                    <select 
                      value={localSettings.dbConfig.type}
                      onChange={(e) => handleDbChange('type', e.target.value)}
                      className="w-full bg-[#2a2b2d] border border-secondary rounded-lg px-4 py-2 text-text"
                    >
                      <option value="postgres">PostgreSQL</option>
                      <option value="mysql">MySQL</option>
                      <option value="sqlite">SQLite (Use Upload)</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-subtext mb-2">{t.host}</label>
                    <input
                      type="text"
                      value={localSettings.dbConfig.host}
                      onChange={(e) => handleDbChange('host', e.target.value)}
                      placeholder="localhost"
                      className="w-full bg-[#2a2b2d] border border-secondary rounded-lg px-4 py-2 text-text"
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-subtext mb-2">{t.port}</label>
                    <input
                      type="text"
                      value={localSettings.dbConfig.port}
                      onChange={(e) => handleDbChange('port', e.target.value)}
                      placeholder={localSettings.dbConfig.type === 'mysql' ? "3306" : "5432"}
                      className="w-full bg-[#2a2b2d] border border-secondary rounded-lg px-4 py-2 text-text"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-subtext mb-2">{t.dbName}</label>
                    <input
                      type="text"
                      value={localSettings.dbConfig.database}
                      onChange={(e) => handleDbChange('database', e.target.value)}
                      placeholder="my_db"
                      className="w-full bg-[#2a2b2d] border border-secondary rounded-lg px-4 py-2 text-text"
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-subtext mb-2">{t.user}</label>
                    <input
                      type="text"
                      value={localSettings.dbConfig.user}
                      onChange={(e) => handleDbChange('user', e.target.value)}
                      placeholder="root / postgres"
                      className="w-full bg-[#2a2b2d] border border-secondary rounded-lg px-4 py-2 text-text"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-subtext mb-2">{t.password}</label>
                    <input
                      type="password"
                      value={localSettings.dbConfig.password}
                      onChange={(e) => handleDbChange('password', e.target.value)}
                      placeholder="••••••"
                      className="w-full bg-[#2a2b2d] border border-secondary rounded-lg px-4 py-2 text-text"
                    />
                  </div>
                </div>

                {localSettings.dbConfig.type !== 'sqlite' && (
                    <div className="pt-2">
                        <button 
                            onClick={handleTestConnection}
                            disabled={isConnecting}
                            className="w-full py-2 bg-blue-600/20 text-blue-300 border border-blue-600/50 rounded-lg hover:bg-blue-600/30 transition-colors flex items-center justify-center gap-2 font-medium text-sm"
                        >
                            {isConnecting ? <Loader2 className="animate-spin" size={16} /> : <Server size={16} />}
                            {localSettings.language === 'zh' ? '测试并保存连接' : 'Test & Save Connection'}
                        </button>
                        {connectionMsg && (
                            <p className={`text-xs mt-2 text-center ${connectionStatus === 'success' ? 'text-green-400' : 'text-red-400'}`}>
                                {connectionMsg}
                            </p>
                        )}
                    </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-secondary flex justify-end gap-3">
          <button onClick={onClose} className="px-4 py-2 text-subtext hover:text-text transition-colors">
            {t.cancel}
          </button>
          <button 
            onClick={() => onSave(localSettings)}
            className="px-6 py-2 bg-accent text-white font-medium rounded-full hover:bg-blue-600 transition-colors flex items-center gap-2"
          >
            <Save size={18} /> {t.save}
          </button>
        </div>
      </div>
    </div>
  );
};

export default SettingsModal;