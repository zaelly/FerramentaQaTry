import { NavLink } from "react-router-dom";

const navItemClass = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-medium transition-colors ${
    isActive ? "bg-accent-500/15 text-accent-400" : "text-slate-400 hover:text-slate-200 hover:bg-base-800"
  }`;

export function Sidebar() {
  return (
    <aside className="w-64 shrink-0 border-r border-base-700 bg-base-900 flex flex-col p-4">
      <div className="flex items-center gap-2.5 px-2 py-3 mb-4">
        <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-accent-400 to-accent-600 flex items-center justify-center text-white font-bold text-sm">
          QA
        </div>
        <div>
          <div className="text-sm font-semibold text-white leading-tight">QA Agent</div>
          <div className="text-[11px] text-slate-500 leading-tight">testes com IA</div>
        </div>
      </div>

      <nav className="flex flex-col gap-1">
        <NavLink to="/" end className={navItemClass}>
          Novo teste
        </NavLink>
        <NavLink to="/history" className={navItemClass}>
          Histórico
        </NavLink>
        <NavLink to="/settings" className={navItemClass}>
          Configurações
        </NavLink>
      </nav>

      <div className="mt-auto text-[11px] text-slate-600 px-2 pt-4 border-t border-base-800">
        Motor de IA: Groq (compatível OpenAI)
      </div>
    </aside>
  );
}
