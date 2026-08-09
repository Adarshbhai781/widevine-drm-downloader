'use client';

import { useChatStore } from '@/store/chat-store';
import { Conversation } from '@/store/chat-store';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Plus, MessageSquare, Trash2, Settings, Moon, Sun, Zap, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { motion, AnimatePresence } from 'framer-motion';

export function Sidebar() {
  const {
    conversations,
    activeConversationId,
    sidebarOpen,
    darkMode,
    isLoadingConversations,
    setActiveConversation,
    deleteConversation,
    toggleSidebar,
    setDarkMode,
  } = useChatStore();

  const handleNewChat = async () => {
    try {
      const res = await fetch('/api/conversations', { method: 'POST' });
      const conversation: Conversation = await res.json();
      useChatStore.getState().addConversation(conversation);
    } catch (e) {
      console.error('Failed to create conversation', e);
    }
  };

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    try {
      await fetch(`/api/conversations/${id}`, { method: 'DELETE' });
      deleteConversation(id);
    } catch {
      console.error('Failed to delete');
    }
  };

  return (
    <AnimatePresence>
      {sidebarOpen && (
        <motion.aside
          initial={{ x: -280, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: -280, opacity: 0 }}
          transition={{ type: 'spring', damping: 25, stiffness: 200 }}
          className="fixed left-0 top-0 bottom-0 w-[280px] bg-card border-r border-border z-40 flex flex-col"
        >
          {/* Header */}
          <div className="p-4 border-b border-border">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center">
                  <Zap className="w-4 h-4 text-white" />
                </div>
                <span className="font-bold text-lg">Z.ai Agent</span>
              </div>
              <Button variant="ghost" size="icon" onClick={toggleSidebar} className="md:hidden">
                <X className="w-4 h-4" />
              </Button>
            </div>
            <Button onClick={handleNewChat} className="w-full gap-2 bg-gradient-to-r from-violet-600 to-purple-600 hover:from-violet-500 hover:to-purple-500 text-white">
              <Plus className="w-4 h-4" />
              New Chat
            </Button>
          </div>

          {/* Chat List */}
          <ScrollArea className="flex-1 p-2">
            {isLoadingConversations ? (
              <div className="space-y-2 p-2">
                {[...Array(5)].map((_, i) => (
                  <div key={i} className="h-12 rounded-lg bg-muted animate-pulse" />
                ))}
              </div>
            ) : conversations.length === 0 ? (
              <div className="text-center text-muted-foreground text-sm p-8">
                <MessageSquare className="w-8 h-8 mx-auto mb-2 opacity-50" />
                <p>No conversations yet</p>
                <p className="text-xs mt-1">Start a new chat!</p>
              </div>
            ) : (
              <div className="space-y-1">
                {conversations.map((conv) => (
                  <motion.div
                    key={conv.id}
                    whileHover={{ scale: 1.01 }}
                    whileTap={{ scale: 0.99 }}
                    onClick={() => setActiveConversation(conv.id)}
                    className={cn(
                      'group flex items-center gap-2 p-3 rounded-lg cursor-pointer transition-all',
                      activeConversationId === conv.id
                        ? 'bg-violet-500/10 text-violet-400 border border-violet-500/20'
                        : 'hover:bg-muted text-foreground'
                    )}
                  >
                    <MessageSquare className="w-4 h-4 shrink-0 opacity-60" />
                    <span className="truncate text-sm flex-1">{conv.title}</span>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={(e) => handleDelete(e, conv.id)}
                      className="opacity-0 group-hover:opacity-100 h-6 w-6 shrink-0"
                    >
                      <Trash2 className="w-3 h-3" />
                    </Button>
                  </motion.div>
                ))}
              </div>
            )}
          </ScrollArea>

          {/* Footer */}
          <div className="p-4 border-t border-border space-y-2">
            <Button
              variant="ghost"
              className="w-full justify-start gap-2"
              onClick={() => setDarkMode(!darkMode)}
            >
              {darkMode ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
              {darkMode ? 'Light Mode' : 'Dark Mode'}
            </Button>
            <div className="flex items-center gap-2 px-2 text-xs text-muted-foreground">
              <Settings className="w-3 h-3" />
              <span>Agentic AI with Tool Calling</span>
            </div>
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
