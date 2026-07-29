import { db } from '@/lib/db';

// Tool definitions for the AI agent
export interface ToolDefinition {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
}

export const TOOLS: ToolDefinition[] = [
  {
    name: 'web_search',
    description: 'Search the web for real-time information, news, articles, and data. Use this when you need current information beyond your training data.',
    parameters: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'The search query' },
      },
      required: ['query'],
    },
  },
  {
    name: 'code_execute',
    description: 'Execute Python or JavaScript code and get the result. Use this for calculations, data processing, file operations, or any code that needs to run.',
    parameters: {
      type: 'object',
      properties: {
        code: { type: 'string', description: 'The code to execute' },
        language: { type: 'string', description: 'Programming language: python or javascript', enum: ['python', 'javascript'] },
      },
      required: ['code', 'language'],
    },
  },
  {
    name: 'file_operations',
    description: 'Read, write, list, or delete files on the server. Use this for file management tasks.',
    parameters: {
      type: 'object',
      properties: {
        action: { type: 'string', description: 'File action: read, write, list, delete', enum: ['read', 'write', 'list', 'delete'] },
        path: { type: 'string', description: 'File path' },
        content: { type: 'string', description: 'Content to write (for write action)' },
      },
      required: ['action'],
    },
  },
  {
    name: 'generate_chart',
    description: 'Generate charts and visualizations (bar, line, pie, scatter). Returns a chart image or SVG.',
    parameters: {
      type: 'object',
      properties: {
        chartType: { type: 'string', description: 'Type: bar, line, pie, scatter, area', enum: ['bar', 'line', 'pie', 'scatter', 'area'] },
        data: { type: 'string', description: 'JSON string of chart data with labels and values' },
        title: { type: 'string', description: 'Chart title' },
      },
      required: ['chartType', 'data'],
    },
  },
  {
    name: 'text_analysis',
    description: 'Analyze text: summarize, extract keywords, sentiment analysis, count words, find patterns.',
    parameters: {
      type: 'object',
      properties: {
        action: { type: 'string', description: 'Analysis type: summarize, keywords, sentiment, wordcount', enum: ['summarize', 'keywords', 'sentiment', 'wordcount'] },
        text: { type: 'string', description: 'The text to analyze' },
      },
      required: ['action', 'text'],
    },
  },
];

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
}

export interface ToolResult {
  toolCallId: string;
  toolName: string;
  output: string;
  isError?: boolean;
}

// Execute a tool call
export async function executeTool(toolCall: ToolCall): Promise<ToolResult> {
  const start = Date.now();
  try {
    let output = '';

    switch (toolCall.name) {
      case 'web_search': {
        const { query } = toolCall.arguments as { query: string };
        const result = await webSearch(query);
        output = JSON.stringify(result, null, 2);
        break;
      }
      case 'code_execute': {
        const { code, language } = toolCall.arguments as { code: string; language: string };
        const result = await codeExecute(code, language);
        output = result;
        break;
      }
      case 'file_operations': {
        const { action, path, content } = toolCall.arguments as { action: string; path?: string; content?: string };
        const result = await fileOperations(action, path, content);
        output = JSON.stringify(result, null, 2);
        break;
      }
      case 'generate_chart': {
        const { chartType, data, title } = toolCall.arguments as { chartType: string; data: string; title?: string };
        const result = await generateChart(chartType, data, title);
        output = JSON.stringify(result, null, 2);
        break;
      }
      case 'text_analysis': {
        const { action, text } = toolCall.arguments as { action: string; text: string };
        const result = textAnalysis(action, text);
        output = JSON.stringify(result, null, 2);
        break;
      }
      default:
        output = `Unknown tool: ${toolCall.name}`;
    }

    const duration = Date.now() - start;
    await db.toolLog.create({
      data: { toolName: toolCall.name, input: JSON.stringify(toolCall.arguments), output, duration, status: 'success' },
    });

    return { toolCallId: toolCall.id, toolName: toolCall.name, output };
  } catch (error) {
    const errMsg = error instanceof Error ? error.message : String(error);
    await db.toolLog.create({
      data: { toolName: toolCall.name, input: JSON.stringify(toolCall.arguments), output: errMsg, status: 'error' },
    });
    return { toolCallId: toolCall.id, toolName: toolCall.name, output: errMsg, isError: true };
  }
}

