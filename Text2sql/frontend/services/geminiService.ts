
import { GoogleGenAI } from "@google/genai";
import { AppSettings, Message, SqlResult } from "../types";
import { api } from "./api";

// Mock Schema for the simulation
const SAMPLE_SCHEMA = `
Table: sales
Columns: id (INT), product_id (INT), customer_id (INT), sale_date (DATE), quantity (INT), total_amount (DECIMAL), region (VARCHAR)

Table: products
Columns: id (INT), name (VARCHAR), category (VARCHAR), unit_price (DECIMAL), cost (DECIMAL)

Table: customers
Columns: id (INT), name (VARCHAR), email (VARCHAR), signup_date (DATE), country (VARCHAR)
`;

// Helper: Get API Key safely
const getApiKey = (settings?: AppSettings): string | undefined => {
  if (settings?.customApiKey) return settings.customApiKey;
  return process.env.API_KEY;
};

// Helper: Generate a short title
export const generateSessionTitle = async (firstUserMessage: string, language: 'en' | 'zh' = 'en', apiKey?: string): Promise<string> => {
  const keyToUse = apiKey || process.env.API_KEY;
  if (!keyToUse) return language === 'zh' ? "分析会话" : "Analysis Session";
  
  const ai = new GoogleGenAI({ apiKey: keyToUse });
  const prompt = language === 'zh'
    ? `为以这个问题开始的数据分析会话生成一个非常简短、简洁的标题（最多 5 个字）："${firstUserMessage}"。不要使用引号。`
    : `Generate a very short, concise title (max 5 words) for a data analysis session starting with this question: "${firstUserMessage}". Do not use quotes.`;

  try {
    const response = await ai.models.generateContent({
      model: 'gemini-2.5-flash',
      contents: prompt,
    });
    return response.text?.trim() || (language === 'zh' ? "分析会话" : "Analysis Session");
  } catch (e) {
    return language === 'zh' ? "分析会话" : "Analysis Session";
  }
};

// --- NEW SPLIT ARCHITECTURE ---

/**
 * Step 1: Generate SQL Draft (but do not run it)
 */
export const createSqlDraft = async (
  query: string, 
  history: Message[], 
  settings: AppSettings
): Promise<{ text: string; sql?: string; error?: string }> => {

  // A. REAL BACKEND
  if (settings.dbConfig.fileId) {
      try {
          const sql = await api.generateSqlDraft(
              query, 
              history, 
              settings.dbConfig.fileId, 
              settings.customApiKey,
              settings.customBaseUrl,
              settings.model
          );
          return {
              text: settings.language === 'zh' ? "我已生成查询语句，请确认后运行。" : "I have generated the SQL. Please review and execute.",
              sql: sql
          };
      } catch (error: any) {
          return {
              text: settings.language === 'zh' ? `生成失败: ${error.message}` : `Generation failed: ${error.message}`,
              error: error.message
          };
      }
  }

  // B. SIMULATION (Google Gemini)
  const apiKey = getApiKey(settings);
  if (!apiKey) {
    return { text: "❌ API Key missing." };
  }

  const ai = new GoogleGenAI({ apiKey: apiKey });
  const systemInstruction = `
    You are an SQL Engineer.
    Schema: ${SAMPLE_SCHEMA}
    Task: Convert the user's question into a valid SQL query.
    Return JSON: { "sql": "SELECT ...", "explanation": "Brief explanation" }
  `;

  try {
    const response = await ai.models.generateContent({
      model: 'gemini-2.5-flash',
      contents: [
        ...history.map(msg => ({ role: msg.role === 'user' ? 'user' : 'model', parts: [{ text: msg.content }] })),
        { role: 'user', parts: [{ text: query }] }
      ],
      config: { systemInstruction, responseMimeType: "application/json" }
    });
    const parsed = JSON.parse(response.text || "{}");
    return {
        text: parsed.explanation || "SQL generated.",
        sql: parsed.sql
    };
  } catch (e: any) {
    return { text: "Error generating mock SQL", error: e.message };
  }
};

/**
 * Step 2: Execute the SQL (User confirmed)
 */
export const executeSqlDraft = async (
    sql: string,
    originalMessage: string,
    settings: AppSettings
): Promise<{ text: string; result?: SqlResult; error?: string }> => {

    // A. REAL BACKEND
    if (settings.dbConfig.fileId) {
        try {
            const response = await api.executeSql(
                sql, 
                originalMessage, 
                settings.dbConfig.fileId, 
                settings.customApiKey,
                settings.customBaseUrl,
                settings.model
            );
            return {
                text: response.answer,
                result: {
                    columns: response.columns,
                    data: response.data,
                    chartTypeSuggestion: response.data.length > 0 && Object.keys(response.data[0]).length === 2 ? 'bar' : 'table',
                    summary: "Real execution result."
                }
            };
        } catch (error: any) {
            return { text: "Execution Error", error: error.message };
        }
    }

    // B. SIMULATION (Generate Mock Data based on SQL)
    const apiKey = getApiKey(settings);
    const ai = new GoogleGenAI({ apiKey: apiKey! });
    
    try {
        const response = await ai.models.generateContent({
            model: 'gemini-2.5-flash',
            contents: `Generate realistic JSON data (array of objects) that would be returned by this SQL query: "${sql}". 
            Context: ${originalMessage}.
            Schema: ${SAMPLE_SCHEMA}.
            Return JSON format: { "data": [...], "explanation": "Analysis of the result" }`,
            config: { responseMimeType: "application/json" }
        });
        const parsed = JSON.parse(response.text || "{}");
        const data = parsed.data || [];
        return {
            text: parsed.explanation || "Analysis complete.",
            result: {
                columns: data.length > 0 ? Object.keys(data[0]) : [],
                data: data,
                chartTypeSuggestion: 'bar',
                summary: "Simulated result."
            }
        };
    } catch (e: any) {
        return { text: "Error executing mock SQL", error: e.message };
    }
};