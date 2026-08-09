'use client';

import { useEffect, useCallback } from 'react';
import { Sidebar } from '@/components/chat/sidebar';
import { ChatMessages } from '@/components/chat/messages';
import { ChatInput } from '@/components/chat/input';
import { useChatStore } from '@/store/chat-store';
import { Button } from '@/components/ui/button';
import { Menu, Zap } from 'lucide-react';
import { motion } from 'framer-motion';

export default function Home() {
  const {
    activeConversationId,
    conversations,
    messages,
    streamingContent,
    activeToolCalls,
    isStreaming,
    sidebarOpen,
    darkMode,
    setConversations,
    setActiveConversation,
    setMessages,
    addMessage,
    setStreamingContent,
    appendStreamingContent,
    addToolCall,
    updateToolCall,
    setStreaming,
    toggleSidebar,
    resetStream,
    setDarkMode,
  } = useChatStore();

  // Initialize dark mode
  useEffect(() => {
    setDarkMode(true);
  }, []);

  // Load conversations on mount
  useEffect(() => {
    const loadConversations = async () => {
      try {
        const res = await fetch('/api/conversations');
        const data = await res.json();
        setConversations(data);
      } catch {
        console.error('Failed to load conversations');
      }
    };
    loadConversations();
  }, [setConversations]);

  // Load messages when conversation changes
  useEffect(() => {
    if (activeConversationId) {
      const loadMessages = async () => {
        try {
          const res = await fetch(`/api/conversations/${activeConversationId}`);
          const data = await res.json();
          if (data.messages) {
            setMessages(data.messages);
          }
        } catch {
          console.error('Failed to load messages');
        }
      };
      loadMessages();
    }
  }, [activeConversationId, setMessages]);

  // Auto-create conversation if none exists
  const ensureConversation = useCallback(async (): Promise<string | null> => {
    if (activeConversationId) return activeConversationId;

    try {
      const res = await fetch('/api/conversations', { method: 'POST' });
      const conversation = await res.json();
      useChatStore.getState().addConversation(conversation);
      return conversation.id;
    } catch {
      return null;
    }
  }, [activeConversationId]);

  // Handle sending messages
  const handleSend = useCallback(async (content: string) => {
    const convId = await ensureConversation();
    if (!convId) return;

    // Add user message optimistically
    const userMsg = {
      id: `msg_${Date.now()}`,
      conversationId: convId,
      role: 'user' as const,
      content,
      createdAt: new Date().toISOString(),
    };
    addMessage(userMsg);
    setStreaming(true);
    resetStream();

    // Collect messages for API
    const currentMessages = [...useChatStore.getState().messages, userMsg];
    const apiMessages = currentMessages.map(m => ({ role: m.role, content: m.content }));

    try {
      const res = await fetch(`/api/chat/${convId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: apiMessages }),
      });

      if (!res.ok) throw new Error('Failed to send message');

      const reader = res.body?.getReader();
      if (!reader) throw new Error('No reader');

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(line.slice(6));

            switch (data.type) {
              case 'content':
                appendStreamingContent(data.text);
                break;
              case 'tool_start':
                addToolCall(data.name);
                break;
              case 'tool_result':
                updateToolCall(data.result.toolName, 'done', data.result.output);
                break;
              case 'tool_end':
                break;
              case 'error':
                appendStreamingContent(`\n\n⚠️ Error: ${data.message}`);
                break;
              case 'done':
                break;
            }
          } catch {
            // Skip malformed JSON
          }
        }
      }

      // Save the full streamed content as assistant message
      const finalContent = useChatStore.getState().streamingContent;
      if (finalContent) {
        addMessage({
          id: `msg_${Date.now()}_resp`,
          conversationId: convId,
          role: 'assistant',
          content: finalContent,
          createdAt: new Date().toISOString(),
        });
      }
    } catch (error) {
      const errMsg = error instanceof Error ? error.message : 'Failed to send message';
      appendStreamingContent(`\n\n⚠️ Error: ${errMsg}`);
    } finally {
      setStreaming(false);
      // Refresh conversations to get updated titles
      try {
        const res = await fetch('/api/conversations');
        const data = await res.json();
        setConversations(data);
      } catch {
        // ignore
      }
    }
  }, [activeConversationId, ensureConversation, addMessage, setStreaming, resetStream, appendStreamingContent, addToolCall, updateToolCall, setConversations]);

  return (
    <div className="min-h-screen bg-background flex">
      {/* Sidebar */}
      <Sidebar />

      {/* Main content */}
      <div className={`flex-1 flex flex-col transition-all duration-300 ${sidebarOpen ? 'ml-[280px]' : 'ml-0'}`}>
        {/* Top bar */}
        <header className="h-14 border-b border-border flex items-center px-4 gap-3 bg-card/50 backdrop-blur-xl">
          <Button variant="ghost" size="icon" onClick={toggleSidebar} className="shrink-0">
            <Menu className="w-5 h-5" />
          </Button>
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center">
              <Zap className="w-3 h-3 text-white" />
            </div>
            <div>
              <h1 className="text-sm font-semibold">
                {activeConversationId
                  ? conversations.find(c => c.id === activeConversationId)?.title || 'Chat'
                  : 'Z.ai Agent'}
              </h1>
              <p className="text-[10px] text-muted-foreground">
                {activeToolCalls.length > 0
                  ? `Running ${activeToolCalls.length} tool${activeToolCalls.length > 1 ? 's' : ''}...`
                  : isStreaming
                  ? 'Thinking...'
                  : 'Ready'}
              </p>
            </div>
          </div>
          {isStreaming && (
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 2, repeat: Infinity, ease: 'linear' }}
              className="ml-auto"
            >
              <div className="w-5 h-5 border-2 border-violet-500 border-t-transparent rounded-full" />
            </motion.div>
          )}
        </header>

        {/* Messages area */}
        <ChatMessages
          messages={messages}
          streamingContent={streamingContent}
          activeToolCalls={activeToolCalls}
          isStreaming={isStreaming}
        />

        {/* Input */}
        <ChatInput
          onSend={handleSend}
          isStreaming={isStreaming}
          disabled={!activeConversationId && isStreaming}
        />
      </div>
    </div>
  );
}