// === TOOL IMPLEMENTATIONS ===

async function webSearch(query: string) {
  try {
    const { search } = await import('z-ai-web-dev-sdk');
    const results = await search({ query, limit: 5 });
    return {
      results: results.map((r: { title: string; url: string; snippet?: string }) => ({
        title: r.title,
        url: r.url,
        snippet: r.snippet || '',
      })),
    };
  } catch {
    return { results: [{ title: 'Search Demo', url: '#', snippet: `Search results for: "${query}". Web search requires z-ai-web-dev-sdk configuration.` }] };
  }
}

async function codeExecute(code: string, language: string) {
  const { exec } = await import('child_process');
  const { promisify } = await import('util');
  const execAsync = promisify(exec);

  const ext = language === 'python' ? 'py' : 'js';
  const cmd = language === 'python' ? 'python3' : 'node';
  const tmpFile = `/tmp/tool_exec_${Date.now()}.${ext}`;

  try {
    const fs = await import('fs/promises');
    await fs.writeFile(tmpFile, code, 'utf-8');

    const { stdout, stderr } = await execAsync(`${cmd} ${tmpFile}`, {
      timeout: 15000,
      maxBuffer: 1024 * 1024,
    });

    await fs.unlink(tmpFile).catch(() => {});

    return stdout || stderr || 'Code executed successfully (no output)';
  } catch (error: unknown) {
    const fs = await import('fs/promises');
    await fs.unlink(tmpFile).catch(() => {});
    const err = error as { stderr?: string; message?: string };
    return `Error: ${err.stderr || err.message || 'Execution failed'}`;
  }
}

async function fileOperations(action: string, path?: string, content?: string) {
  const fs = await import('fs/promises');
  const basePath = '/home/z/my-project/download';

  switch (action) {
    case 'list': {
      const targetPath = path || basePath;
      try {
        const entries = await fs.readdir(targetPath, { withFileTypes: true });
        return {
          path: targetPath,
          entries: entries.slice(0, 100).map(e => ({
            name: e.name,
            type: e.isDirectory() ? 'directory' : 'file',
          })),
        };
      } catch {
        return { error: 'Path not found', path: targetPath };
      }
    }
    case 'read': {
      if (!path) return { error: 'Path required' };
      try {
        const data = await fs.readFile(path, 'utf-8');
        return { path, content: data.slice(0, 10000), truncated: data.length > 10000 };
      } catch {
        return { error: 'File not found', path };
      }
    }
    case 'write': {
      if (!path || !content) return { error: 'Path and content required' };
      try {
        await fs.writeFile(path, content, 'utf-8');
        return { success: true, path, bytes: content.length };
      } catch {
        return { error: 'Write failed', path };
      }
    }
    case 'delete': {
      if (!path) return { error: 'Path required' };
      try {
        await fs.unlink(path);
        return { success: true, path };
      } catch {
        return { error: 'Delete failed', path };
      }
    }
    default:
      return { error: 'Unknown action' };
  }
}

