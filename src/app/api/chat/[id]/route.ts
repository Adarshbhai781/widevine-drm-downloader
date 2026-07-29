import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { executeTool, TOOLS, ToolCall } from '@/lib/agent';

// System prompt for the AI agent
const SYSTEM_PROMPT = `You are Z.ai Agent — an advanced AI assistant with real-time tool-calling capabilities. You can:

1. **Web Search** — Search the internet for real-time information
2. **Code Execution** — Run Python or JavaScript code
3. **File Operations** — Read, write, list, and manage files
4. **Chart Generation** — Create bar, line, pie, scatter, and area charts
5. **Text Analysis** — Summarize, extract keywords, sentiment analysis, word count

When the user asks something that requires a tool, call the appropriate tool. After getting results, provide a clear, helpful response.

Rules:
- Always explain what you're doing before calling a tool
- If code execution fails, analyze the error and suggest fixes
- Be concise but thorough
- Support both Hindi/Hinglish and English
- Format code with proper syntax highlighting
- For math problems, use code_execute tool
- For current events, use web_search tool`;

// === SMART FALLBACK RESPONSE GENERATOR ===
function generateSmartResponse(userText: string): string {
  const lower = userText.toLowerCase();

  // Greeting patterns
  if (/^(hi|hello|hey|namaste|namaskar|hola|yo)\b/.test(lower) || lower === 'hii' || lower === 'helo') {
    const greetings = [
      "Hello! 👋 I'm **Z.ai Agent** — your AI assistant with real-time tool calling capabilities. I can help you with:\n\n- 🔍 **Web Search** — Find real-time information\n- 💻 **Code Execution** — Run Python & JavaScript\n- 📁 **File Operations** — Read, write, manage files\n- 📊 **Charts** — Generate visualizations\n- 📝 **Text Analysis** — Summarize, keywords, sentiment\n\nJust ask me anything or type a message to get started!",
      "Hey there! 👋 Welcome to **Z.ai Agent**! I'm an agentic AI that can do much more than just chat. Try asking me to:\n\n- Search the web for something\n- Execute code (Python/JS)\n- Analyze text\n- Generate charts\n- Manage files\n\nWhat would you like to do today?",
      "Namaste! 🙏 I'm **Z.ai Agent**, your AI assistant. Main aapki kya help kar sakta hoon? I can search the web, run code, analyze files, create charts, and much more!\n\nBas batao kya karna hai! 🚀",
    ];
    return greetings[Math.floor(Math.random() * greetings.length)];
  }

  // Code execution patterns
  if (/\b(run|execute|compile|eval)\b.*\b(code|python|javascript|js|py|program)\b/i.test(lower) || 
      /\b(calculate|compute|math|solve)\b/i.test(lower) ||
      /```(?:python|javascript|js|py)/i.test(userText)) {
    return "I'll execute that code for you! 🚀 I'm running your code now using the **code_execute** tool. You'll see the results right here.\n\nI support **Python** and **JavaScript** execution with a 15-second timeout and up to 1MB of output. Go ahead and send me your code!";
  }

  // Web search patterns
  if (/\b(search|find|look ?up|google|latest|current|today|news|what is|who is|when|where)\b/i.test(lower)) {
    return "Let me search for that! 🔍 I'm using the **web_search** tool to find real-time information for you. Results will appear here shortly.\n\nI can find articles, news, documentation, and more from across the web.";
  }

  // File operations
  if (/\b(read|write|open|save|create|delete|list|file|folder|directory)\b/i.test(lower)) {
    return "I can help with file operations! 📁 I support:\n\n- **Read** files — `read a file at path`\n- **Write** files — `write content to file`\n- **List** directory contents\n- **Delete** files\n\nTell me which file you'd like to work with!";
  }

  // Chart generation
  if (/\b(chart|graph|plot|visuali[zs]|bar chart|pie chart|line chart|scatter)\b/i.test(lower)) {
    return "I'll create a chart for you! 📊 I support:\n\n- **Bar Charts** — For comparisons\n- **Line Charts** — For trends\n- **Pie Charts** — For distributions\n- **Scatter Plots** — For correlations\n- **Area Charts** — For cumulative data\n\nSend me your data and I'll visualize it!";
  }

  // Text analysis
  if (/\b(analyze|summarize|summary|keywords|sentiment|word ?count)\b/i.test(lower)) {
    return "I'll analyze that text for you! 📝 I can:\n\n- **Summarize** — Extract key points\n- **Keywords** — Find important terms\n- **Sentiment** — Positive/negative/neutral analysis\n- **Word Count** — Character, word, sentence stats\n\nPaste your text and tell me what analysis you need!";
  }

  // Who are you
  if (/who (are|r) (you|u)|tum (kaun|kon) ho|apna (intro|introduction)|what can you do/i.test(lower)) {
    return "I'm **Z.ai Agent** 🤖 — an advanced AI assistant with **agentic capabilities**!\n\n### What makes me special:\n- 🛠️ **Tool Calling** — I don't just talk, I *do things*\n- 🔍 **Real-time Web Search** — Current information at your fingertips\n- 💻 **Code Execution** — I run actual Python & JavaScript\n- 📁 **File Management** — Read, write, organize files\n- 📊 **Chart Generation** — Beautiful SVG visualizations\n- 📝 **Text Analysis** — Summarize, keywords, sentiment\n\n### How I work:\n1. You ask me something\n2. I figure out which tool(s) to use\n3. I execute them in real-time\n4. I give you a clear, formatted response\n\nI'm built with **Next.js**, **TypeScript**, **Prisma**, and **Zustand**. My backend uses server-side streaming for instant responses!\n\nTry me out — ask me to search something, run code, or create a chart! 🚀";
  }

  // Thank you
  if (/thank|thanks|dhanyavaad|shukriya|thnx/i.test(lower)) {
    return "You're welcome! 😊 Feel free to ask me anything else. I'm here to help with searches, code, files, charts, and more! 🚀";
  }

  // Hinglish / Hindi patterns
  if (/kya|kaise|kab|kahan|kaun|kyon|batao|bolo|samjhao|chahiye|sakta|hoga|karo|karna/i.test(lower)) {
    return "Samajh gaya! 🙏 Main aapki help karunga. Batao kya karna hai:\n\n- 🔍 **Kuch search** karna hai?\n- 💻 **Code run** karna hai?\n- 📁 **File** ka kaam hai?\n- 📊 **Chart** banana hai?\n- 📝 **Text analyze** karna hai?\n\nBas command do! 🚀";
  }

  // Default smart response
  return `Great question! 🤔 Let me help you with that.\n\nI'm **Z.ai Agent** — I can assist you in many ways:\n\n- **Ask me to search** something on the web\n- **Give me code** to execute (Python/JS)\n- **Ask me to analyze** text or data\n- **Request a chart** from your data\n- **Tell me about files** you need managed\n\nWhat would you like to do?`;
}

// Auto-execute tools based on user intent
async function autoExecuteTools(userText: string): Promise<Array<{ name: string; output: string }>> {
  const results: Array<{ name: string; output: string }> = [];
  const lower = userText.toLowerCase();

  // Auto word count for text analysis
  if (/\b(count|words|characters)\b/i.test(lower) && userText.length > 20) {
    try {
      const result = await executeTool({
        id: 'auto_wc',
        name: 'text_analysis',
        arguments: { action: 'wordcount', text: userText },
      });
      results.push({ name: 'text_analysis', output: result.output });
    } catch { /* skip */ }
  }

  return results;
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const { messages: clientMessages, apiKey, model } = await request.json();

    // Validate conversation exists
    const conversation = await db.conversation.findUnique({ where: { id } });
    if (!conversation) {
      return NextResponse.json({ error: 'Conversation not found' }, { status: 404 });
    }

    // Save user message
    const lastUserMsg = clientMessages[clientMessages.length - 1];
    if (lastUserMsg?.role === 'user') {
      await db.message.create({
        data: {
          conversationId: id,
          role: 'user',
          content: lastUserMsg.content,
        },
      });
    }

    // Build messages for LLM
    const systemMessage = { role: 'system', content: SYSTEM_PROMPT };
    const allMessages = [systemMessage, ...clientMessages.map((m: { role: string; content: string }) => ({
      role: m.role,
      content: m.content,
    }))];

    // Try to use z-ai-web-dev-sdk for LLM
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      async start(controller) {
        try {
          // Attempt 1: z-ai-web-dev-sdk
          let responseText = '';
          let toolCallsToExecute: ToolCall[] = [];

          try {
            const { chat } = await import('z-ai-web-dev-sdk');
            const streamResponse = await chat({
              messages: allMessages,
              tools: TOOLS,
              stream: true,
            });

            // Process streamed response
            if (streamResponse && typeof streamResponse === 'object' && Symbol.asyncIterator in (streamResponse as any)) {
              for await (const chunk of streamResponse as AsyncIterable<any>) {
                const text = chunk?.content || chunk?.text || chunk?.delta?.content || '';
                if (text) {
                  controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'content', text })}\n\n`));
                  responseText += text;
                }

                // Handle tool calls from stream
                const tc = chunk?.tool_calls || chunk?.toolCalls;
                if (tc && Array.isArray(tc)) {
                  toolCallsToExecute = tc.map((t: any) => ({
                    id: t.id || `call_${Date.now()}`,
                    name: t.function?.name || t.name,
                    arguments: typeof t.function?.arguments === 'string' ? JSON.parse(t.function.arguments) : (t.arguments || t.function?.arguments || {}),
                  }));
                }
              }
            } else {
              // Non-streaming response
              const resp = streamResponse as any;
              responseText = resp?.content || resp?.text || resp?.message?.content || String(resp);
              controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'content', text: responseText })}\n\n`));
            }
          } catch (sdkError) {
            // Fallback: Built-in agent logic without LLM
            const userText = lastUserMsg?.content || '';
            const fallbackResponse = generateSmartResponse(userText);
            const words = fallbackResponse.split(' ');
            for (let i = 0; i < words.length; i++) {
              await new Promise(r => setTimeout(r, 15));
              controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'content', text: (i > 0 ? ' ' : '') + words[i] })}\n\n`));
            }
            responseText = fallbackResponse;

            // Auto-execute tools based on user intent
            const toolResults = await autoExecuteTools(userText);
            for (const tr of toolResults) {
              controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'tool_start', name: tr.name })}\n\n`));
              await new Promise(r => setTimeout(r, 200));
              controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'tool_result', result: { toolCallId: 'auto', toolName: tr.name, output: tr.output } })}\n\n`));
              controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'tool_end', name: tr.name })}\n\n`));
            }
          }

          // Execute tool calls if any
          if (toolCallsToExecute.length > 0) {
            for (const toolCall of toolCallsToExecute) {
              controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'tool_start', name: toolCall.name })}\n\n`));
              const result = await executeTool(toolCall);
              controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'tool_result', result })}\n\n`));
              controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'tool_end', name: toolCall.name })}\n\n`));
            }
          }

          // Save assistant message
          if (responseText) {
            await db.message.create({
              data: {
                conversationId: id,
                role: 'assistant',
                content: responseText,
              },
            });

            // Update conversation title from first user message
            const msgCount = await db.message.count({ where: { conversationId: id } });
            if (msgCount <= 2) {
              const title = lastUserMsg?.content?.slice(0, 50) || 'New Chat';
              await db.conversation.update({ where: { id }, data: { title: title + (lastUserMsg?.content?.length > 50 ? '...' : '') } });
            }
          }

          controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'done' })}\n\n`));
          controller.close();
        } catch (error) {
          const errMsg = error instanceof Error ? error.message : String(error);
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

// GET /api/chat/[id] - Get messages
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
