import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";

export function NewTestPage() {
  const navigate = useNavigate();
  const [url, setUrl] = useState("");
  const [goal, setGoal] = useState(
    "Explore o site como um usuário real: navegue pelas principais páginas, teste formulários e botões, e identifique qualquer problema de funcionamento ou de usabilidade."
  );
  const [showCreds, setShowCreds] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [maxSteps, setMaxSteps] = useState(25);
  const [headless, setHeadless] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [configured, setConfigured] = useState(true);

  useEffect(() => {
    api
      .listProviders()
      .then((providers) => setConfigured(providers.some((p) => p.enabled)))
      .catch(() => setConfigured(false));
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!url.trim()) {
      setError("Informe a URL que o agente deve testar.");
      return;
    }
    setLoading(true);
    try {
      const { run_id } = await api.startTest({
        url: url.trim(),
        goal: goal.trim(),
        username: username || undefined,
        password: password || undefined,
        max_steps: maxSteps,
        headless,
      });
      navigate(`/run/${run_id}`);
    } catch (err: any) {
      setError(err.message || "Não foi possível iniciar o teste.");
      setLoading(false);
    }
  }

  return (
    <div className="max-w-3xl mx-auto px-8 py-10">
      <h1 className="text-2xl font-semibold text-white mb-1">Novo teste automatizado</h1>
      <p className="text-sm text-slate-400 mb-8">
        O agente vai navegar pela sua aplicação como um usuário real, testar funcionalidades, tirar prints
        de qualquer erro encontrado e gerar um relatório com sugestões de melhoria.
      </p>

      {!configured && (
        <div className="card p-4 mb-6 border-yellow-500/30 bg-yellow-500/10 text-yellow-300 text-sm">
          Nenhum provedor de IA ativo (Groq, Ollama local, etc).{" "}
          <a href="#/settings" className="underline font-medium">
            Configure agora
          </a>{" "}
          antes de rodar um teste.
        </div>
      )}

      <form onSubmit={handleSubmit} className="card p-6 space-y-5">
        <div>
          <label className="label">URL da aplicação</label>
          <input
            className="input"
            placeholder="https://minhaaplicacao.com"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            required
          />
        </div>

        <div>
          <label className="label">O que o agente deve testar</label>
          <textarea
            className="input min-h-[96px] resize-y"
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
          />
        </div>

        <div>
          <button
            type="button"
            onClick={() => setShowCreds((v) => !v)}
            className="text-sm text-accent-400 hover:text-accent-500 font-medium flex items-center gap-1.5"
          >
            {showCreds ? "▾" : "▸"} Credenciais de login (opcional)
          </button>
          {showCreds && (
            <div className="grid grid-cols-2 gap-4 mt-3">
              <div>
                <label className="label">Usuário / e-mail</label>
                <input className="input" value={username} onChange={(e) => setUsername(e.target.value)} />
              </div>
              <div>
                <label className="label">Senha</label>
                <input
                  className="input"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
            </div>
          )}
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label">Máximo de passos</label>
            <input
              className="input"
              type="number"
              min={5}
              max={80}
              value={maxSteps}
              onChange={(e) => setMaxSteps(Number(e.target.value))}
            />
          </div>
          <div className="flex items-end pb-1">
            <label className="flex items-center gap-2.5 text-sm text-slate-300">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-base-600 bg-base-900 accent-accent-500"
                checked={headless}
                onChange={(e) => setHeadless(e.target.checked)}
              />
              Rodar em segundo plano (headless)
            </label>
          </div>
        </div>

        {error && <div className="text-sm text-red-400">{error}</div>}

        <button type="submit" className="btn-primary w-full" disabled={loading}>
          {loading ? "Iniciando..." : "Iniciar teste"}
        </button>
      </form>
    </div>
  );
}
