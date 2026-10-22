'use client';

import { useState, useRef, KeyboardEvent } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Send, Paperclip, Sparkles, Code, Search, FileText, BarChart3, Loader2 } from 'lucide-react';
import { motion } from 'framer-motion';

const QUICK_PROMPTS = [
  { icon: Search, label: 'Search', prompt: 'Search the web for ' },
  { icon: Code, label: 'Code', prompt: 'Execute this code:\n' },
  { icon: FileText, label: 'Analyze', prompt: 'Analyze this text:\n' },
  { icon: BarChart3, label: 'Chart', prompt: 'Create a chart with this data:\n' },
];

interface ChatInputProps {
  onSend: (message: string) => void;
  isStreaming: boolean;
  disabled?: boolean;
}

export function ChatInput({ onSend, isStreaming, disabled }: ChatInputProps) {
  const [input, setInput] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = () => {
    if (!input.trim() || isStreaming) return;
    onSend(input.trim());
    setInput('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleQuickPrompt = (prompt: string) => {
    setInput(prompt);
    textareaRef.current?.focus();
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
  };

  return (
    <div className="border-t border-border bg-card/50 backdrop-blur-xl p-4">
      {/* Quick action buttons */}
      {!disabled && !input && (
        <div className="flex gap-2 mb-3 overflow-x-auto">
          {QUICK_PROMPTS.map(({ icon: Icon, label, prompt }) => (
            <motion.button
              key={label}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={() => handleQuickPrompt(prompt)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-muted/50 hover:bg-muted border border-border text-xs text-muted-foreground hover:text-foreground transition-colors shrink-0"
            >
              <Icon className="w-3 h-3" />
              {label}
            </motion.button>
          ))}
        </div>
      )}

      {/* Input area */}
      <div className="flex items-end gap-2">
        <div className="flex-1 relative">
          <Textarea
            ref={textareaRef}
            value={input}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder={disabled ? 'Create a new chat first...' : 'Type a message... (Shift+Enter for new line)'}
            disabled={isStreaming || disabled}
            className="resize-none min-h-[44px] max-h-[200px] pr-12 rounded-xl bg-background border-border focus:border-violet-500/50 focus:ring-violet-500/20"
            rows={1}
          />
          <div className="absolute bottom-2 right-2 flex items-center gap-1">
            {input && (
              <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} className="text-xs text-muted-foreground">
                {input.length}
              </motion.div>
            )}
          </div>
        </div>
        <Button
          onClick={handleSend}
          disabled={!input.trim() || isStreaming || disabled}
          className="h-11 w-11 rounded-xl bg-gradient-to-r from-violet-600 to-purple-600 hover:from-violet-500 hover:to-purple-500 text-white shrink-0"
          size="icon"
        >
          {isStreaming ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Send className="w-4 h-4" />
          )}
        </Button>
      </div>

      <div className="flex items-center justify-center mt-2">
        <p className="text-[10px] text-muted-foreground flex items-center gap-1">
          <Sparkles className="w-2.5 h-2.5" />
          Powered by Z.ai Agent — Web Search, Code Execution, File Ops, Charts, Text Analysis
        </p>
      </div>
    </div>
  );
}