async function generateChart(chartType: string, dataStr: string, title?: string) {
  try {
    const data = JSON.parse(dataStr);
    // Generate SVG directly (no jsdom dependency needed)
    const labels: string[] = data.labels || data.map((_: unknown, i: number) => `Item ${i + 1}`);
    const values: number[] = data.values || data.data || Object.values(data).map(Number);

    let svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 400">`;
    svg += `<rect width="600" height="400" fill="#1a1a2e" rx="12"/>`;
    svg += `<text x="300" y="30" fill="#e2e8f0" text-anchor="middle" font-size="16" font-weight="bold" font-family="sans-serif">${title || 'Chart'}</text>`;

    if (chartType === 'bar' || chartType === 'line' || chartType === 'area') {
      const max = Math.max(...values.map(Number));
      const barWidth = Math.min(60, 500 / values.length - 10);
      const startX = 50;

      values.forEach((v: number, i: number) => {
        const height = (Number(v) / Math.max(max, 1)) * 300;
        const x = startX + i * (barWidth + 10);
        const y = 360 - height;

        if (chartType === 'area' || chartType === 'line') {
          svg += `<line x1="${x + barWidth / 2}" y1="${y}" x2="${x + barWidth / 2}" y2="360" stroke="#8b5cf6" stroke-width="2"/>`;
          svg += `<circle cx="${x + barWidth / 2}" cy="${y}" r="4" fill="#a78bfa"/>`;
        } else {
          svg += `<rect x="${x}" y="${y}" width="${barWidth}" height="${height}" fill="#8b5cf6" rx="4"/>`;
        }

        svg += `<text x="${x + barWidth / 2}" y="375" fill="#94a3b8" text-anchor="middle" font-size="10" font-family="sans-serif">${labels[i] || ''}</text>`;
        svg += `<text x="${x + barWidth / 2}" y="${y - 5}" fill="#e2e8f0" text-anchor="middle" font-size="11" font-family="sans-serif">${v}</text>`;
      });

      if (chartType === 'area') {
        const startXArea = 50 + barWidth / 2;
        const endXArea = 50 + (values.length - 1) * (barWidth + 10) + barWidth / 2;
        svg += `<rect x="${startXArea}" y="60" width="${endXArea - startXArea}" height="300" fill="#8b5cf6" opacity="0.1" rx="4"/>`;
      }
    } else if (chartType === 'pie') {
      const total = values.reduce((a: number, b: number) => a + Number(b), 0);
      const colors = ['#8b5cf6', '#06b6d4', '#f59e0b', '#10b981', '#ef4444', '#ec4899', '#6366f1'];
      let currentAngle = 0;

      values.forEach((v: number, i: number) => {
        const angle = (Number(v) / Math.max(total, 1)) * 360;
        const startAngle = currentAngle;
        const endAngle = currentAngle + angle;
        const midAngle = (startAngle + endAngle) / 2;

        const x1 = 300 + 150 * Math.cos((startAngle * Math.PI) / 180);
        const y1 = 210 + 150 * Math.sin((startAngle * Math.PI) / 180);
        const x2 = 300 + 150 * Math.cos((endAngle * Math.PI) / 180);
        const y2 = 210 + 150 * Math.sin((endAngle * Math.PI) / 180);

        svg += `<path d="M300,210 L${x1},${y1} A150,150 0 ${angle > 180 ? 1 : 0},1 ${x2},${y2} Z" fill="${colors[i % colors.length]}"/>`;
        svg += `<text x="${300 + 180 * Math.cos((midAngle * Math.PI) / 180)}" y="${210 + 180 * Math.sin((midAngle * Math.PI) / 180)}" fill="#e2e8f0" text-anchor="middle" font-size="11" font-family="sans-serif">${labels[i] || ''}</text>`;

        currentAngle = endAngle;
      });
    } else if (chartType === 'scatter') {
      const max = Math.max(...values.map(Number));
      values.forEach((v: number, i: number) => {
        const x = 80 + (i / Math.max(values.length, 1)) * 480;
        const y = 360 - (Number(v) / Math.max(max, 1)) * 300;
        svg += `<circle cx="${x}" cy="${y}" r="6" fill="#8b5cf6" opacity="0.8"/>`;
      });
    }

    svg += '</svg>';
    return { svg, chartType, title: title || 'Chart' };
  } catch {
    return { error: 'Failed to generate chart. Ensure data is valid JSON.' };
  }
}

