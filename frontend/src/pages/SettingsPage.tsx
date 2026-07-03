import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { Provider, ProviderPreset, SmtpConfig } from "../lib/types";

type PresetKey = string;

interface FormState {
  preset: PresetKey;
  name: string;
  base_url: string;
  api_key: string;
  vision_model: string;
  text_model: string;
}

const EMPTY_FORM: FormState = {
  preset: "groq",
  name: "",
  base_url: "",
  api_key: "",
  vision_model: "",
  text_model: "",
};

export function SettingsPage() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [presets, setPresets] = useState<Record<string, ProviderPreset>>({});
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null); // null = closed, "new" = creating
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [error, setError] = useState("");

  function load() {
    Promise.all([api.listProviders(), api.providerPresets()]).then(([p, presetList]) => {
      setProviders(p);
      setPresets(presetList);
      setLoading(false);
    });
  }

  useEffect(() => {
    load();
  }, []);

  function openNewForm() {
    const firstPreset = Object.keys(presets)[0] || "groq";
    const preset = presets[firstPreset];
    setForm({
      preset: firstPreset,
      name: preset?.name || "",
      base_url: preset?.base_url || "",
      api_key: "",
      vision_model: preset?.vision_model || "",
      text_model: preset?.text_model || "",
    });
    setEditingId("new");
    setError("");
  }

  function openEditForm(p: Provider) {
    setForm({
      preset: "custom",
      name: p.name,
      base_url: p.base_url,
      api_key: "",
      vision_model: p.vision_model,
      text_model: p.text_model,
    });
    setEditingId(p.id);
    setError("");
  }

  function applyPreset(key: string) {
    const preset = presets[key];
    setForm((f) => ({
      ...f,
      preset: key,
      name: preset?.name || f.name,
      base_url: preset?.base_url ?? f.base_url,
      vision_model: preset?.vision_model || f.vision_model,
      text_model: preset?.text_model || f.text_model,
    }));
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!form.name.trim() || !form.base_url.trim() || !form.vision_model.trim() || !form.text_model.trim()) {
      setError("Preencha nome, URL base, modelo de visão e modelo de texto.");
      return;
    }
    try {
      if (editingId === "new") {
        const updated = await api.addProvider({
          name: form.name.trim(),
          base_url: form.base_url.trim(),
          api_key: form.api_key || undefined,
          vision_model: form.vision_model.trim(),
          text_model: form.text_model.trim(),
          enabled: true,
        });
        setProviders(updated);
      } else if (editingId) {
        const patch: Record<string, unknown> = {
          name: form.name.trim(),
          base_url: form.base_url.trim(),
          vision_model: form.vision_model.trim(),
          text_model: form.text_model.trim(),
        };
        if (form.api_key) patch.api_key = form.api_key;
        const updated = await api.patchProvider(editingId, patch);
        setProviders(updated);
      }
      setEditingId(null);
    } catch (err: any) {
      setError(err.message || "Não foi possível salvar o provedor.");
    }
  }

  async function toggleEnabled(p: Provider) {
    const updated = await api.patchProvider(p.id, { enabled: !p.enabled });
    setProviders(updated);
  }

  async function remove(p: Provider) {
    if (!confirm(`Remover o provedor "${p.name}"?`)) return;
    const updated = await api.deleteProvider(p.id);
    setProviders(updated);
  }

  async function move(index: number, direction: -1 | 1) {
    const next = [...providers];
    const target = index + direction;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    setProviders(next);
    await api.reorderProviders(next.map((p) => p.id));
  }

  if (loading) return <div className="p-10 text-slate-400">Carregando...</div>;

  return (
    <div className="max-w-3xl mx-auto px-8 py-10">
      <h1 className="text-2xl font-semibold text-white mb-1">Provedores de IA</h1>
      <p className="text-sm text-slate-400 mb-8">
        Configure um ou mais provedores compatíveis com a API da OpenAI — Groq, um Ollama rodando na
        sua máquina, ou qualquer outro serviço. A ordem da lista é a ordem de tentativa: se o primeiro
        falhar ou estourar limite de uso, o agente tenta automaticamente o próximo.
      </p>

      {providers.length === 0 && (
        <div className="card p-6 text-center text-slate-500 text-sm mb-6">
          Nenhum provedor configurado ainda. Adicione um para poder rodar testes.
        </div>
      )}

      <div className="space-y-3 mb-6">
        {providers.map((p, i) => (
          <div key={p.id} className="card p-4 flex items-start gap-4">
            <div className="flex flex-col gap-1 pt-1">
              <button
                onClick={() => move(i, -1)}
                disabled={i === 0}
                className="text-slate-500 hover:text-slate-200 disabled:opacity-20 text-xs leading-none"
                title="Mover para cima (maior prioridade)"
              >
                ▲
              </button>
              <span className="text-[11px] text-slate-600 text-center">{i + 1}</span>
              <button
                onClick={() => move(i, 1)}
                disabled={i === providers.length - 1}
                className="text-slate-500 hover:text-slate-200 disabled:opacity-20 text-xs leading-none"
                title="Mover para baixo (menor prioridade)"
              >
                ▼
              </button>
            </div>

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-white font-medium">{p.name}</span>
                {!p.enabled && (
                  <span className="text-[11px] px-2 py-0.5 rounded-full border border-slate-600 text-slate-400">
                    desativado
                  </span>
                )}
              </div>
              <div className="text-xs text-slate-500 mt-0.5 truncate">{p.base_url}</div>
              <div className="text-xs text-slate-400 mt-1.5 flex gap-4">
                <span>Visão: {p.vision_model}</span>
                <span>Texto: {p.text_model}</span>
              </div>
              <div className="text-xs text-slate-500 mt-1">
                {p.has_api_key ? `Chave: ${p.api_key}` : "Sem chave de API"}
              </div>
            </div>

            <div className="flex items-center gap-3 shrink-0">
              <button
                onClick={() => toggleEnabled(p)}
                className={`relative w-10 h-5 rounded-full transition-colors ${p.enabled ? "bg-accent-500" : "bg-base-700"}`}
                title={p.enabled ? "Desativar" : "Ativar"}
              >
                <span
                  className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform ${p.enabled ? "translate-x-5" : "translate-x-0.5"}`}
                />
              </button>
              <button onClick={() => openEditForm(p)} className="text-xs text-accent-400 hover:text-accent-500 font-medium">
                Editar
              </button>
              <button onClick={() => remove(p)} className="text-xs text-red-400 hover:text-red-500 font-medium">
                Remover
              </button>
            </div>
          </div>
        ))}
      </div>

      {editingId === null && (
        <button onClick={openNewForm} className="btn-secondary text-sm">
          + Adicionar provedor
        </button>
      )}

      {editingId !== null && (
        <form onSubmit={handleSave} className="card p-6 space-y-4 mt-2">
          <h3 className="text-white font-semibold">
            {editingId === "new" ? "Novo provedor" : "Editar provedor"}
          </h3>

          {editingId === "new" && (
            <div>
              <label className="label">Tipo</label>
              <div className="flex gap-2">
                {Object.entries(presets).map(([key, preset]) => (
                  <button
                    type="button"
                    key={key}
                    onClick={() => applyPreset(key)}
                    className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
                      form.preset === key
                        ? "bg-accent-500/15 border-accent-500/40 text-accent-400"
                        : "border-base-700 text-slate-400 hover:bg-base-800"
                    }`}
                  >
                    {preset.name}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div>
            <label className="label">Nome</label>
            <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>

          <div>
            <label className="label">URL base (compatível com a API da OpenAI)</label>
            <input
              className="input"
              placeholder="http://localhost:11434/v1"
              value={form.base_url}
              onChange={(e) => setForm({ ...form, base_url: e.target.value })}
            />
          </div>

          <div>
            <label className="label">Chave de API {presets[form.preset]?.needs_api_key === false && "(opcional para Ollama local)"}</label>
            <input
              className="input"
              type="password"
              placeholder={editingId !== "new" ? "Deixe em branco para manter a atual" : "gsk_... (ou vazio se não precisar)"}
              value={form.api_key}
              onChange={(e) => setForm({ ...form, api_key: e.target.value })}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">Modelo de visão</label>
              <input
                className="input"
                value={form.vision_model}
                onChange={(e) => setForm({ ...form, vision_model: e.target.value })}
              />
            </div>
            <div>
              <label className="label">Modelo de texto</label>
              <input
                className="input"
                value={form.text_model}
                onChange={(e) => setForm({ ...form, text_model: e.target.value })}
              />
            </div>
          </div>

          {error && <div className="text-sm text-red-400">{error}</div>}

          <div className="flex gap-3">
            <button type="submit" className="btn-primary">
              Salvar
            </button>
            <button type="button" onClick={() => setEditingId(null)} className="btn-secondary">
              Cancelar
            </button>
          </div>
        </form>
      )}

      <SmtpSection />
    </div>
  );
}

