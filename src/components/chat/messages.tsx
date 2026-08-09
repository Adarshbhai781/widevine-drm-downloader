'use client';

import { useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { motion, AnimatePresence } from 'framer-motion';
import { Bot, User, Wrench, Copy, Check, ExternalLink } from 'lucide-react';
import { Message, ToolCallDisplay } from '@/store/chat-store';
import { Button } from '@/components/ui/button';
import { useState } from 'react';

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      variant="ghost"
      size="icon"
      className="absolute top-2 right-2 h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity"
      onClick={() => {
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }}
    >
      {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
    </Button>
  );
}

function ToolCallBlock({ toolCall }: { toolCall: ToolCallDisplay }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="my-2 rounded-lg border border-border bg-card/50 backdrop-blur"
    >
      <div className="flex items-center gap-2 px-3 py-2 text-sm">
        <div className={`w-2 h-2 rounded-full ${toolCall.status === 'running' ? 'bg-yellow-400 animate-pulse' : toolCall.status === 'done' ? 'bg-green-400' : 'bg-red-400'}`} />
        <Wrench className="w-3.5 h-3.5 text-muted-foreground" />
        <span className="font-medium text-violet-400">{toolCall.name}</span>
        <span className="text-muted-foreground text-xs">
          {toolCall.status === 'running' ? 'executing...' : toolCall.status === 'done' ? 'completed' : 'failed'}
        </span>
      </div>
      {toolCall.output && toolCall.status !== 'running' && (
        <div className="px-3 pb-2">
          <pre className="text-xs bg-background rounded p-2 overflow-x-auto max-h-40 text-muted-foreground">
            {toolCall.output.slice(0, 500)}{toolCall.output.length > 500 ? '...' : ''}
          </pre>
        </div>
      )}
    </motion.div>
  );
}

function MessageBubble({ message, isStreaming }: { message: Message | null; isStreaming?: boolean }) {
  const isUser = message?.role === 'user';
  const content = message?.content || '';

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}
    >
      {/* Avatar */}
      <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${isUser ? 'bg-violet-500/20' : 'bg-gradient-to-br from-violet-500 to-purple-600'}`}>
        {isUser ? (
          <User className="w-4 h-4 text-violet-400" />
        ) : (
          <Bot className="w-4 h-4 text-white" />
        )}
      </div>

      {/* Content */}
      <div className={`flex-1 max-w-[85%] ${isUser ? 'flex flex-col items-end' : ''}`}>
        <div className={`rounded-2xl px-4 py-3 ${isUser ? 'bg-violet-500 text-white rounded-br-md' : 'bg-card border border-border rounded-bl-md'} group relative`}>
          {isUser ? (
            <p className="whitespace-pre-wrap text-sm">{content}</p>
          ) : content ? (
            <div className="prose prose-sm prose-invert max-w-none">
              <ReactMarkdown
                components={{
                  code({ className, children, ...props }) {
                    const match = /language-(\w+)/.exec(className || '');
                    const codeStr = String(children).replace(/\n$/, '');

                    if (match) {
                      return (
                        <div className="relative group my-2">
                          <CopyButton text={codeStr} />
                          <SyntaxHighlighter
                            style={oneDark}
                            language={match[1]}
                            PreTag="div"
                            customStyle={{ borderRadius: '8px', fontSize: '13px', margin: 0 }}
                          >
                            {codeStr}
                          </SyntaxHighlighter>
                        </div>
                      );
                    }
                    return (
                      <code className="bg-muted px-1.5 py-0.5 rounded text-sm" {...props}>
                        {children}
                      </code>
                    );
                  },
                  a({ children, href }) {
                    return (
                      <a href={href} target="_blank" rel="noopener noreferrer" className="text-violet-400 hover:underline flex items-center gap-1">
                        {children} <ExternalLink className="w-3 h-3" />
                      </a>
                    );
                  },
                }}
              >
                {content + (isStreaming ? '|' : '')}
              </ReactMarkdown>
            </div>
          ) : isStreaming ? (
            <div className="flex items-center gap-1">
              <div className="w-1.5 h-1.5 bg-violet-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <div className="w-1.5 h-1.5 bg-violet-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <div className="w-1.5 h-1.5 bg-violet-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          ) : null}
        </div>
      </div>
    </motion.div>
  );
}

export function ChatMessages({
  messages,
  streamingContent,
  activeToolCalls,
  isStreaming,
}: {
  messages: Message[];
  streamingContent: string;
  activeToolCalls: ToolCallDisplay[];
  isStreaming: boolean;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, streamingContent, activeToolCalls]);

  return (
    <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4">
      {messages.length === 0 && !isStreaming ? (
        <EmptyState />
      ) : (
        <>
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}
          <AnimatePresence>
            {activeToolCalls.map((tc) => (
              <ToolCallBlock key={tc.name + tc.status} toolCall={tc} />
            ))}
          </AnimatePresence>
          {isStreaming && streamingContent && (
            <MessageBubble
              message={{
                id: 'streaming',
                conversationId: '',
                role: 'assistant',
                content: streamingContent,
                createdAt: new Date().toISOString(),
              }}
              isStreaming
            />
          )}
          {isStreaming && !streamingContent && activeToolCalls.length === 0 && (
            <MessageBubble message={null} isStreaming />
          )}
        </>
      )}
    </div>
  );
}

function EmptyState() {
  const features = [
    { icon: '🔍', title: 'Web Search', desc: 'Real-time information from the internet' },
    { icon: '💻', title: 'Code Execution', desc: 'Run Python & JavaScript code' },
    { icon: '📁', title: 'File Operations', desc: 'Read, write, and manage files' },
    { icon: '📊', title: 'Charts', desc: 'Generate beautiful visualizations' },
    { icon: '📝', title: 'Text Analysis', desc: 'Summarize, keywords, sentiment' },
    { icon: '🤖', title: 'Smart Agent', desc: 'Autonomous task execution' },
  ];

  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="text-center max-w-lg">
        <motion.div
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: 'spring', damping: 15 }}
          className="w-20 h-20 rounded-2xl bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center mx-auto mb-6 shadow-lg shadow-violet-500/20"
        >
          <Bot className="w-10 h-10 text-white" />
        </motion.div>
        <h2 className="text-2xl font-bold mb-2 bg-gradient-to-r from-violet-400 to-purple-400 bg-clip-text text-transparent">
          Z.ai Agent
        </h2>
        <p className="text-muted-foreground mb-8">
          Your AI assistant with real-time tool calling capabilities. Ask me anything!
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {features.map((f, i) => (
            <motion.div
              key={f.title}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              className="p-3 rounded-xl bg-card border border-border hover:border-violet-500/30 transition-colors"
            >
              <div className="text-2xl mb-1">{f.icon}</div>
              <div className="text-sm font-medium">{f.title}</div>
              <div className="text-xs text-muted-foreground">{f.desc}</div>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
}
