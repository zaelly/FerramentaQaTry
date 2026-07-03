import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { StatusBadge } from "../components/Badges";
import { api } from "../lib/api";
import type { TestRunListItem } from "../lib/types";

export function HistoryPage() {
  const [runs, setRuns] = useState<TestRunListItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .listTests()
      .then(setRuns)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="max-w-5xl mx-auto px-8 py-10">
      <h1 className="text-2xl font-semibold text-white mb-1">Histórico de testes</h1>
      <p className="text-sm text-slate-400 mb-8">Todas as execuções anteriores do agente.</p>

      {loading && <div className="text-slate-500 text-sm">Carregando...</div>}

      {!loading && runs.length === 0 && (
        <div className="card p-10 text-center text-slate-500">
          Nenhum teste executado ainda.{" "}
          <Link to="/" className="text-accent-400 font-medium">
            Iniciar o primeiro teste
          </Link>
        </div>
      )}

      <div className="space-y-2">
        {runs.map((run) => (
          <Link
            key={run.id}
            to={`/run/${run.id}`}
            className="card flex items-center justify-between px-5 py-4 hover:border-accent-500/40 transition-colors"
          >
            <div className="min-w-0">
              <div className="text-white font-medium truncate">{run.url}</div>
              <div className="text-xs text-slate-500 truncate mt-0.5">{run.goal}</div>
            </div>
            <div className="flex items-center gap-5 shrink-0 ml-4">
              <div className="text-xs text-slate-500">{run.issue_count} problema(s)</div>
              {run.score != null && <div className="text-sm font-semibold text-white">{run.score}/10</div>}
              <StatusBadge status={run.status} />
              <div className="text-xs text-slate-600 w-28 text-right">
                {new Date(run.started_at * 1000).toLocaleString("pt-BR")}
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
