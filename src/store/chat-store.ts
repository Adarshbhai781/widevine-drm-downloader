import { create } from 'zustand';

export interface Message {
  id: string;
  conversationId: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  toolCalls?: string;
  toolCallId?: string;
  metadata?: string;
  createdAt: string;
}

export interface Conversation {
  id: string;
  title: string;
  model: string;
  createdAt: string;
  updatedAt: string;
  _count?: { messages: number };
  messages?: Message[];
}

export interface ToolCallDisplay {
  name: string;
  status: 'running' | 'done' | 'error';
  output?: string;
}

interface ChatState {
  // Conversations
  conversations: Conversation[];
  activeConversationId: string | null;
  isLoadingConversations: boolean;

  // Messages
  messages: Message[];
  streamingContent: string;
  activeToolCalls: ToolCallDisplay[];
  isStreaming: boolean;

  // UI
  sidebarOpen: boolean;
  darkMode: boolean;

  // Actions
  setConversations: (conversations: Conversation[]) => void;
  addConversation: (conversation: Conversation) => void;
  setActiveConversation: (id: string | null) => void;
  setMessages: (messages: Message[]) => void;
  addMessage: (message: Message) => void;
  setStreamingContent: (content: string) => void;
  appendStreamingContent: (content: string) => void;
  addToolCall: (name: string) => void;
  updateToolCall: (name: string, status: 'done' | 'error', output?: string) => void;
  setStreaming: (streaming: boolean) => void;
  toggleSidebar: () => void;
  setDarkMode: (dark: boolean) => void;
  deleteConversation: (id: string) => void;
  updateConversationTitle: (id: string, title: string) => void;
  resetStream: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  conversations: [],
  activeConversationId: null,
  isLoadingConversations: false,
  messages: [],
  streamingContent: '',
  activeToolCalls: [],
  isStreaming: false,
  sidebarOpen: true,
  darkMode: true,

  setConversations: (conversations) => set({ conversations }),
  addConversation: (conversation) =>
    set((state) => ({
      conversations: [conversation, ...state.conversations],
      activeConversationId: conversation.id,
      messages: [],
    })),
  setActiveConversation: (id) => set({ activeConversationId: id, messages: [], streamingContent: '', activeToolCalls: [] }),
  setMessages: (messages) => set({ messages }),
  addMessage: (message) =>
    set((state) => ({
      messages: [...state.messages, message],
    })),
  setStreamingContent: (content) => set({ streamingContent: content }),
  appendStreamingContent: (content) =>
    set((state) => ({ streamingContent: state.streamingContent + content })),
  addToolCall: (name) =>
    set((state) => ({
      activeToolCalls: [...state.activeToolCalls, { name, status: 'running' }],
    })),
  updateToolCall: (name, status, output) =>
    set((state) => ({
      activeToolCalls: state.activeToolCalls.map((tc) =>
        tc.name === name ? { ...tc, status, output } : tc
      ),
    })),
  setStreaming: (streaming) => set({ isStreaming: streaming }),
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  setDarkMode: (dark) => {
    if (dark) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
    set({ darkMode: dark });
  },
  deleteConversation: (id) =>
    set((state) => ({
      conversations: state.conversations.filter((c) => c.id !== id),
      activeConversationId: state.activeConversationId === id ? null : state.activeConversationId,
      messages: state.activeConversationId === id ? [] : state.messages,
    })),
  updateConversationTitle: (id, title) =>
    set((state) => ({
      conversations: state.conversations.map((c) =>
        c.id === id ? { ...c, title } : c
      ),
    })),
  resetStream: () => set({ streamingContent: '', activeToolCalls: [], isStreaming: false }),
}));
