import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { executeTool, TOOLS } from '@/lib/agent';
import type { ToolCall } from '@/lib/agent';

// System prompt — makes the AI a true autonomous agent
const SYSTEM_PROMPT = `You are Z.ai Agent — an advanced autonomous AI agent. You think, plan, and execute tasks just like a senior developer.

## YOUR CAPABILITIES
You have REAL tools you can call to do actual work. When you need to use a tool, output a tool call in this EXACT format:

TOOL_CALL:{"name":"tool_name","args":{"key":"value"}}

Available tools:
1. **bash_execute** — Run shell commands. Args: {"command": "your bash command"}
2. **code_execute** — Run Python/JS code. Args: {"code": "your code", "language": "python"|"javascript"}
3. **file_operations** — Read/write/list/delete files. Args: {"action": "read"|"write"|"list"|"delete", "path": "/path", "content": "text for write"}
4. **web_search** — Search internet. Args: {"query": "search terms"}
5. **generate_chart** — Make SVG charts. Args: {"chartType": "bar"|"line"|"pie"|"scatter"|"area", "data": '{"labels":[],"values":[]}', "title": "Chart Title"}
6. **text_analysis** — Analyze text. Args: {"action": "wordcount"|"keywords"|"sentiment"|"summarize", "text": "text to analyze"}

## IMPORTANT: TOOL CALL FORMAT
To call a tool, put this on its OWN line:
TOOL_CALL:{"name":"bash_execute","args":{"command":"ls -la"}}
Then continue your response after. You can make MULTIPLE tool calls in one response. Each goes on its own line.

## HOW YOU WORK
1. User gives you a task
2. Think about approach, explain briefly
3. CALL TOOLS to do the actual work
4. After getting results, explain what happened
5. If there's an error, fix and retry

## CODE GENERATION
When asked to write code:
1. Explain what you'll build
2. Write the code
3. Use code_execute or file_operations to save AND run it
4. Show the output

## RULES
- ALWAYS execute code when asked — don't just write it, RUN it
- Support Hindi/Hinglish and English equally
- Use markdown formatting
- Be thorough — actually complete tasks
- Maximum 8 tool calls per turn`;

// Parse TOOL_CALL: patterns from LLM response
function parseToolCalls(text: string): { cleanText: string; toolCalls: ToolCall[] } {
  const lines = text.split('\n');
  const toolCalls: ToolCall[] = [];
  const cleanLines: string[] = [];

  for (const line of lines) {
    const match = line.match(/^TOOL_CALL:(.+)$/);
    if (match) {
      try {
        const parsed = JSON.parse(match[1]);
        toolCalls.push({
          id: `call_${Date.now()}_${toolCalls.length}`,
          type: 'function',
          function: {
            name: parsed.name || parsed.tool || 'unknown',
            arguments: JSON.stringify(parsed.args || parsed.arguments || parsed.params || {}),
          },
        });
      } catch {
        cleanLines.push(line);
      }
    } else {
      cleanLines.push(line);
    }
  }

  // Also check for code blocks that look like they should be executed
  // Pattern: user asks to run code and LLM writes it in a code block
  return {
    cleanText: cleanLines.join('\n'),
    toolCalls,
  };
}

