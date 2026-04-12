"use client";

import { Sliders, Zap, BookOpen, HardDrive, Info } from "lucide-react";

interface SettingsTabProps {
  settings: {
    chunkSize: number;
    ragEnabled: boolean;
  };
  setSettings: (settings: any) => void;
}

export default function SettingsTab({ settings, setSettings }: SettingsTabProps) {
  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <div className="p-8 bg-zinc-900/30 border border-zinc-800 rounded-2xl space-y-8">
        <section className="space-y-4">
          <div className="flex items-center gap-3 mb-6">
            <Zap className="text-amber-500" size={20} />
            <h3 className="text-lg font-bold text-white">Generation Engine</h3>
          </div>
          
          <div className="flex items-center justify-between p-4 bg-zinc-900/50 rounded-xl border border-zinc-800">
            <div>
              <h4 className="text-sm font-medium text-zinc-200">Retrieval Augmented Generation</h4>
              <p className="text-xs text-zinc-500 mt-1">Ground model responses in your uploaded workspace data.</p>
            </div>
            <button 
              onClick={() => setSettings({ ...settings, ragEnabled: !settings.ragEnabled })}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${settings.ragEnabled ? 'bg-indigo-600' : 'bg-zinc-700'}`}
            >
              <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${settings.ragEnabled ? 'translate-x-6' : 'translate-x-1'}`} />
            </button>
          </div>
        </section>

        <section className="space-y-4">
          <div className="flex items-center gap-3 mb-6">
            <BookOpen className="text-indigo-500" size={20} />
            <h3 className="text-lg font-bold text-white">Embedding Logic</h3>
          </div>
          
          <div className="space-y-6">
            <div className="p-4 bg-zinc-900/50 rounded-xl border border-zinc-800">
              <div className="flex items-center justify-between mb-4">
                <h4 className="text-sm font-medium text-zinc-200">Context Window (Words)</h4>
                <span className="text-xs font-mono text-indigo-400 bg-indigo-500/10 px-2 py-1 rounded">
                  {settings.chunkSize}
                </span>
              </div>
              <input 
                type="range" 
                min="100" 
                max="2000" 
                step="50"
                value={settings.chunkSize}
                onChange={(e) => setSettings({ ...settings, chunkSize: parseInt(e.target.value) })}
                className="w-full h-1.5 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-indigo-500"
              />
              <div className="flex justify-between mt-2 text-[10px] text-zinc-600 font-bold uppercase tracking-widest">
                <span>Atomic</span>
                <span>Verbose</span>
              </div>
            </div>
            
            <div className="flex items-start gap-3 p-4 bg-indigo-500/5 border border-indigo-500/10 rounded-xl">
              <Info size={16} className="text-indigo-400 mt-0.5" />
              <p className="text-xs text-zinc-500 leading-relaxed">
                Higher chunk sizes allow more context per block but might dilute specificity. 
                Changes apply only to future uploads.
              </p>
            </div>
          </div>
        </section>

        <section className="pt-6 border-t border-zinc-800">
           <div className="flex items-center gap-2 text-[10px] font-bold text-zinc-600 uppercase tracking-[0.2em] justify-center">
             <HardDrive size={12} />
             Backend: v1.0.4-stable
           </div>
        </section>
      </div>
    </div>
  );
}
