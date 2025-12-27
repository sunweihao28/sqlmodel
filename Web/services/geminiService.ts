import { GoogleGenAI } from "@google/genai";
import { TableSchema, SqlResult, ChartType } from "../types";

const SYSTEM_INSTRUCTION = `
You are an expert SQL Data Analyst and Database Engineer. 
Your goal is to accept a natural language query and a database schema, and produce:
1. A syntactically correct PostgreSQL query.
2. A clear, brief explanation of the logic.
3. SIMULATED data that would result from running this query (since we don't have a live DB connection).
4. A recommendation for how to visualize this data (Bar, Line, Pie, or just Table).

Rules:
- Strictly adhere to the provided schema.
- The simulated data should be realistic and relevant to the query context.
- Return the response in JSON format.
`;

export const generateSqlAndData = async (
  apiKey: string,
  schema: TableSchema[],
  userQuery: string
): Promise<SqlResult> => {
  if (!apiKey) {
    throw new Error("API Key is missing.");
  }

  const ai = new GoogleGenAI({ apiKey });

  const schemaDescription = schema.map(t => 
    `Table: ${t.tableName}\nColumns: ${t.columns.join(", ")}\nDescription: ${t.description || "N/A"}`
  ).join("\n\n");

  const prompt = `
    Database Schema:
    ${schemaDescription}

    User Question: "${userQuery}"

    Generate a valid JSON response strictly following this structure:
    {
      "sql": "The SQL query string",
      "explanation": "Brief explanation of what the query does",
      "data": [
        { "col1": "val1", "col2": 100 },
        { "col1": "val2", "col2": 200 }
      ],
      "chartType": "bar" | "line" | "pie" | "table",
      "xAxisKey": "The key in the data objects to use for X-axis (if applicable)",
      "dataKeys": ["Array of keys to use for data series (Y-axis)"]
    }
    
    Ensure 'data' is an array of objects representing the result rows of the SQL query. 
    The keys in the 'data' objects must match the columns selected in the SQL query.
  `;

  try {
    const response = await ai.models.generateContent({
      model: "gemini-2.5-flash",
      contents: prompt,
      config: {
        systemInstruction: SYSTEM_INSTRUCTION,
        responseMimeType: "application/json",
      }
    });

    if (response.text) {
      const result = JSON.parse(response.text) as SqlResult;
      // Normalize chart type just in case
      if (!Object.values(ChartType).includes(result.chartType)) {
        result.chartType = ChartType.TABLE;
      }
      return result;
    } else {
      throw new Error("No content generated.");
    }
  } catch (error: any) {
    console.error("Gemini API Error:", error);
    let errorMessage = "Failed to generate SQL and data.";
    
    // Pass through detailed error message if available
    if (error.message) {
        errorMessage = error.message;
    }
    
    throw new Error(errorMessage);
  }
};
