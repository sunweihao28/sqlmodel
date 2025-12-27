import React from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  LineChart, Line, PieChart, Pie, Cell
} from 'recharts';
import { ChartType, SqlResult } from '../types';

interface DataVisualizerProps {
  result: SqlResult;
}

const COLORS = ['#669df6', '#a8c7fa', '#c58af9', '#f28b82', '#fdd663', '#81c995'];

const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-[#1e1f20] border border-[#444746] p-2 rounded shadow-lg text-xs">
        <p className="font-bold text-[#e3e3e3] mb-1">{label}</p>
        {payload.map((entry: any, index: number) => (
          <p key={index} style={{ color: entry.color }}>
            {entry.name}: {entry.value}
          </p>
        ))}
      </div>
    );
  }
  return null;
};

const DataVisualizer: React.FC<DataVisualizerProps> = ({ result }) => {
  const { data, chartType, xAxisKey, dataKeys } = result;

  if (!data || data.length === 0) {
    return <div className="text-gray-500 text-sm p-4">暂无数据可显示</div>;
  }

  const renderChart = () => {
    switch (chartType) {
      case ChartType.BAR:
        return (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#444746" opacity={0.5} />
              <XAxis dataKey={xAxisKey} stroke="#9ca3af" fontSize={12} tickLine={false} />
              <YAxis stroke="#9ca3af" fontSize={12} tickLine={false} />
              <Tooltip content={<CustomTooltip />} cursor={{fill: '#2d2e2f'}} />
              <Legend />
              {dataKeys?.map((key, index) => (
                <Bar 
                  key={key} 
                  dataKey={key} 
                  fill={COLORS[index % COLORS.length]} 
                  radius={[4, 4, 0, 0]} 
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        );

      case ChartType.LINE:
        return (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#444746" opacity={0.5} />
              <XAxis dataKey={xAxisKey} stroke="#9ca3af" fontSize={12} tickLine={false} />
              <YAxis stroke="#9ca3af" fontSize={12} tickLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <Legend />
              {dataKeys?.map((key, index) => (
                <Line 
                  key={key} 
                  type="monotone" 
                  dataKey={key} 
                  stroke={COLORS[index % COLORS.length]} 
                  strokeWidth={3}
                  dot={{ r: 4, fill: '#131314', strokeWidth: 2 }}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        );

      case ChartType.PIE:
         const pieDataKey = dataKeys ? dataKeys[0] : Object.keys(data[0])[1];
         const pieNameKey = xAxisKey || Object.keys(data[0])[0];
         
         return (
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                cx="50%"
                cy="50%"
                labelLine={false}
                outerRadius={80}
                fill="#8884d8"
                dataKey={pieDataKey}
                nameKey={pieNameKey}
                label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
              >
                {data.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        );
        
      default: // Table view
        return null; // Handled outside in wrapper
    }
  };

  return (
    <div className="w-full mt-4 flex flex-col gap-6">
      {chartType !== ChartType.TABLE && (
        <div className="h-64 w-full bg-[#1e1f20] rounded-xl border border-[#444746] p-4">
           {renderChart()}
        </div>
      )}

      {/* Always show data table for reference */}
      <div className="overflow-x-auto bg-[#1e1f20] rounded-xl border border-[#444746]">
        <table className="w-full text-sm text-left text-gray-400">
          <thead className="text-xs uppercase bg-[#2d2e2f] text-gray-300">
            <tr>
              {Object.keys(data[0] || {}).map((header) => (
                <th key={header} className="px-6 py-3 font-medium tracking-wider">{header}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((row, i) => (
              <tr key={i} className="border-b border-[#444746] hover:bg-[#2d2e2f]">
                {Object.values(row).map((val: any, j) => (
                  <td key={j} className="px-6 py-4 whitespace-nowrap text-[#e3e3e3]">
                    {val?.toString()}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default DataVisualizer;