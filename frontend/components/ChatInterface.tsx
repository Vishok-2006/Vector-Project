"use client";

import { useState, useEffect, useRef } from "react";
import { Send, Bot, User, Sparkles, Loader2, FileText, Info } from "lucide-react";
import Message from "./Message";
import { motion, AnimatePresence } from "framer-motion";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  context?: string;
  timestamp?: string;
}

interface ChatInterfaceProps {
  settings: {
    ragEnabled: boolean;
    chunkSize: number;
  };
}

export default function ChatInterface({ settings }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [chatId, setChatId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleSwitch = (e: any) => {
      loadChat(e.detail);
    };
    const handleNew = () => {
      setChatId(null);
      setMessages([]);
    };

    window.addEventListener('switch-chat', handleSwitch);
    window.addEventListener('new-chat', handleNew);
    return () => {
      window.removeEventListener('switch-chat', handleSwitch);
      window.removeEventListener('new-chat', handleNew);
    };
  }, []);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const loadChat = async (id: string) => {
    setLoading(true);
    try {
      const res = await fetch(`http://localhost:8000/chat/${id}`);
      const data = await res.json();
      setChatId(data.chat_id);
      setMessages(data.messages);
    } catch (error) {
      console.error("Failed to load chat", error);
    } finally {
      setLoading(false);
    }
  };

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userMsg: ChatMessage = { role: "user", content: input };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch("http://localhost:8000/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: input,
          chat_id: chatId,
          rag_enabled: settings.ragEnabled
        }),
      });

      const data = await res.json();
      setChatId(data.chat_id);
      
      const assistantMsg: ChatMessage = { 
        role: "assistant", 
        content: data.answer,
        context: data.context 
      };
      setMessages((prev) => [...prev, assistantMsg]);
      
      // Notify sidebar to refresh
      window.dispatchEvent(new Event('chat-updated'));
    } catch (error) {
      setMessages((prev) => [...prev, { role: "assistant", content: "Sorry, I encountered an error." }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-zinc-950 relative">
      <div 
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6 custom-scrollbar"
      >
        {messages.length === 0 && !loading && (
          <div className="flex flex-col items-center justify-center h-full opacity-40">
            <Sparkles size={48} className="text-indigo-500 mb-4" />
            <h2 className="text-2xl font-bold tracking-tight">How can I help you today?</h2>
            <p className="text-zinc-400 mt-2">Ask anything about your documents</p>
          </div>
        )}
        
        {messages.map((msg, i) => (
          <ChatMessageItem key={i} msg={msg} />
        ))}
        
        {loading && (
          <div className="flex items-start gap-4">
            <div className="w-8 h-8 rounded-full bg-indigo-500/20 flex items-center justify-center">
              <Loader2 size={18} className="text-indigo-500 animate-spin" />
            </div>
            <div className="flex-1 bg-zinc-900/50 rounded-2xl p-4 border border-zinc-800 animate-pulse">
               <div className="h-4 bg-zinc-800 rounded w-2/3 mb-2" />
               <div className="h-4 bg-zinc-800 rounded w-1/3" />
            </div>
          </div>
        )}
      </div>

      <div className="p-4 md:p-8 pt-0">
        <div className="max-w-4xl mx-auto relative group">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder="Ask something about your data..."
            className="w-full bg-zinc-900/50 border border-zinc-800 rounded-2xl py-4 pl-6 pr-14 text-zinc-200 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 transition-all resize-none min-h-[60px] max-h-[200px]"
            rows={1}
          />
          <button 
            onClick={handleSend}
            disabled={!input.trim() || loading}
            className="absolute right-3 bottom-3 p-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl transition-all disabled:opacity-50 disabled:bg-zinc-800"
          >
            <Send size={18} />
          </button>
        </div>
        <p className="text-center text-[10px] text-zinc-600 mt-4 uppercase tracking-tighter">
          Powered by Endee Vector DB & Gemini 1.5 Pro
        </p>
      </div>
    </div>
  );
}

function ChatMessageItem({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  const [showDocs, setShowDocs] = useState(false);

  return (
    <motion.div 
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={`flex gap-4 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}
    >
      <div className={`w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center ${isUser ? 'bg-indigo-600' : 'bg-zinc-800 border border-zinc-700'}`}>
        {isUser ? <User size={16} /> : <Bot size={16} />}
      </div>
      <div className={`flex-1 max-w-[85%] space-y-2`}>
        <div className={`p-4 rounded-2xl border ${isUser ? 'bg-indigo-500/10 border-indigo-500/20 text-indigo-50' : 'bg-zinc-900/80 border-zinc-800 text-zinc-300 shadow-sm'}`}>
          <div className="prose prose-invert prose-sm max-w-none whitespace-pre-wrap">
            {msg.content}
          </div>
        </div>
        
        {msg.context && !isUser && (
          <div className="flex flex-col gap-2">
            <button 
              onClick={() => setShowDocs(!showDocs)}
              className="flex items-center gap-1.5 text-[10px] font-bold text-zinc-500 uppercase tracking-widest hover:text-zinc-300 transition-colors pl-2"
            >
              <Info size={12} />
              {showDocs ? 'Hide Sources' : 'View Sources'}
            </button>
            <AnimatePresence>
              {showDocs && (
                <motion.div 
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="overflow-hidden"
                >
                  <div className="bg-zinc-950/50 border border-zinc-800/50 rounded-xl p-3 text-[11px] text-zinc-500 font-mono leading-relaxed whitespace-pre-wrap">
                    {msg.context}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}
      </div>
    </motion.div>
  );
}
