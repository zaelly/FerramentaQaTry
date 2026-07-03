# QA Agent — testador de aplicações com IA

Agente de IA que navega em uma aplicação web como um usuário real, testa funcionalidades,
tira prints de qualquer erro encontrado e gera um relatório com sugestões de melhoria
(funcionalidade, UI/UX, SEO, acessibilidade, performance e segurança).

- **Backend**: Python + FastAPI + Playwright (automação de navegador) + SDK da OpenAI, apontado
  para um ou mais **provedores de IA compatíveis com a API da OpenAI** (Groq, Ollama local, ou
  qualquer outro), usando um modelo com visão para "enxergar" a tela a cada passo.
- **Frontend**: Electron (app desktop) + React + TypeScript + Tailwind, com acompanhamento do teste
  em tempo real via WebSocket.

## O que o agente verifica

Além de navegar e testar funcionalidades como um usuário real (guiado pelo modelo de visão), a cada
página nova visitada o agente roda automaticamente auditorias determinísticas (sem gastar tokens de
IA):

- **SEO**: título, meta description, meta viewport, quantidade de `<h1>`, presença de robots.txt e
  sitemap.xml.
- **Acessibilidade (WCAG)**: usando o [axe-core](https://github.com/dequelabs/axe-core) (o mesmo
  motor usado pelo Lighthouse/axe DevTools) — contraste de cores, texto alternativo em imagens,
  atributo `lang`, landmarks, headings, e dezenas de outras regras.
- **Performance/carregamento**: tempo de carregamento da página, TTFB, quantidade de requisições e
  volume de dados transferidos, com alertas para páginas lentas ou pesadas.
- **Segurança (passiva e não-destrutiva)**: uso de HTTPS, cabeçalhos de segurança HTTP
  (Content-Security-Policy, Strict-Transport-Security, X-Frame-Options, etc.), flags de cookies
  (Secure/HttpOnly/SameSite), e checagem de arquivos comumente expostos por engano (`.env`,
  `.git/config`, etc. — apenas leitura, nenhuma tentativa de exploração ativa).
- **Login social/SSO**: detecta automaticamente botões de "Entrar com Google/Microsoft/Apple/Facebook"
  e sinaliza como item para teste manual, já que provedores OAuth de terceiros normalmente exigem
  uma conta real fora do controle do agente.

Essas auditorias aparecem junto com os problemas encontrados pelo agente na aba **Problemas** e nas
sugestões do relatório final, categorizadas por tipo (Funcional, UI/UX, SEO, Acessibilidade,
Performance, Segurança).

**Importante sobre o escopo de segurança**: o agente faz apenas verificações passivas e de leitura
(cabeçalhos, cookies, arquivos expostos). Ele nunca tenta explorar vulnerabilidades ativamente
(injeção de SQL, XSS, bypass de autenticação, etc.) — isso exigiria autorização explícita e escopo
definido, e está fora do propósito desta ferramenta de QA de uso geral.

## Múltiplos provedores de IA (Groq, Ollama, ou qualquer outro)

Você pode configurar quantos provedores quiser na tela **Configurações**, em qualquer combinação:

- **Groq** (nuvem, precisa de chave de API gratuita em https://console.groq.com/keys) — rápido, mas
  cada conta tem um limite de tokens por minuto que pode ser atingido durante um teste mais longo.
- **Ollama** (roda localmente na sua máquina, sem custo e sem limite de tokens, mas depende da sua
  GPU/CPU e pode ser mais lento) — instale em https://ollama.com, depois baixe um modelo com visão
  e configure em Configurações com a URL `http://localhost:11434/v1`. Não precisa de chave de API.
- **Qualquer outro serviço compatível com a API da OpenAI** (OpenRouter, LM Studio, vLLM, Together,
  etc.) — use a opção "Personalizado" e informe a URL base e a chave, se houver.

A ordem em que os provedores aparecem na lista é a ordem de tentativa: se o primeiro falhar ou
estourar o limite de uso, o agente tenta automaticamente o próximo da lista, sem interromper o
teste. Use as setas ▲▼ para reordenar, o interruptor para ativar/desativar sem remover, e "Editar"
para trocar modelo ou chave.

### Qual modelo de visão usar no Ollama

Testado nesta máquina (GPU NVIDIA antiga, GTX 750 Ti / 2GB de VRAM):

- **`llama3.2-vision`** — quebra com um bug conhecido de várias versões recentes do Ollama
  ("`unknown model architecture: 'mllama'`"). Não é problema deste projeto; veja
  https://github.com/ollama/ollama/issues/16490. Evite por enquanto.
- **`moondream`** — bem rápido, mas não segue instruções nem responde em JSON de forma confiável;
  não funciona para o agente decidir ações.
- **`qwen2.5vl:7b`** — funciona corretamente e segue o formato JSON. **Recomendado.** Em CPU pura
  (sem GPU compatível) pode levar 1-3 minutos por passo — bem mais lento que a Groq, então funciona
  melhor como provedor de reserva (depois da Groq na lista) do que como principal.

Se sua GPU NVIDIA for mais antiga/com pouca VRAM e o Ollama travar com um erro de CUDA
("PTX was compiled with an unsupported toolchain" ou parecido) nos logs em
`%LOCALAPPDATA%\Ollama\server.log`, force o modo CPU definindo a variável de ambiente do Windows
`OLLAMA_LLM_LIBRARY=cpu` (Configurações do Windows → Variáveis de Ambiente) e reinicie o Ollama.

## Enviar relatórios por e-mail

Na tela **Configurações**, na seção "E-mail (envio de relatórios)", configure um servidor SMTP:

- **Gmail**: servidor `smtp.gmail.com`, porta 587, criptografia STARTTLS, e uma
  [senha de app](https://myaccount.google.com/apppasswords) (não a senha normal da conta — o Gmail
  não aceita mais senha normal para SMTP de terceiros).
- **Outlook/Office 365**: servidor `smtp.office365.com`, porta 587, STARTTLS.
- Qualquer outro provedor SMTP (SendGrid, Amazon SES, servidor da própria empresa, etc.) também
  funciona — basta preencher host, porta, usuário e senha corretos.

Depois de configurado, abra qualquer relatório concluído (aba **Relatório** na tela de execução) e
clique em **"Enviar por e-mail"**. Informe até 10 destinatários (separados por vírgula ou um por
linha) e, opcionalmente, uma mensagem — o mesmo relatório (com nota, sugestões por categoria,
problemas encontrados e capturas de tela) é enviado para todos de uma vez. As imagens vão embutidas
diretamente no e-mail (não como link), então aparecem mesmo se o destinatário não tiver acesso à
sua máquina.

## Pré-requisitos

1. **Python 3.10+** — instale em https://www.python.org/downloads/ (marque "Add python.exe to
   PATH" no instalador do Windows).
2. **Node.js 20.19+** (a versão atual, 20.3.1, é ligeiramente antiga para algumas ferramentas mais
   novas do ecossistema Vite/Electron — recomenda-se atualizar para a última LTS em
   https://nodejs.org).
3. Pelo menos um provedor de IA configurado: uma chave gratuita da Groq
   (https://console.groq.com/keys) e/ou o Ollama instalado localmente (https://ollama.com).

## Configuração inicial

### 1. Backend (Python)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
playwright install chromium
```

Copie `backend/.env.example` para `backend/.env` e cole sua chave da Groq (isso cria automaticamente
um provedor "Groq" na primeira execução), ou pule isso e configure todos os provedores direto pela
interface (tela **Configurações**) depois de abrir o app.

### 2. Frontend (Electron + React)

```bash
cd frontend
npm install
```

## Rodando em modo desenvolvimento

Com o backend configurado (venv criado e dependências instaladas), basta rodar o frontend — ele
sobe o backend Python automaticamente como um processo filho do Electron:

```bash
cd frontend
npm run electron:dev
```

Isso abre a janela do app. Na primeira execução, vá em **Configurações** e adicione pelo menos um
provedor de IA (Groq, Ollama local, ou outro), caso não tenha usado o `.env`.

Se preferir rodar só a interface web no navegador (sem Electron) durante o desenvolvimento:

```bash
# terminal 1
cd backend && .venv\Scripts\python run.py

# terminal 2
cd frontend && npm run dev
```

E acesse http://localhost:5173.

## Como usar

1. Na tela **Novo teste**, informe a URL da aplicação a ser testada.
2. Descreva o que o agente deve testar (ex.: "cadastre-se, faça login e finalize uma compra").
3. Se a aplicação exigir login, expanda "Credenciais de login" e informe usuário/senha de teste.
4. Clique em **Iniciar teste**. Acompanhe em tempo real: capturas de tela, ações do agente e
   problemas encontrados (com prints automáticos assim que um erro é detectado).
5. Ao final, veja o relatório com nota geral, sugestões de melhoria funcional e de UI/UX, e abra o
   relatório HTML completo para compartilhar.

## Como o agente decide o que fazer

A cada passo: tira um print da tela, identifica os elementos clicáveis/preenchíveis e desenha
caixas numeradas sobre eles, e envia tudo para o modelo de visão do provedor de IA ativo
perguntando qual é a próxima ação (clicar, preencher campo, rolar a página, voltar, ou reportar um
problema). Erros de console do navegador e requisições HTTP com falha (4xx/5xx) são capturados
automaticamente, independente do que a IA perceber visualmente. A imagem enviada à IA é redimensionada
antes do envio para reduzir custo de tokens; a versão em resolução total fica salva para o
relatório/UI.

## Empacotar como executável (opcional)

```bash
cd frontend
npm run build
npm run electron:pack
```

Isso gera o instalador em `frontend/release/`. Note que o backend Python continua sendo um
processo externo — para uma distribuição totalmente standalone, seria necessário empacotar o
backend com PyInstaller e ajustar `electron/main.cjs` para apontar para o executável gerado.

## Estrutura do projeto

```
backend/
  app/
    agent/          # loop do agente, extração do DOM, marcação visual, execução de ações
      audits.py     # auditorias de SEO, acessibilidade (axe-core), performance e segurança passiva
      vendor/       # axe-core vendorizado (motor de acessibilidade)
    reports/        # geração do relatório HTML final
    main.py         # API FastAPI (REST + WebSocket)
    ai_client.py    # cliente OpenAI SDK multi-provedor, com fallback automático
    config.py       # armazenamento dos provedores configurados (data/config.json)
  data/             # screenshots, relatórios, histórico de execuções e config.json (gerado em runtime)
frontend/
  electron/         # processo principal do Electron (sobe o backend, abre a janela)
  src/
    pages/          # Novo teste, Execução ao vivo, Histórico, Configurações
    components/     # Sidebar, badges de status/severidade
    lib/            # cliente da API e tipos compartilhados
```