// Check if the response has code blocks that should be auto-executed
function extractAutoExecuteCode(text: string, userMessage: string): ToolCall[] {
  const toolCalls: ToolCall[] = [];
  const lowerMsg = userMessage.toLowerCase();

  // Only auto-execute if user explicitly asked to run/execute the code
  const shouldAutoExec = /run|execute|chalao|karo|test|try|check|dekho|compile/i.test(lowerMsg);
  if (!shouldAutoExec) return [];

  // Extract code blocks
  const codeBlockRegex = /```(\w+)\s*\n([\s\S]*?)```/g;
  let match;
  while ((match = codeBlockRegex.exec(text)) !== null) {
    const lang = match[1].toLowerCase();
    const code = match[2].trim();
    if (code.length > 5 && ['python', 'py', 'javascript', 'js', 'bash', 'sh', 'shell'].includes(lang)) {
      if (['bash', 'sh', 'shell'].includes(lang)) {
        toolCalls.push({
          id: `auto_${Date.now()}_${toolCalls.length}`,
          type: 'function',
          function: { name: 'bash_execute', arguments: JSON.stringify({ command: code }) },
        });
      } else {
        toolCalls.push({
          id: `auto_${Date.now()}_${toolCalls.length}`,
          type: 'function',
          function: { name: 'code_execute', arguments: JSON.stringify({ code, language: lang === 'py' ? 'python' : 'javascript' }) },
        });
      }
    }
  }

  return toolCalls;
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const { messages: clientMessages } = await request.json();

    const conversation = await db.conversation.findUnique({ where: { id } });
    if (!conversation) {
      return NextResponse.json({ error: 'Conversation not found' }, { status: 404 });
    }

    // Save user message
    const lastUserMsg = clientMessages[clientMessages.length - 1];
    if (lastUserMsg?.role === 'user') {
      await db.message.create({
        data: { conversationId: id, role: 'user', content: lastUserMsg.content },
      });
    }

    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      async start(controller) {
        let fullResponse = '';

        try {
          // Init ZAI SDK - carefully handle ES module
          let zai: any = null;
          try {
            let ZAI;
            try {
              ZAI = (await import('z-ai-web-dev-sdk')).default;
            } catch (_importErr) {
              // Dynamic import failed — SDK may not be available
            }
            if (ZAI && typeof ZAI.create === 'function') {
              zai = await ZAI.create();
            }
          } catch (sdkErr) {
            console.error('ZAI SDK init failed:', sdkErr);
            controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'content', text: 'AI backend is starting up. Please try again in a moment.' })}\n\n`));
            controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'done' })}\n\n`));
            controller.close();
            return;
          }

          // Build LLM messages
          const llmMessages: any[] = [
            { role: 'system', content: SYSTEM_PROMPT },
            ...clientMessages.map((m: { role: string; content: string; toolCalls?: string; role?: string }) => ({
              role: m.role === 'user' ? 'user' : 'assistant',
              content: m.content,
            })),
          ];

          const MAX_ROUNDS = 8;
          const userText = lastUserMsg?.content || '';

          // === AGENTIC LOOP ===
          for (let round = 0; round < MAX_ROUNDS; round++) {
            let llmResponseText = '';
            let allToolCalls: ToolCall[] = [];

            try {
              // Call LLM with timeout protection
              const response = await Promise.race([
                zai.chat.completions.create({
                  messages: llmMessages,
                  stream: false,
                  thinking: { type: 'disabled' },
                }),
                new Promise((_, reject) => setTimeout(() => reject(new Error('LLM request timed out after 60s')), 60000)),
              ]);

              // Parse response safely
              try {
                const choice = response?.choices?.[0];
                if (choice?.message?.content) {
                  llmResponseText = choice.message.content;
                } else if (typeof response === 'string') {
                  llmResponseText = response;
                } else if (response?.content) {
                  llmResponseText = response.content;
                } else if (response?.message?.content) {
                  llmResponseText = response.message.content;
                } else {
                  llmResponseText = JSON.stringify(response).slice(0, 500);
                }
              } catch {
                llmResponseText = 'Received a response but could not parse it.';
              }
            } catch (llmError) {
              const errMsg = llmError instanceof Error ? llmError.message : String(llmError);
              console.error('LLM error:', errMsg);
              controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'error', message: `LLM Error: ${errMsg}` })}\n\n`));
              break;
            }

            // Parse tool calls from response
            const parsed = parseToolCalls(llmResponseText);
            const explicitToolCalls = parsed.toolCalls;

            // Also check for auto-executable code blocks
            const autoExecCalls = extractAutoExecuteCode(parsed.cleanText, userText);
            allToolCalls = [...explicitToolCalls, ...autoExecCalls];

            // Stream the text content to user
            if (parsed.cleanText.trim()) {
              const words = parsed.cleanText.split(/(\s+)/);
              for (const word of words) {
                controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'content', text: word })}\n\n`));
              }
              fullResponse += parsed.cleanText;
            }

            // If no tool calls, we're done
            if (allToolCalls.length === 0) break;

            // Execute tools
            let toolResultsText = '';
            for (const toolCall of allToolCalls) {
              controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'tool_start', name: toolCall.function.name, id: toolCall.id })}\n\n`));

              const result = await executeTool(toolCall);
              const preview = result.output.slice(0, 3000);

              controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'tool_result', result: { toolCallId: result.toolCallId, toolName: result.toolName, output: preview, isError: result.isError } })}\n\n`));
              controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'tool_end', name: toolCall.function.name, id: toolCall.id })}\n\n`));

              toolResultsText += `\n\n**[${result.toolName} Result]**:\n${result.output.slice(0, 4000)}`;
            }

            fullResponse += toolResultsText;

            // Send tool results back to LLM for it to analyze/continue
            if (allToolCalls.length > 0 && round < MAX_ROUNDS - 1) {
              llmMessages.push({ role: 'assistant', content: llmResponseText });
              llmMessages.push({
                role: 'user',
                content: `[Tool execution results for your previous response]:${toolResultsText}\n\nPlease analyze these results and provide a summary or continue if needed.`,
              });
              await new Promise(r => setTimeout(r, 500));
            }
          }

          // Save to DB
          if (fullResponse) {
            await db.message.create({
              data: { conversationId: id, role: 'assistant', content: fullResponse },
            });

            const msgCount = await db.message.count({ where: { conversationId: id } });
            if (msgCount <= 2) {
              const title = userText.slice(0, 50) || 'New Chat';
              await db.conversation.update({
                where: { id },
                data: { title: title + (userText.length > 50 ? '...' : '') },
              });
            }
          }

          controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'done' })}\n\n`));
          controller.close();
        } catch (error) {
          const errMsg = error instanceof Error ? error.message : String(error);
          console.error('Stream error:', errMsg);
          controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'error', message: errMsg })}\n\n`));
          controller.close();
        }
      },
    });

    return new Response(stream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
      },
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    );
  }
}

// GET /api/chat/[id] — Fetch messages
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const messages = await db.message.findMany({
      where: { conversationId: id },
      orderBy: { createdAt: 'asc' },
    });
    return NextResponse.json(messages);
  } catch {
    return NextResponse.json({ error: 'Failed to fetch messages' }, { status: 500 });
  }
}