const EMPTY_SMTP: SmtpConfig = {
  host: "",
  port: 587,
  encryption: "starttls",
  username: "",
  password: "",
  has_password: false,
  from_email: "",
  from_name: "QA Agent",
  configured: false,
};

function SmtpSection() {
  const [smtp, setSmtp] = useState<SmtpConfig>(EMPTY_SMTP);
  const [passwordInput, setPasswordInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .getSmtpConfig()
      .then(setSmtp)
      .finally(() => setLoading(false));
  }, []);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setSaved(false);
    setSaving(true);
    try {
      const updated = await api.patchSmtpConfig({
        host: smtp.host.trim(),
        port: smtp.port,
        encryption: smtp.encryption,
        username: smtp.username.trim(),
        from_email: smtp.from_email.trim(),
        from_name: smtp.from_name.trim(),
        ...(passwordInput ? { password: passwordInput } : {}),
      });
      setSmtp(updated);
      setPasswordInput("");
      setSaved(true);
    } catch (err: any) {
      setError(err.message || "Não foi possível salvar as configurações de e-mail.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return null;

  return (
    <div className="mt-10">
      <h2 className="text-xl font-semibold text-white mb-1">E-mail (envio de relatórios)</h2>
      <p className="text-sm text-slate-400 mb-4">
        Configure um servidor SMTP para poder enviar relatórios por e-mail (até 10 destinatários por
        envio) direto da tela de resultados. Para Gmail, use <code>smtp.gmail.com</code>, porta 587,
        STARTTLS, e uma{" "}
        <a
          href="https://myaccount.google.com/apppasswords"
          target="_blank"
          rel="noreferrer"
          className="text-accent-400 underline"
        >
          senha de app
        </a>{" "}
        (não a senha normal da conta).
      </p>

      <form onSubmit={handleSave} className="card p-6 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label">Servidor SMTP</label>
            <input
              className="input"
              placeholder="smtp.gmail.com"
              value={smtp.host}
              onChange={(e) => setSmtp({ ...smtp, host: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Porta</label>
            <input
              className="input"
              type="number"
              value={smtp.port}
              onChange={(e) => setSmtp({ ...smtp, port: Number(e.target.value) })}
            />
          </div>
        </div>

        <div>
          <label className="label">Criptografia</label>
          <div className="flex gap-2">
            {(["starttls", "ssl", "none"] as const).map((opt) => (
              <button
                type="button"
                key={opt}
                onClick={() => setSmtp({ ...smtp, encryption: opt })}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
                  smtp.encryption === opt
                    ? "bg-accent-500/15 border-accent-500/40 text-accent-400"
                    : "border-base-700 text-slate-400 hover:bg-base-800"
                }`}
              >
                {opt === "starttls" ? "STARTTLS (587)" : opt === "ssl" ? "SSL/TLS (465)" : "Nenhuma"}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label">Usuário</label>
            <input
              className="input"
              placeholder="seu@gmail.com"
              value={smtp.username}
              onChange={(e) => setSmtp({ ...smtp, username: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Senha</label>
            <input
              className="input"
              type="password"
              placeholder={smtp.has_password ? "Deixe em branco para manter a atual" : "senha de app"}
              value={passwordInput}
              onChange={(e) => setPasswordInput(e.target.value)}
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label">E-mail remetente</label>
            <input
              className="input"
              placeholder="seu@gmail.com"
              value={smtp.from_email}
              onChange={(e) => setSmtp({ ...smtp, from_email: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Nome do remetente</label>
            <input
              className="input"
              value={smtp.from_name}
              onChange={(e) => setSmtp({ ...smtp, from_name: e.target.value })}
            />
          </div>
        </div>

        {error && <div className="text-sm text-red-400">{error}</div>}
        {saved && <div className="text-sm text-emerald-400">Configurações de e-mail salvas.</div>}

        <button type="submit" className="btn-primary" disabled={saving}>
          {saving ? "Salvando..." : "Salvar configurações de e-mail"}
        </button>
      </form>
    </div>
  );
}
