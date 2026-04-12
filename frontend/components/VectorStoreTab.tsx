"use client";

import { useState, useEffect } from "react";
import { Database, Trash2, ShieldAlert, Cpu, Layers, RefreshCw } from "lucide-react";
import { motion } from "framer-motion";

export default function VectorStoreTab() {
  const [stats, setStats] = useState({ total_vectors: 0 });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchStats();
  }, []);

  const fetchStats = async () => {
    setLoading(true);
    try {
      const res = await fetch("http://localhost:8000/vector-store/stats");
      const data = await res.json();
      setStats(data);
    } catch (error) {
      console.error("Failed to fetch stats", error);
    } finally {
      setLoading(false);
    }
  };

  const clearDB = async () => {
    if (!confirm("Are you sure you want to wipe the entire vector database? This cannot be undone.")) return;
    
    setLoading(true);
    try {
      await fetch("http://localhost:8000/vector-store/clear", { method: "POST" });
      fetchStats();
    } catch (error) {
      console.error("Failed to clear DB", error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <StatCard 
          icon={<Layers className="text-indigo-500" />} 
          title="Total Vectors" 
          value={stats.total_vectors.toLocaleString()} 
        />
        <StatCard 
          icon={<Cpu className="text-pink-500" />} 
          title="Engine Status" 
          value="Healthy" 
        />
        <StatCard 
          icon={<Database className="text-emerald-500" />} 
          title="Index Name" 
          value="pdf_rag_index" 
        />
      </div>

      <div className="bg-zinc-900/30 border border-zinc-800 rounded-2xl overflow-hidden">
        <div className="p-6 border-b border-zinc-800 flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold text-white">Advanced Controls</h3>
            <p className="text-sm text-zinc-500">Manage your vector infrastructure directly</p>
          </div>
          <button 
            onClick={fetchStats}
            disabled={loading}
            className="p-2 hover:bg-zinc-800 rounded-lg text-zinc-400 transition-colors"
          >
            <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
        
        <div className="p-6 space-y-6">
          <div className="flex items-center justify-between p-4 bg-rose-500/5 border border-rose-500/20 rounded-xl">
            <div className="flex gap-4">
              <div className="w-10 h-10 rounded-lg bg-rose-500/10 flex items-center justify-center text-rose-500">
                <ShieldAlert size={20} />
              </div>
              <div>
                <h4 className="text-sm font-bold text-rose-200">Danger Zone: Wipe Index</h4>
                <p className="text-xs text-rose-500/70">Permanently delete all stored embeddings and metadata in Endee.</p>
              </div>
            </div>
            <button 
              onClick={clearDB}
              disabled={loading}
              className="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold rounded-lg transition-all shadow-lg shadow-rose-600/20"
            >
              Clear DB
            </button>
          </div>
        </div>
      </div>

      <div className="space-y-4">
         <h3 className="text-sm font-bold text-zinc-500 uppercase tracking-widest pl-2">Latency Analysis</h3>
         <div className="h-24 bg-zinc-900/50 rounded-xl border border-zinc-800 flex items-center justify-center italic text-zinc-600 text-sm">
           Live performance metrics visualization coming soon...
         </div>
      </div>
    </div>
  );
}

function StatCard({ icon, title, value }: { icon: React.ReactNode, title: string, value: string }) {
  return (
    <div className="p-6 bg-zinc-900/50 border border-zinc-800 rounded-2xl space-y-3">
      <div className="w-10 h-10 rounded-xl bg-zinc-800 flex items-center justify-center">
        {icon}
      </div>
      <div>
        <p className="text-xs font-bold text-zinc-500 uppercase tracking-widest">{title}</p>
        <p className="text-2xl font-bold text-white mt-1">{value}</p>
      </div>
    </div>
  );
}
