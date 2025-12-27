
import { GoogleGenAI } from "@google/genai";
import { AppSettings, Message, SqlResult, AVAILABLE_MODELS } from "../types";
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
  // If user provided a custom key in settings, use it.
  if (settings?.customApiKey) return settings.customApiKey;
  // Otherwise try environment variable (for simulation mode primarily)
  return process.env.API_KEY;
};

// Helper: Generate a short title for the session based on the first prompt
export const generateSessionTitle = async (firstUserMessage: string, language: 'en' | 'zh' = 'en'): Promise<string> => {
  const apiKey = getApiKey();
  // Always use Gemini for lightweight title generation if API key exists
  if (!apiKey) return language === 'zh' ? "分析会话" : "Analysis Session";
  
  const ai = new GoogleGenAI({ apiKey: apiKey });
  
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

export const generateSqlAndAnalysis = async (
  query: string,
  history: Message[],
  settings: AppSettings
): Promise<{ text: string; sql?: string; result?: SqlResult }> => {

  // ---------------------------------------------------------
  // MODE A: REAL BACKEND EXECUTION
  // If a file ID is present in settings, we use the real Python backend.
  // ---------------------------------------------------------
  if (settings.dbConfig.fileId) {
      try {
          // Use custom API key if available, otherwise backend handles it
          const apiKey = settings.customApiKey || undefined;
          
          const response = await api.analyzeData(query, settings.dbConfig.fileId, apiKey);
          
          return {
              text: response.answer,
              sql: response.sql,
              result: {
                  columns: response.columns,
                  data: response.data,
                  // Heuristic for chart type
                  chartTypeSuggestion: response.data.length > 0 && Object.keys(response.data[0]).length === 2 ? 'bar' : 'table',
                  summary: "Executed on real database."
              }
          };
      } catch (error: any) {
          return {
              text: settings.language === 'zh' 
                ? `后端执行错误: ${error.message}` 
                : `Backend execution error: ${error.message}`,
          };
      }
  }

  // ---------------------------------------------------------
  // MODE B: FRONTEND SIMULATION (Gemini Mock)
  // ---------------------------------------------------------
  
  const apiKey = getApiKey(settings);
  if (!apiKey) {
    return {
      text: settings.language === 'zh'
        ? "❌ 未检测到 API Key。请在设置中输入您的 API Key，或配置环境变量。"
        : "❌ API Key missing. Please enter your API Key in Settings or env variables."
    };
  }

  // Logic for Model Selection (in simulation, we just use Gemini to mock other models)
  let modelName = 'gemini-2.5-flash';
  let isGoogleModel = true;

  if (settings.model.includes('gemini')) {
    modelName = settings.model;
  } else {
    isGoogleModel = false;
    // Fallback to Gemini for the demo
    modelName = 'gemini-2.5-flash';
  }

  const ai = new GoogleGenAI({ apiKey: apiKey });

  const systemInstruction = `
    You are an expert Data Analyst and SQL Engineer.
    Your goal is to answer user questions by converting natural language to SQL queries.
    
    Context:
    You are working with a PostgreSQL database.
    
    Database Schema:
    ${SAMPLE_SCHEMA}

    Instructions:
    1. Analyze the user's request.
    2. Generate a valid PostgreSQL query to answer the question.
    3. If the user asks for a visualization, suggest a chart type (bar, line, pie).
    4. Provide a brief explanation of what the query does. ${settings.language === 'zh' ? 'The explanation MUST be in Chinese.' : ''}
    5. Return the response in a structured JSON format.

    IMPORTANT: Return ONLY raw JSON without markdown formatting.
    Structure:
    {
      "explanation": "string",
      "sql": "string",
      "chartType": "bar" | "line" | "pie" | "table",
      "dataSimulation": [ ...array of objects representing the result dataset... ]
    }
    
    For "dataSimulation", generate realistic mock data (5-10 rows) that would result from executing the SQL. 
    This is for a frontend demo where no real DB is connected.
    
    ${!isGoogleModel ? `NOTE: You are simulating the behavior of the model: ${settings.model}.` : ''}
  `;

  try {
    const response = await ai.models.generateContent({
      model: modelName,
      contents: [
        ...history.map(msg => ({
          role: msg.role === 'user' ? 'user' : 'model',
          parts: [{ text: msg.content }]
        })),
        { role: 'user', parts: [{ text: query }] }
      ],
      config: {
        systemInstruction: systemInstruction,
        responseMimeType: "application/json"
      }
    });

    const jsonText = response.text || "{}";
    const parsed = JSON.parse(jsonText);

    return {
      text: parsed.explanation,
      sql: parsed.sql,
      result: {
        columns: parsed.dataSimulation && parsed.dataSimulation.length > 0 ? Object.keys(parsed.dataSimulation[0]) : [],
        data: parsed.dataSimulation || [],
        chartTypeSuggestion: parsed.chartType || 'table',
        summary: "Query executed successfully on simulated database."
      }
    };

  } catch (error: any) {
    console.error("Gemini API Error:", error);
    let errorMsg = error.message || "";
    if (errorMsg.includes("401")) {
        errorMsg = "API Key 无效 (401 Unauthorized)。请检查您的 Key 是否正确。";
    }
    return {
      text: settings.language === 'zh' 
        ? `遇到错误: ${errorMsg}` 
        : `Error encountered: ${errorMsg}`,
    };
  }
};
