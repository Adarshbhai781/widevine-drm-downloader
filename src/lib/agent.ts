import { db } from '@/lib/db';

// Tool definitions in OpenAI function-calling format
export interface ToolDefinition {
  type: 'function';
  function: {
    name: string;
    description: string;
    parameters: {
      type: 'object';
      properties: Record<string, unknown>;
      required?: string[];
    };
  };
}

export const TOOLS: ToolDefinition[] = [
  {
    type: 'function',
    function: {
      name: 'bash_execute',
      description: 'Execute a bash/shell command on the server. Returns stdout and stderr. Use this to run scripts, install packages, check system info, or perform any CLI operation. The working directory is /home/z/my-project. Timeout: 30 seconds.',
      parameters: {
        type: 'object',
        properties: {
          command: { type: 'string', description: 'The bash command to execute' },
        },
        required: ['command'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'code_execute',
      description: 'Execute Python or JavaScript code in a temporary file. Use this for calculations, data processing, algorithms, or any programmatic task. Python and Node.js are available.',
      parameters: {
        type: 'object',
        properties: {
          code: { type: 'string', description: 'The code to execute' },
          language: { type: 'string', description: 'python or javascript', enum: ['python', 'javascript'] },
        },
        required: ['code', 'language'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'file_operations',
      description: 'Read, write, list, or delete files. Use write to create new files or modify existing ones. All file operations are within /home/z/my-project/ directory tree.',
      parameters: {
        type: 'object',
        properties: {
          action: { type: 'string', description: 'read, write, list, delete', enum: ['read', 'write', 'list', 'delete'] },
          path: { type: 'string', description: 'File or directory path' },
          content: { type: 'string', description: 'Content to write (for write action)' },
        },
        required: ['action'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'web_search',
      description: 'Search the web for real-time information, news, articles, documentation. Use when you need current data beyond training cutoff.',
      parameters: {
        type: 'object',
        properties: {
          query: { type: 'string', description: 'Search query' },
        },
        required: ['query'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'generate_chart',
      description: 'Generate SVG charts: bar, line, pie, scatter, area. Provide data as JSON string with labels and values arrays.',
      parameters: {
        type: 'object',
        properties: {
          chartType: { type: 'string', description: 'bar, line, pie, scatter, area', enum: ['bar', 'line', 'pie', 'scatter', 'area'] },
          data: { type: 'string', description: 'JSON: {"labels":["A","B"],"values":[10,20]}' },
          title: { type: 'string', description: 'Chart title' },
        },
        required: ['chartType', 'data'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'text_analysis',
      description: 'Analyze text content: word count, keyword extraction, sentiment analysis, or summarization.',
      parameters: {
        type: 'object',
        properties: {
          action: { type: 'string', description: 'wordcount, keywords, sentiment, summarize', enum: ['wordcount', 'keywords', 'sentiment', 'summarize'] },
          text: { type: 'string', description: 'Text to analyze' },
        },
        required: ['action', 'text'],
      },
    },
  },
];

export interface ToolCall {
  id: string;
  type: 'function';
  function: {
    name: string;
    arguments: string;
  };
}

export interface ToolResult {
  toolCallId: string;
  toolName: string;
  output: string;
  isError?: boolean;
}

// Execute a tool call and return result
export async function executeTool(toolCall: ToolCall): Promise<ToolResult> {
  const start = Date.now();
  const toolName = toolCall.function.name;

  try {
    // Parse arguments (they come as JSON string in OpenAI format)
    let args: Record<string, unknown>;
    try {
      args = typeof toolCall.function.arguments === 'string'
        ? JSON.parse(toolCall.function.arguments)
        : toolCall.function.arguments;
    } catch {
      args = {};
    }

    let output = '';

    switch (toolName) {
      case 'bash_execute': {
        const { command } = args as { command: string };
        output = await bashExecute(command);
        break;
      }
      case 'code_execute': {
        const { code, language } = args as { code: string; language: string };
        output = await codeExecute(code, language);
        break;
      }
      case 'file_operations': {
        const { action, path, content } = args as { action: string; path?: string; content?: string };
        const result = await fileOperations(action, path, content);
        output = JSON.stringify(result, null, 2);
        break;
      }
      case 'web_search': {
        const { query } = args as { query: string };
        const result = await webSearch(query);
        output = JSON.stringify(result, null, 2);
        break;
      }
      case 'generate_chart': {
        const { chartType, data, title } = args as { chartType: string; data: string; title?: string };
        const result = await generateChart(chartType, data, title);
        output = JSON.stringify(result, null, 2);
        break;
      }
      case 'text_analysis': {
        const { action, text } = args as { action: string; text: string };
        const result = textAnalysis(action, text);
        output = JSON.stringify(result, null, 2);
        break;
      }
      default:
        output = `Unknown tool: ${toolName}`;
    }

    const duration = Date.now() - start;
    await db.toolLog.create({
      data: { toolName, input: JSON.stringify(args), output: output.slice(0, 5000), duration, status: 'success' },
    });

    return { toolCallId: toolCall.id, toolName, output };
  } catch (error) {
    const errMsg = error instanceof Error ? error.message : String(error);
    await db.toolLog.create({
      data: { toolName, input: toolCall.function.arguments, output: errMsg, status: 'error' },
    });
    return { toolCallId: toolCall.id, toolName, output: errMsg, isError: true };
  }
}

// === TOOL IMPLEMENTATIONS ===

async function bashExecute(command: string): Promise<string> {
  const { exec } = await import('child_process');
  const { promisify } = await import('util');
  const execAsync = promisify(exec);

  try {
    const { stdout, stderr } = await execAsync(command, {
      cwd: '/home/z/my-project',
      timeout: 30000,
      maxBuffer: 1024 * 1024,
    });
    const output = (stdout || '') + (stderr ? `\n[stderr]: ${stderr}` : '');
    return output.trim() || 'Command executed successfully (no output)';
  } catch (error: unknown) {
    const err = error as { stderr?: string; message?: string; stdout?: string };
    const output = (err.stdout || '') + (err.stderr || '') + (err.message ? `\n${err.message}` : '');
    return output.trim() || `Command failed`;
  }
}

async function codeExecute(code: string, language: string): Promise<string> {
  const { exec } = await import('child_process');
  const { promisify } = await import('util');
  const execAsync = promisify(exec);
  const fs = await import('fs/promises');

  const ext = language === 'python' ? 'py' : 'js';
  const cmd = language === 'python' ? 'python3' : 'node';
  const tmpFile = `/tmp/tool_exec_${Date.now()}.${ext}`;

  try {
    await fs.writeFile(tmpFile, code, 'utf-8');
    const { stdout, stderr } = await execAsync(`${cmd} ${tmpFile}`, {
      timeout: 30000,
      maxBuffer: 1024 * 1024,
    });
    await fs.unlink(tmpFile).catch(() => {});
    return (stdout || '') + (stderr ? `\n[stderr]: ${stderr}` : '') || 'Executed successfully (no output)';
  } catch (error: unknown) {
    await fs.unlink(tmpFile).catch(() => {});
    const err = error as { stderr?: string; message?: string; stdout?: string };
    return `Error: ${(err.stderr || err.message || 'Execution failed')}`;
  }
}

async function fileOperations(action: string, path?: string, content?: string) {
  const fs = await import('fs/promises');
  const basePath = '/home/z/my-project';

  switch (action) {
    case 'list': {
      const targetPath = path || basePath;
      try {
        const entries = await fs.readdir(targetPath, { withFileTypes: true });
        return { path: targetPath, entries: entries.slice(0, 100).map(e => ({ name: e.name, type: e.isDirectory() ? 'directory' : 'file' })) };
      } catch {
        return { error: 'Path not found', path: targetPath };
      }
    }
    case 'read': {
      if (!path) return { error: 'Path required' };
      try {
        const data = await fs.readFile(path, 'utf-8');
        return { path, content: data.slice(0, 15000), truncated: data.length > 15000 };
      } catch {
        return { error: 'File not found', path };
      }
    }
    case 'write': {
      if (!path || content === undefined) return { error: 'Path and content required' };
      try {
        const fullContent = typeof content === 'string' ? content : JSON.stringify(content, null, 2);
        await fs.writeFile(path, fullContent, 'utf-8');
        return { success: true, path, bytes: fullContent.length };
      } catch (e) {
        return { error: `Write failed: ${e instanceof Error ? e.message : String(e)}`, path };
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

async function webSearch(query: string) {
  try {
    const ZAI = (await import('z-ai-web-dev-sdk')).default;
    const zai = await ZAI.create();
    const results = await zai.functions.invoke('web_search', { query, num: 5 });
    return {
      results: Array.isArray(results)
        ? results.map((r: { name?: string; url?: string; snippet?: string; title?: string }) => ({
            title: r.name || r.title || '',
            url: r.url || '',
            snippet: r.snippet || '',
          }))
        : results,
    };
  } catch {
    return { results: [{ title: 'Search unavailable', url: '', snippet: `Could not search for: "${query}"` }] };
  }
}

async function generateChart(chartType: string, dataStr: string, title?: string) {
  try {
    const data = JSON.parse(dataStr);
    const labels: string[] = data.labels || data.map((_: unknown, i: number) => `Item ${i + 1}`);
    const values: number[] = data.values || data.data || Object.values(data).map(Number);

    let svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 400">`;
    svg += `<rect width="600" height="400" fill="#1a1a2e" rx="12"/>`;
    svg += `<text x="300" y="30" fill="#e2e8f0" text-anchor="middle" font-size="16" font-weight="bold" font-family="sans-serif">${title || 'Chart'}</text>`;

    if (chartType === 'bar' || chartType === 'line' || chartType === 'area') {
      const max = Math.max(...values.map(Number), 1);
      const barWidth = Math.min(60, 500 / values.length - 10);
      const startX = 50;
      values.forEach((v: number, i: number) => {
        const h = (Number(v) / max) * 300;
        const x = startX + i * (barWidth + 10);
        const y = 360 - h;
        if (chartType === 'line' || chartType === 'area') {
          svg += `<line x1="${x + barWidth / 2}" y1="${y}" x2="${x + barWidth / 2}" y2="360" stroke="#8b5cf6" stroke-width="2"/>`;
          svg += `<circle cx="${x + barWidth / 2}" cy="${y}" r="4" fill="#a78bfa"/>`;
        } else {
          svg += `<rect x="${x}" y="${y}" width="${barWidth}" height="${h}" fill="#8b5cf6" rx="4"/>`;
        }
        svg += `<text x="${x + barWidth / 2}" y="375" fill="#94a3b8" text-anchor="middle" font-size="10" font-family="sans-serif">${labels[i] || ''}</text>`;
        svg += `<text x="${x + barWidth / 2}" y="${y - 5}" fill="#e2e8f0" text-anchor="middle" font-size="11" font-family="sans-serif">${v}</text>`;
      });
    } else if (chartType === 'pie') {
      const total = values.reduce((a: number, b: number) => a + Number(b), 0) || 1;
      const colors = ['#8b5cf6', '#06b6d4', '#f59e0b', '#10b981', '#ef4444', '#ec4899'];
      let angle = 0;
      values.forEach((v: number, i: number) => {
        const a = (Number(v) / total) * 360;
        const x1 = 300 + 150 * Math.cos((angle * Math.PI) / 180);
        const y1 = 210 + 150 * Math.sin((angle * Math.PI) / 180);
        const x2 = 300 + 150 * Math.cos(((angle + a) * Math.PI) / 180);
        const y2 = 210 + 150 * Math.sin(((angle + a) * Math.PI) / 180);
        svg += `<path d="M300,210 L${x1},${y1} A150,150 0 ${a > 180 ? 1 : 0},1 ${x2},${y2} Z" fill="${colors[i % colors.length]}"/>`;
        svg += `<text x="${300 + 180 * Math.cos(((angle + a / 2) * Math.PI) / 180)}" y="${210 + 180 * Math.sin(((angle + a / 2) * Math.PI) / 180)}" fill="#e2e8f0" text-anchor="middle" font-size="11" font-family="sans-serif">${labels[i] || ''}</text>`;
        angle += a;
      });
    } else if (chartType === 'scatter') {
      const max = Math.max(...values.map(Number), 1);
      values.forEach((v: number, i: number) => {
        svg += `<circle cx="${80 + (i / Math.max(values.length, 1)) * 480}" cy="${360 - (Number(v) / max) * 300}" r="6" fill="#8b5cf6" opacity="0.8"/>`;
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
      const sentences = text.split(/[.!?]+/).filter(Boolean);
      return { words: words.length, characters: text.length, sentences: sentences.length, paragraphs: text.split(/\n\n+/).filter(Boolean).length };
    }
    case 'keywords': {
      const stops = new Set(['the', 'a', 'an', 'is', 'are', 'was', 'were', 'have', 'has', 'had', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from', 'and', 'but', 'or', 'if', 'it', 'this', 'that', 'not']);
      const freq: Record<string, number> = {};
      text.toLowerCase().split(/\s+/).filter(w => w.length > 2 && !stops.has(w)).forEach(w => { freq[w] = (freq[w] || 0) + 1; });
      return Object.entries(freq).sort((a, b) => b[1] - a[1]).slice(0, 15).map(([word, count]) => ({ word, count }));
    }
    case 'sentiment': {
      const pos = ['good', 'great', 'excellent', 'amazing', 'love', 'happy', 'best', 'perfect'];
      const neg = ['bad', 'terrible', 'horrible', 'awful', 'hate', 'sad', 'worst', 'fail'];
      const words = text.toLowerCase().split(/\s+/);
      let p = 0, n = 0;
      words.forEach(w => { if (pos.some(x => w.includes(x))) p++; if (neg.some(x => w.includes(x))) n++; });
      const s = p + n === 0 ? 0.5 : p / (p + n);
      return { score: Math.round(s * 100) / 100, label: s > 0.6 ? 'Positive' : s < 0.4 ? 'Negative' : 'Neutral' };
    }
    case 'summarize': {
      const sentences = text.split(/[.!?]+/).filter(s => s.trim().length > 20);
      if (sentences.length <= 3) return { summary: text.slice(0, 500) };
      const freq: Record<string, number> = {};
      text.toLowerCase().split(/\s+/).forEach(w => { if (w.length > 3) freq[w] = (freq[w] || 0) + 1; });
      return { summary: sentences.map(s => ({ s, score: s.toLowerCase().split(/\s+/).reduce((a, w) => a + (freq[w] || 0), 0) })).sort((a, b) => b.score - a.score).slice(0, 3).map(x => x.s.trim()).join('. ') + '.' };
    }
    default:
      return { error: 'Unknown action' };
  }
}
