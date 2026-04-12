import ReactMarkdown from "react-markdown";
import { User, Sparkles, FileText, ChevronRight } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useState } from "react";

export default function Message({ message }: { message: any }) {
  const isUser = message.role === "user";
  const [showSources, setShowSources] = useState(false);

  if (isUser) {
    return (
      <motion.div initial={{opacity:0,y:10}} animate={{opacity:1,y:0}} className="flex flex-col items-end w-full">
        <div className="bg-zinc-800 text-zinc-200 px-6 py-4 rounded-2xl rounded-tr-sm max-w-[85%] shadow-md border border-zinc-700">
          {message.content}
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div initial={{opacity:0,y:10}} animate={{opacity:1,y:0}} className="flex items-start gap-4 w-full">
      <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-accent to-purple-600 flex items-center justify-center shrink-0 shadow-lg shadow-accent/20">
         <Sparkles className="w-5 h-5 text-white" />
      </div>
      
      <div className="flex-1 space-y-4 max-w-[90%]">
        <div className={`prose prose-invert prose-p:leading-relaxed prose-pre:bg-zinc-900 prose-pre:border prose-pre:border-zinc-800 max-w-none text-zinc-300 ${message.error ? "text-red-400" : ""}`}>
           <ReactMarkdown>{message.content}</ReactMarkdown>
        </div>

        {message.sources && message.sources.length > 0 && (
          <div className="mt-4 pt-4 border-t border-zinc-800/50">
            <button 
              onClick={() => setShowSources(!showSources)}
              className="flex items-center gap-2 text-sm text-zinc-400 hover:text-accent transition-colors font-medium cursor-pointer bg-card px-3 py-1.5 rounded-lg border border-zinc-800 hover:border-accent/40"
            >
              <FileText className="w-4 h-4" />
              {message.sources.length} Sources Investigated
              <motion.div animate={{ rotate: showSources ? 90 : 0 }}>
                 <ChevronRight className="w-4 h-4" />
               </motion.div>
            </button>
            
            <AnimatePresence>
              {showSources && (
                <motion.div 
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="overflow-hidden mt-3"
                >
                  <div className="grid grid-cols-1 gap-3">
                    {message.sources.map((src: any, i: number) => (
                      <motion.div 
                        whileHover={{ scale: 1.01, x: 2 }}
                        key={i} 
                        className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-4 hover:border-accent/50 transition-colors shadow-sm relative group overflow-hidden"
                      >
                         <div className="absolute top-0 left-0 w-1 h-full bg-gradient-to-b from-accent to-purple-500 opacity-0 group-hover:opacity-100 transition-opacity" />
                        <div className="flex justify-between items-start mb-2">
                          <span className="font-semibold text-accent truncate pr-4 text-sm flex items-center gap-2">
                            <span className="w-1.5 h-1.5 rounded-full bg-accent"></span>
                            {src.filename}
                          </span>
                          <span className="text-xs bg-zinc-800 border border-zinc-700 px-2 py-1 rounded-md text-zinc-400 font-mono">
                            Page {src.page}
                          </span>
                        </div>
                        <p className="text-zinc-500 text-sm leading-relaxed line-clamp-3">
                          "{src.text}"
                        </p>
                      </motion.div>
                    ))}
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
