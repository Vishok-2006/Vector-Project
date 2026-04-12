"use client";

import { useState } from "react";
import Sidebar from "@/components/Sidebar";
import Chat from "@/components/Chat";
import Upload from "@/components/Upload";
import { motion, AnimatePresence } from "framer-motion";

export default function Home() {
  const [hasIndexedFiles, setHasIndexedFiles] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar />
      <main className="flex-1 flex flex-col relative w-full h-full">
        <header className="h-16 border-b border-card bg-background/50 backdrop-blur flex items-center px-6 justify-between flex-shrink-0 z-10">
          <h1 className="font-bold tracking-tight text-lg text-transparent bg-clip-text bg-gradient-to-r from-accent to-purple-400">
            Agentic RAG Assistant
          </h1>
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-xs text-zinc-400 font-medium tracking-wide">Endee Live</span>
          </div>
        </header>

        <div className="flex-1 flex items-center justify-center p-6 relative overflow-hidden">
          <AnimatePresence mode="wait">
            {!hasIndexedFiles ? (
              <motion.div
                key="upload"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className="max-w-2xl w-full"
              >
                <div className="text-center mb-10 space-y-4">
                  <h2 className="text-4xl font-bold tracking-tight">Construct Your Knowledge Base.</h2>
                  <p className="text-zinc-400 text-lg">
                    Upload PDFs, allow the Python backend to embed and vectorize them into Endee,
                    and perform hyper-accurate targeted queries with Gemini 1.5 Pro.
                  </p>
                </div>
                <div className="bg-card/50 backdrop-blur-xl border border-zinc-800 rounded-2xl p-2 shadow-2xl hover:shadow-accent/5 transition-all duration-500">
                  <Upload onUploadComplete={() => setHasIndexedFiles(true)} />
                </div>
              </motion.div>
            ) : (
              <motion.div
                key="chat"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="w-full max-w-5xl h-[85vh] bg-card/30 backdrop-blur rounded-2xl border border-zinc-800/50 shadow-2xl flex flex-col overflow-hidden"
              >
                <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800/50 bg-card/50">
                  <span className="text-sm font-medium text-zinc-300">Active Session</span>
                  <button
                    onClick={() => setHasIndexedFiles(false)}
                    className="text-xs text-zinc-500 hover:text-accent transition-colors"
                  >
                    + Add More Documents
                  </button>
                </div>
                <Chat />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </main>
    </div>
  );
}
