"use client";

import { useState, useEffect } from "react";
import Sidebar from "@/components/Sidebar";
import ChatInterface from "@/components/ChatInterface";
import DocumentsTab from "@/components/DocumentsTab";
import VectorStoreTab from "@/components/VectorStoreTab";
import SettingsTab from "@/components/SettingsTab";
import { AnimatePresence, motion } from "framer-motion";

export type Tab = "chat" | "documents" | "vector-store" | "settings";

export default function Home() {
  const [activeTab, setActiveTab] = useState<Tab>("chat");
  const [settings, setSettings] = useState({
    chunkSize: 500,
    ragEnabled: true,
  });

  return (
    <div className="flex h-screen overflow-hidden bg-background text-zinc-200">
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} />
      
      <main className="flex-1 flex flex-col relative overflow-hidden">
        <header className="h-16 border-b border-zinc-800 bg-background/50 backdrop-blur-md flex items-center px-8 justify-between z-20">
          <div className="flex items-center gap-3">
            <h1 className="font-bold text-xl tracking-tight text-white capitalize">
              {activeTab.replace("-", " ")}
            </h1>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-zinc-900 border border-zinc-800">
              <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-xs text-zinc-400 font-medium tracking-wide font-mono uppercase">
                Endee Node Active
              </span>
            </div>
          </div>
        </header>

        <div className="flex-1 relative overflow-hidden p-0">
          <AnimatePresence mode="wait">
            {activeTab === "chat" && (
              <motion.div
                key="chat"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                className="h-full"
              >
                <ChatInterface settings={settings} />
              </motion.div>
            )}
            
            {activeTab === "documents" && (
              <motion.div
                key="docs"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                className="h-full p-8"
              >
                <DocumentsTab />
              </motion.div>
            )}

            {activeTab === "vector-store" && (
              <motion.div
                key="vector"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                className="h-full p-8"
              >
                <VectorStoreTab />
              </motion.div>
            )}

            {activeTab === "settings" && (
              <motion.div
                key="settings"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                className="h-full p-8"
              >
                <SettingsTab settings={settings} setSettings={setSettings} />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </main>
    </div>
  );
}
