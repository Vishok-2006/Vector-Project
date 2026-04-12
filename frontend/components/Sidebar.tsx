"use client";

import { MessageSquare, FileText, Database, Settings, Trash2, Plus } from "lucide-react";
import { useState, useEffect } from "react";

interface Chat {
  chat_id: string;
  title: string;
  created_at: string;
}

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: any) => void;
}

export default function Sidebar({ activeTab, setActiveTab }: SidebarProps) {
  const [chats, setChats] = useState<Chat[]>([]);

  useEffect(() => {
    fetchChats();
  }, []);

  const fetchChats = async () => {
    try {
      const res = await fetch("http://localhost:8000/chats");
      const data = await res.json();
      setChats(data);
    } catch (error) {
      console.error("Failed to fetch chats", error);
    }
  };

  const deleteChat = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await fetch(`http://localhost:8000/chat/${id}`, { method: "DELETE" });
      fetchChats();
    } catch (error) {
      console.error("Failed to delete chat", error);
    }
  };

  return (
    <aside className="w-72 border-r border-zinc-800 bg-zinc-950 flex flex-col z-30">
      <div className="p-6">
        <div className="flex items-center gap-3 mb-8">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/20">
            <Database className="w-5 h-5 text-white" />
          </div>
          <span className="font-bold tracking-tight text-xl text-white">Vectra</span>
        </div>

        <nav className="space-y-1.5 mb-8">
          <NavItem 
            icon={<MessageSquare size={18} />} 
            text="Chat" 
            active={activeTab === "chat"} 
            onClick={() => setActiveTab("chat")}
          />
          <NavItem 
            icon={<FileText size={18} />} 
            text="Documents" 
            active={activeTab === "documents"} 
            onClick={() => setActiveTab("documents")}
          />
          <NavItem 
            icon={<Database size={18} />} 
            text="Vector Store" 
            active={activeTab === "vector-store"} 
            onClick={() => setActiveTab("vector-store")}
          />
          <NavItem 
            icon={<Settings size={18} />} 
            text="Settings" 
            active={activeTab === "settings"} 
            onClick={() => setActiveTab("settings")}
          />
        </nav>

        {activeTab === "chat" && (
          <div className="mt-4">
            <div className="flex items-center justify-between mb-4">
               <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-widest pl-2">History</h3>
               <button 
                onClick={() => window.dispatchEvent(new CustomEvent('new-chat'))}
                className="p-1 hover:bg-zinc-800 rounded-md transition-colors text-zinc-400 hover:text-white"
                title="New Chat"
               >
                 <Plus size={16} />
               </button>
            </div>
            <div className="space-y-1 max-h-[60vh] overflow-y-auto pr-2 custom-scrollbar">
              {chats.map((chat) => (
                <div 
                  key={chat.chat_id}
                  onClick={() => {
                    setActiveTab("chat");
                    window.dispatchEvent(new CustomEvent('switch-chat', { detail: chat.chat_id }));
                  }}
                  className="group flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-all duration-200 cursor-pointer text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
                >
                  <span className="truncate flex-1">{chat.title}</span>
                  <button 
                    onClick={(e) => deleteChat(chat.chat_id, e)}
                    className="opacity-0 group-hover:opacity-100 p-1 hover:text-red-400 transition-all"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
              {chats.length === 0 && (
                <p className="text-xs text-zinc-600 pl-2">No conversations yet</p>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="mt-auto p-4 border-t border-zinc-900">
        <div className="bg-zinc-900/30 rounded-xl p-4 border border-zinc-800/50">
           <div className="flex items-center gap-2 mb-2">
             <div className="w-1.5 h-1.5 rounded-full bg-indigo-500" />
             <h3 className="text-xs font-semibold text-zinc-300">System Ready</h3>
           </div>
           <p className="text-[10px] text-zinc-500 leading-relaxed font-mono">
             FastAPI + Gemini 1.5 <br />
             Endee Vector Engine
           </p>
        </div>
      </div>
    </aside>
  );
}

function NavItem({ icon, text, active = false, onClick }: { icon: React.ReactNode, text: string, active?: boolean, onClick: () => void }) {
  return (
    <button 
      onClick={onClick}
      className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all duration-300 ${active ? 'bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 font-medium' : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200 border border-transparent'}`}
    >
      {icon}
      {text}
    </button>
  );
}
