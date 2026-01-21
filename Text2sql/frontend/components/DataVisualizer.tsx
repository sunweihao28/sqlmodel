
import React from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as ReTooltip, Legend, ResponsiveContainer,
  LineChart, Line, PieChart, Pie, Cell
} from 'recharts';
import { SqlResult, ChartType, DisplayType } from '../types';
import { translations } from '../i18n';

interface Props {
  result: SqlResult;
  language: 'en' | 'zh';
}

const COLORS = ['#669DF6', '#F4B400', '#DB4437', '#0F9D58', '#AB47BC', '#00ACC1'];

const DataVisualizer: React.FC<Props> = ({ result, language }) => {
  const { data, chartTypeSuggestion, columns, visualizationConfig } = result;
  const t = translations[language];

  if (!data || data.length === 0) return <div className="text-subtext italic p-4">{t.noData}</div>;

  // 决定显示类型：优先使用 visualizationConfig.displayType，否则使用 result.displayType，默认 'both'
  const displayType: DisplayType = visualizationConfig?.displayType 
    ? visualizationConfig.displayType 
    : (result.displayType || 'both');

  // 判断是否显示表格
  const showTable = displayType === 'table' || displayType === 'both';
  
  // 判断是否显示图表（当 chartTypeSuggestion 不是 'table' 时）
  const showChart = (displayType === 'chart' || displayType === 'both') && chartTypeSuggestion !== 'table';

  // Heuristic to find numeric and label keys
  const keys = Object.keys(data[0]);
  const labelKey = keys.find(k => typeof data[0][k] === 'string') || keys[0];
  const valueKeys = keys.filter(k => typeof data[0][k] === 'number');

  const renderChart = () => {
    switch (chartTypeSuggestion) {
      case 'bar':
        return (
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#444746" />
              <XAxis dataKey={labelKey} stroke="#C4C7C5" />
              <YAxis stroke="#C4C7C5" />
              <ReTooltip 
                contentStyle={{ backgroundColor: '#1E1F20', borderColor: '#444746', color: '#E3E3E3' }} 
              />
              <Legend />
              {valueKeys.map((key, index) => (
                <Bar key={key} dataKey={key} fill={COLORS[index % COLORS.length]} radius={[4, 4, 0, 0]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        );
      case 'line':
        return (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#444746" />
              <XAxis dataKey={labelKey} stroke="#C4C7C5" />
              <YAxis stroke="#C4C7C5" />
              <ReTooltip contentStyle={{ backgroundColor: '#1E1F20', borderColor: '#444746' }} />
              <Legend />
              {valueKeys.map((key, index) => (
                <Line type="monotone" key={key} dataKey={key} stroke={COLORS[index % COLORS.length]} strokeWidth={2} dot={{r: 4}} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        );
      case 'pie':
        return (
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={data}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                outerRadius={100}
                fill="#8884d8"
                dataKey={valueKeys[0]}
                nameKey={labelKey}
              >
                {data.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <ReTooltip contentStyle={{ backgroundColor: '#1E1F20', borderColor: '#444746' }} />
            </PieChart>
          </ResponsiveContainer>
        );
      default:
        return null;
    }
  };

  return (
    <div className="mt-4 flex flex-col gap-6">
      {/* Table View - 条件渲染 */}
      {showTable && (
        <div className="overflow-x-auto rounded-lg border border-secondary">
          <div className="flex items-center gap-2 px-4 py-2 text-xs font-medium text-accent uppercase tracking-wider bg-[#2a2b2d] border-b border-secondary">
            <span>{t.dataTable || 'Data Table'}</span>
          </div>
          <table className="w-full text-sm text-left text-subtext">
            <thead className="text-xs uppercase bg-[#2a2b2d] text-text">
              <tr>
                {columns.map(col => (
                  <th key={col} className="px-6 py-3">{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map((row, idx) => (
                <tr key={idx} className="bg-surface border-b border-secondary hover:bg-[#2a2b2d] transition-colors">
                  {columns.map(col => (
                    <td key={`${idx}-${col}`} className="px-6 py-4 font-medium text-text whitespace-nowrap">
                      {row[col]}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Chart View - 条件渲染 */}
      {showChart && (
        <div className="p-4 bg-[#2a2b2d] rounded-xl border border-secondary">
          <h4 className="text-sm font-medium text-subtext mb-4 uppercase tracking-wider">
            {visualizationConfig?.title || t.visualization}
          </h4>
          {renderChart()}
        </div>
      )}
    </div>
  );
};

export default DataVisualizer;
