import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { CategoryBadge, SeverityBadge, StatusBadge } from "../components/Badges";
import { api } from "../lib/api";
import type { Issue, RunStatus, Step, SuggestionItem, TestRun } from "../lib/types";

export function RunPage() {
  const { id } = useParams<{ id: string }>();
  const [run, setRun] = useState<TestRun | null>(null);
  const [status, setStatus] = useState<RunStatus>("queued");
  const [activeTab, setActiveTab] = useState<"timeline" | "issues" | "report">("timeline");
  const stepsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;

    api
      .getTest(id)
      .then((r) => {
        if (!cancelled) {
          setRun(r);
          setStatus(r.status);
        }
      })
      .catch(() => {});

    const ws = api.streamTest(id, (event) => {
      if (event.type === "snapshot") {
        setRun(event.run);
        setStatus(event.run.status);
      } else if (event.type === "status") {
        setStatus(event.status);
      } else if (event.type === "step") {
        setRun((prev) => (prev ? { ...prev, steps: [...prev.steps, event.step as Step] } : prev));
      } else if (event.type === "issue") {
        setRun((prev) => (prev ? { ...prev, issues: [...prev.issues, event.issue as Issue] } : prev));
      } else if (event.type === "finished") {
        setStatus(event.status);
        api.getTest(id).then((r) => !cancelled && setRun(r));
      }
    });

    return () => {
      cancelled = true;
      ws.close();
    };
  }, [id]);

  useEffect(() => {
    stepsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [run?.steps.length]);

  if (!run) {
    return <div className="p-10 text-slate-400">Carregando execução...</div>;
  }

  const lastScreenshot = [...run.steps].reverse().find((s) => s.screenshot)?.screenshot;
  const isLive = status === "running" || status === "queued";

  return (
    <div className="max-w-6xl mx-auto px-8 py-8">
      <div className="flex items-start justify-between mb-6">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold text-white">{run.url}</h1>
            <StatusBadge status={status} />
          </div>
          <p className="text-sm text-slate-400 mt-1 max-w-xl">{run.goal}</p>
        </div>
        {run.summary?.score != null && (
          <div className="text-right">
            <div className="text-3xl font-bold text-white">{run.summary.score}/10</div>
            <div className="text-xs text-slate-500">nota geral</div>
          </div>
        )}
      </div>

      <div className="grid grid-cols-5 gap-6">
        <div className="col-span-2">
          <div className="card p-3 sticky top-8">
            <div className="text-xs font-medium text-slate-400 mb-2 px-1">
              {isLive ? "Tela atual" : "Última captura"}
            </div>
            {lastScreenshot ? (
              <img
                src={api.screenshotUrl(lastScreenshot)}
                className="rounded-xl w-full border border-base-700"
                alt="captura de tela"
              />
            ) : (
              <div className="aspect-video rounded-xl bg-base-900 flex items-center justify-center text-slate-600 text-sm">
                Aguardando primeira captura...
              </div>
            )}
          </div>
        </div>

        <div className="col-span-3">
          <div className="flex gap-2 mb-4">
            <TabButton active={activeTab === "timeline"} onClick={() => setActiveTab("timeline")}>
              Linha do tempo ({run.steps.length})
            </TabButton>
            <TabButton active={activeTab === "issues"} onClick={() => setActiveTab("issues")}>
              Problemas ({run.issues.length})
            </TabButton>
            <TabButton active={activeTab === "report"} onClick={() => setActiveTab("report")}>
              Relatório
            </TabButton>
          </div>

          {activeTab === "timeline" && (
            <div className="card p-4 max-h-[70vh] overflow-y-auto space-y-2">
              {run.steps.map((step, i) => (
                <StepRow key={i} step={step} />
              ))}
              {isLive && (
                <div className="flex items-center gap-2 text-sm text-slate-500 px-2 py-2">
                  <span className="h-2 w-2 rounded-full bg-accent-500 animate-pulse" /> agente pensando...
                </div>
              )}
              <div ref={stepsEndRef} />
            </div>
          )}

          {activeTab === "issues" && (
            <div className="space-y-3 max-h-[70vh] overflow-y-auto">
              {run.issues.length === 0 && (
                <div className="card p-6 text-center text-slate-500 text-sm">
                  Nenhum problema encontrado até agora.
                </div>
              )}
              {run.issues.map((issue) => (
                <IssueCard key={issue.id} issue={issue} />
              ))}
            </div>
          )}

          {activeTab === "report" && (
            <div className="card p-6">
              {status === "running" || status === "queued" ? (
                <div className="text-slate-500 text-sm">O relatório será gerado quando o teste terminar.</div>
              ) : (
                <>
                  <h3 className="text-white font-semibold mb-2">Avaliação geral</h3>
                  <p className="text-sm text-slate-300 mb-5">{run.summary.overall_assessment}</p>

                  <div className="grid grid-cols-2 gap-6">
                    <SuggestionList title="Sugestões funcionais" items={run.summary.functional_suggestions} />
                    <SuggestionList title="Sugestões de UI/UX" items={run.summary.ui_ux_suggestions} />
                    <SuggestionList title="Sugestões de SEO" items={run.summary.seo_suggestions} />
                    <SuggestionList title="Sugestões de segurança" items={run.summary.security_suggestions} />
                  </div>

                  {Object.keys(run.performance_metrics).length > 0 && (
                    <div className="mt-6">
                      <h4 className="text-sm font-semibold text-slate-200 mb-2">Performance de carregamento</h4>
                      <div className="space-y-1.5">
                        {Object.entries(run.performance_metrics).map(([url, m]) => (
                          <div key={url} className="text-xs text-slate-400 flex gap-4">
                            <span className="truncate max-w-xs" title={url}>
                              {url}
                            </span>
                            <span>
                              {m.loadTime != null ? `${(m.loadTime / 1000).toFixed(1)}s` : "n/d"}
                            </span>
                            <span>{m.resourceCount ?? "n/d"} requisições</span>
                            <span>{((m.transferSize ?? 0) / (1024 * 1024)).toFixed(1)}MB</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="flex items-center gap-3 mt-6">
                    {run.report_html_path && (
                      <a
                        href={api.reportUrl(run.report_html_path)}
                        target="_blank"
                        rel="noreferrer"
                        className="btn-secondary inline-block text-sm"
                      >
                        Abrir relatório completo (HTML) ↗
                      </a>
                    )}
                  </div>

                  <SendEmailSection runId={run.id} />
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const MAX_RECIPIENTS = 10;

function parseRecipients(raw: string): string[] {
  return Array.from(
    new Set(
      raw
        .split(/[,;\n]/)
        .map((s) => s.trim())
        .filter(Boolean)
    )
  );
}

function SendEmailSection({ runId }: { runId: string }) {
  const [open, setOpen] = useState(false);
  const [recipientsText, setRecipientsText] = useState("");
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  const recipients = parseRecipients(recipientsText);
  const tooMany = recipients.length > MAX_RECIPIENTS;

  async function handleSend() {
    setResult(null);
    if (recipients.length === 0) {
      setResult({ ok: false, text: "Informe pelo menos um destinatário." });
      return;
    }
    if (tooMany) {
      setResult({ ok: false, text: `No máximo ${MAX_RECIPIENTS} destinatários por envio.` });
      return;
    }
    setSending(true);
    try {
      const res = await api.sendReportEmail(runId, recipients, message || undefined);
      if (res.ok) {
        setResult({ ok: true, text: `Relatório enviado para ${recipients.length} destinatário(s).` });
      } else {
        setResult({ ok: false, text: res.error || "Falha ao enviar." });
      }
    } catch (err: any) {
      setResult({ ok: false, text: err.message || "Falha ao enviar." });
    } finally {
      setSending(false);
    }
  }

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className="btn-secondary text-sm mt-3">
        Enviar por e-mail
      </button>
    );
  }

  return (
    <div className="card p-5 mt-4">
      <h4 className="text-white font-semibold mb-1">Enviar relatório por e-mail</h4>
      <p className="text-xs text-slate-500 mb-3">
        Até {MAX_RECIPIENTS} destinatários, separados por vírgula ou uma linha por e-mail.
      </p>
      <textarea
        className="input min-h-[70px] resize-y"
        placeholder="ana@empresa.com, joao@empresa.com..."
        value={recipientsText}
        onChange={(e) => setRecipientsText(e.target.value)}
      />
      <div className={`text-xs mt-1 ${tooMany ? "text-red-400" : "text-slate-500"}`}>
        {recipients.length}/{MAX_RECIPIENTS} destinatários
      </div>

      <textarea
        className="input min-h-[60px] resize-y mt-3"
        placeholder="Mensagem opcional para incluir no topo do e-mail..."
        value={message}
        onChange={(e) => setMessage(e.target.value)}
      />

      {result && (
        <div className={`text-sm mt-3 ${result.ok ? "text-emerald-400" : "text-red-400"}`}>{result.text}</div>
      )}

      <div className="flex gap-3 mt-4">
        <button onClick={handleSend} disabled={sending} className="btn-primary text-sm">
          {sending ? "Enviando..." : "Enviar"}
        </button>
        <button onClick={() => setOpen(false)} className="btn-secondary text-sm">
          Cancelar
        </button>
      </div>
    </div>
  );
}

function SuggestionList({ title, items }: { title: string; items: SuggestionItem[] }) {
  return (
    <div>
      <h4 className="text-sm font-semibold text-slate-200 mb-2">{title}</h4>
      {items.length === 0 && <div className="text-sm text-slate-500">Nenhuma sugestão.</div>}
      <div className="space-y-3">
        {items.map((s, i) => (
          <div key={i} className="text-sm text-slate-400 border-l-2 border-base-700 pl-3">
            <div>{s.text}</div>
            {s.url && (
              <div className="text-xs text-slate-500 mt-1 truncate" title={s.url}>
                URL: {s.url}
              </div>
            )}
            {s.screenshot && (
              <img
                src={api.screenshotUrl(s.screenshot)}
                className="mt-2 rounded-lg border border-base-700 max-w-xs"
                alt="onde aplicar a sugestão"
              />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`px-3.5 py-2 rounded-lg text-sm font-medium transition-colors ${
        active ? "bg-accent-500/15 text-accent-400" : "text-slate-400 hover:bg-base-800"
      }`}
    >
      {children}
    </button>
  );
}

function StepRow({ step }: { step: Step }) {
  return (
    <div className={`flex items-start gap-3 px-2 py-2 rounded-lg ${!step.ok ? "bg-red-500/5" : ""}`}>
      <div className="text-[11px] text-slate-600 w-6 pt-0.5 text-right shrink-0">{step.index}</div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono font-semibold text-accent-400">{step.action}</span>
          {step.target && <span className="text-xs text-slate-500">alvo #{step.target}</span>}
          {step.provider && (
            <span className="text-[10px] px-1.5 py-0.5 rounded border border-base-600 text-slate-500">
              via {step.provider}
            </span>
          )}
          {!step.ok && <span className="text-xs text-red-400">erro</span>}
        </div>
        {step.thought && <div className="text-sm text-slate-300 mt-0.5">{step.thought}</div>}
        {step.error && <div className="text-xs text-red-400 mt-0.5">{step.error}</div>}
      </div>
    </div>
  );
}

function IssueCard({ issue }: { issue: Issue }) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-2 mb-2">
        <SeverityBadge severity={issue.severity} />
        <CategoryBadge category={issue.category} />
      </div>
      <h4 className="text-white font-medium">{issue.title}</h4>
      {issue.url && (
        <div className="text-xs text-slate-500 mt-1 truncate" title={issue.url}>
          URL: {issue.url}
        </div>
      )}
      <p className="text-sm text-slate-400 mt-2">{issue.description}</p>
      {issue.recommendation && (
        <p className="text-sm text-emerald-400/90 mt-2">
          <span className="font-medium">Sugestão: </span>
          {issue.recommendation}
        </p>
      )}
      {issue.path_summary && (
        <pre className="text-xs text-slate-500 mt-3 bg-base-900 border border-base-700 rounded-lg p-3 whitespace-pre-wrap font-mono">
          {issue.path_summary}
        </pre>
      )}
      {issue.screenshot && (
        <img
          src={api.screenshotUrl(issue.screenshot)}
          className="mt-3 rounded-lg border border-base-700 max-w-md"
          alt="evidência do problema"
        />
      )}
    </div>
  );
}
