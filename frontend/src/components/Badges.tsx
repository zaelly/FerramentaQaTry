import type { IssueCategory, IssueSeverity, RunStatus } from "../lib/types";

const severityStyles: Record<IssueSeverity, string> = {
  critical: "bg-red-500/15 text-red-400 border-red-500/30",
  major: "bg-orange-500/15 text-orange-400 border-orange-500/30",
  minor: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
  suggestion: "bg-sky-500/15 text-sky-400 border-sky-500/30",
};

const severityLabel: Record<IssueSeverity, string> = {
  critical: "Crítico",
  major: "Grave",
  minor: "Leve",
  suggestion: "Sugestão",
};

export function SeverityBadge({ severity }: { severity: IssueSeverity }) {
  return (
    <span className={`text-[11px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full border ${severityStyles[severity]}`}>
      {severityLabel[severity]}
    </span>
  );
}

const categoryLabel: Record<IssueCategory, string> = {
  functional: "Funcional",
  ui_ux: "UI/UX",
  performance: "Performance",
  accessibility: "Acessibilidade",
};

export function CategoryBadge({ category }: { category: IssueCategory }) {
  return (
    <span className="text-[11px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full border border-base-600 bg-base-800 text-slate-300">
      {categoryLabel[category]}
    </span>
  );
}

const statusStyles: Record<RunStatus, string> = {
  queued: "bg-slate-500/15 text-slate-300 border-slate-500/30",
  running: "bg-accent-500/15 text-accent-400 border-accent-500/30 animate-pulse",
  completed: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  failed: "bg-red-500/15 text-red-400 border-red-500/30",
  stopped: "bg-slate-500/15 text-slate-300 border-slate-500/30",
};

const statusLabel: Record<RunStatus, string> = {
  queued: "Na fila",
  running: "Executando",
  completed: "Concluído",
  failed: "Falhou",
  stopped: "Interrompido",
};

export function StatusBadge({ status }: { status: RunStatus }) {
  return (
    <span className={`text-xs font-semibold px-2.5 py-1 rounded-full border ${statusStyles[status]}`}>
      {statusLabel[status]}
    </span>
  );
}