function textAnalysis(action: string, text: string) {
  switch (action) {
    case 'wordcount': {
      const words = text.split(/\s+/).filter(Boolean);
      const chars = text.length;
      const sentences = text.split(/[.!?]+/).filter(Boolean);
      const paragraphs = text.split(/\n\n+/).filter(Boolean);
      return {
        words: words.length,
        characters: chars,
        sentences: sentences.length,
        paragraphs: paragraphs.length,
        avgWordsPerSentence: words.length / Math.max(sentences.length, 1),
      };
    }
    case 'keywords': {
      const stopWords = new Set(['the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'shall', 'can', 'need', 'dare', 'ought', 'used', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through', 'during', 'before', 'after', 'above', 'below', 'between', 'out', 'off', 'over', 'under', 'again', 'further', 'then', 'once', 'here', 'there', 'when', 'where', 'why', 'how', 'all', 'each', 'every', 'both', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 'and', 'but', 'or', 'if', 'while', 'about', 'it', 'its', 'this', 'that', 'these', 'those', 'i', 'me', 'my', 'we', 'our', 'you', 'your', 'he', 'him', 'his', 'she', 'her', 'they', 'them', 'their', 'what', 'which', 'who', 'whom']);
      const words = text.toLowerCase().split(/\s+/).filter(w => w.length > 2 && !stopWords.has(w));
      const freq: Record<string, number> = {};
      words.forEach(w => { freq[w] = (freq[w] || 0) + 1; });
      return Object.entries(freq).sort((a, b) => b[1] - a[1]).slice(0, 20).map(([word, count]) => ({ word, count }));
    }
    case 'sentiment': {
      const positive = ['good', 'great', 'excellent', 'amazing', 'wonderful', 'fantastic', 'awesome', 'love', 'happy', 'joy', 'best', 'perfect', 'brilliant', 'outstanding', 'superb', 'beautiful', 'nice', 'pleasant', 'positive', 'success', 'win', 'won', 'achieve', 'improve', 'growth'];
      const negative = ['bad', 'terrible', 'horrible', 'awful', 'worst', 'hate', 'ugly', 'poor', 'negative', 'fail', 'failure', 'lose', 'lost', 'problem', 'issue', 'error', 'wrong', 'broken', 'damage', 'destroy', 'waste', 'pain', 'sad', 'angry', 'disappoint'];

      const words = text.toLowerCase().split(/\s+/);
      let posCount = 0;
      let negCount = 0;
      words.forEach(w => {
        if (positive.some(p => w.includes(p))) posCount++;
        if (negative.some(n => w.includes(n))) negCount++;
      });

      const total = posCount + negCount;
      const score = total === 0 ? 0.5 : posCount / total;
      return {
        score: Math.round(score * 100) / 100,
        label: score > 0.6 ? 'Positive' : score < 0.4 ? 'Negative' : 'Neutral',
        positive: posCount,
        negative: negCount,
        total: total,
      };
    }
    case 'summarize': {
      const sentences = text.split(/[.!?]+/).filter(s => s.trim().length > 20);
      if (sentences.length <= 3) return { summary: text.slice(0, 500) };

      // Simple extractive summary: pick sentences with most keyword overlap
      const allWords = text.toLowerCase().split(/\s+/);
      const freq: Record<string, number> = {};
      allWords.forEach(w => { if (w.length > 3) freq[w] = (freq[w] || 0) + 1; });

      const scored = sentences.map(s => {
        const sWords = s.toLowerCase().split(/\s+/);
        let score = 0;
        sWords.forEach(w => { score += freq[w] || 0; });
        return { sentence: s.trim(), score };
      });

      scored.sort((a, b) => b.score - a.score);
      const topSentences = scored.slice(0, Math.min(3, Math.ceil(sentences.length / 3)));

      return {
        summary: topSentences.map(s => s.sentence).join('. ') + '.',
        originalLength: text.length,
        summaryLength: topSentences.reduce((a, s) => a + s.sentence.length, 0),
        sentencesSelected: topSentences.length,
      };
    }
    default:
      return { error: 'Unknown analysis action' };
  }
}
