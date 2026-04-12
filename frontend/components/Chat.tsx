import { useState, useRef, useEffect } from "react";
import MessageComponent from "./Message";
import { Send, Loader2, Sparkles } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

type Message = { role: string; content: string; sources?: any[]; error?: boolean };

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const question = input.trim();
    setInput("");
    
    setMessages(prev => [...prev, { role: "user", content: question }]);
    setLoading(true);

    try {
      const history = messages.map(m => ({ role: m.role, content: m.content }));
      
      const res = await fetch("http://127.0.0.1:8000/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: question, history }),
      });

      if (!res.ok) throw new Error("Failed to get answer");
      const data = await res.json();

      setMessages(prev => [...prev, { 
         role: "assistant", 
         content: data.answer,
         sources: data.sources 
      }]);

    } catch (err: any) {
      setMessages(prev => [...prev, { role: "assistant", content: err.message, error: true }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-background/50">
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        <AnimatePresence>
          {messages.length === 0 ? (
            <motion.div initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} className="h-full flex flex-col items-center justify-center text-zinc-500 space-y-4">
              <div className="w-16 h-16 rounded-full bg-card border border-zinc-800 flex items-center justify-center shadow-lg">
                 <Sparkles className="w-8 h-8 text-accent" />
              </div>
              <p className="text-lg">What would you like to know about your documents?</p>
            </motion.div>
          ) : (
            messages.map((m, i) => (
              <MessageComponent key={i} message={m} />
            ))
          )}
        </AnimatePresence>
        
        {loading && (
          <motion.div initial={{opacity:0,y:10}} animate={{opacity:1,y:0}} className="flex items-center gap-4">
             <div className="w-10 h-10 rounded-xl bg-card border border-zinc-800 flex items-center justify-center shrink-0">
                <Sparkles className="w-5 h-5 text-accent animate-pulse" />
             </div>
             <Loader2 className="w-5 h-5 text-zinc-500 animate-spin" />
             <span className="text-zinc-500 text-sm">Agent is thinking...</span>
          </motion.div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="p-4 bg-card/80 border-t border-zinc-800/50 backdrop-blur-sm">
        <form onSubmit={handleSubmit} className="relative max-w-4xl mx-auto flex gap-3">
          <input
            autoFocus
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={loading}
            placeholder="Ask a question..."
            className="flex-1 bg-background border border-zinc-700/50 rounded-2xl px-5 py-4 text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent transition-all shadow-inner disabled:opacity-50 text-base"
          />
          <button
            type="submit"
            disabled={!input.trim() || loading}
            className="bg-accent hover:bg-accent/90 text-white rounded-2xl px-6 flex items-center justify-center font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-accent/20"
          >
            <Send className="w-5 h-5" />
          </button>
        </form>
      </div>
    </div>
  );
}
