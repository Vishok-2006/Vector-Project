import { FileText, Database, Webhook, Settings, Sparkles } from "lucide-react";

export default function Sidebar() {
  return (
    <aside className="w-64 border-r border-card bg-card/50 hidden md:flex flex-col">
      <div className="p-6">
        <div className="flex items-center gap-2 mb-8">
           <Sparkles className="w-6 h-6 text-accent" />
           <span className="font-bold tracking-tight text-xl">Vectra</span>
        </div>

        <nav className="space-y-2">
          <NavItem icon={<FileText size={18} />} text="Documents" active />
          <NavItem icon={<Database size={18} />} text="Vector Store" />
          <NavItem icon={<Webhook size={18} />} text="API Keys" />
          <NavItem icon={<Settings size={18} />} text="Settings" />
        </nav>
      </div>

      <div className="mt-auto p-6">
        <div className="bg-zinc-900/50 rounded-xl p-4 border border-zinc-800">
           <h3 className="text-sm font-semibold mb-1">Endpoints Active</h3>
           <p className="text-xs text-zinc-400">Gemini 1.5 Pro</p>
           <p className="text-xs text-zinc-400">Endee Vector DB</p>
        </div>
      </div>
    </aside>
  );
}

function NavItem({ icon, text, active = false }: { icon: React.ReactNode, text: string, active?: boolean }) {
  return (
    <button className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all duration-200 ${active ? 'bg-accent/10 border border-accent/20 text-accent font-medium' : 'text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200 border border-transparent'}`}>
      {icon}
      {text}
    </button>
  )
}
