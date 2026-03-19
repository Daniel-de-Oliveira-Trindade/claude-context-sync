# Plan: Auto-Sync + Central Server + Session Sharing

## Contexto

Um contato viu o projeto e trouxe um caso de uso corporativo: gestores/diretores não técnicos
usando Claude em VMs gerenciadas, sem troca de contexto entre as sessões deles. O objetivo é:
- Sync automático sem interação do usuário (file watcher)
- Servidor central (além do git) com dashboard de visibilidade
- Compartilhamento de contexto entre usuários sem sobrescrever a sessão de ninguém
- Controle de acesso pelo administrador

Tudo embutido no claude-session-sync para que quem não precisar das features novas continue
usando exatamente como está.

---

## Arquitetura Geral — 4 Componentes Independentes

```
┌─────────────────────────────────────────────────────────────────────┐
│  Fase 1: File Watcher                                                │
│  • Daemon que observa ~/.claude/projects/*/  *.jsonl                │
│  • Debounce 30s → auto sync-push                                     │
│  • CLI: claude-sync watch [--daemon] [--interval N]                  │
│  • Extensão: toggle "Auto Sync" no settings                          │
└─────────────────────────────────────────────────────────────────────┘
         ↓ push bundles
┌─────────────────────────────────────────────────────────────────────┐
│  Fase 2: Central Server (HTTP API)                                   │
│  • Substitui/complementa o git repo                                  │
│  • Auth token por usuário                                            │
│  • REST: POST /sessions/push, GET /sessions/pull, GET /sessions/list │
│  • Metadata: user_id, session_size, token_count (estimado)           │
│  • Git como backup automático de tudo                                │
└─────────────────────────────────────────────────────────────────────┘
         ↓ armazena + expõe
┌─────────────────────────────────────────────────────────────────────┐
│  Fase 3: Session Sharing (sem sobrescrever)                          │
│  • Usuário A compartilha sessão → aparece para Usuário B             │
│  • B importa em diretório SEPARADO (novo project dir, não sobrescreve)│
│  • Claude lê o contexto do colega como "referência"                  │
│  • CLI: claude-sync share SESSION_ID --with USER                     │
│  • CLI: claude-sync inbox (lista sessões compartilhadas comigo)      │
└─────────────────────────────────────────────────────────────────────┘
         ↓ visibilidade
┌─────────────────────────────────────────────────────────────────────┐
│  Fase 4: Admin Dashboard (Web UI)                                    │
│  • Tabela: usuários × sessions × tamanho × tokens estimados          │
│  • Controle de acesso: quem compartilhou o quê com quem              │
│  • Ação: revogar compartilhamento, forçar pull para um usuário        │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Fase 1 — File Watcher (mais simples, mais valor imediato)

### Mecanismo
- Usar `watchdog` (Python) para observar `~/.claude/projects/`
- Evento: modificação de qualquer `.jsonl` → extrair session_id do nome do arquivo
- Debounce de 30s após última modificação (evita push a cada keystroke)
- Ao disparar: executa `sync-push --session {id} --auto --compress`

### Modos de operação

**O daemon vive no CLI — funciona com ou sem VSCode:**
```bash
claude-sync watch --daemon      # inicia em background, PID salvo em ~/.claude-context-sync/watch.pid
claude-sync watch --stop        # para o daemon
claude-sync watch --status      # mostra se está rodando + última atividade
```

Para ambientes sem VSCode (ex: VMs do parceiro), o administrador roda `claude-sync watch --daemon`
uma vez por máquina via script de setup. Zero interação do usuário final.

**Integrado nos hooks (instalação automática via CLI):**
- `hooks-install` pode opcionalmente iniciar o watcher (flag `--watch`)
- Em Windows: alternativa via Task Scheduler (gerado automaticamente por `hooks-install --watch`)
- Em Linux/Mac: opção de gerar unit file para systemd/launchd

### Extensão VSCode (camada de conveniência — não obrigatória)
- Nova setting: `claudeContextSync.autoSync: boolean` (default false)
- Quando ativado: chama `claude-sync watch --daemon` via CLI runner (usando o binário embutido no VSIX)
- Status bar mostra "Auto Sync: ON" + última sincronização (lida do log)
- Toggle simples para usuários VSCode — por baixo é o mesmo daemon Python

**Distribuição:** O binário `claude-sync-{win32|darwin|linux}` já é embutido no VSIX pelo
GitHub Actions. O comando `watch` vai junto automaticamente no mesmo binário — quem instala
a extensão já tem o daemon sem precisar do CLI separado. O build VSIX atual já cobre tudo.

### Arquivos a modificar
- **`src/cli.py`** — novo comando `watch`
- **`src/watcher.py`** — novo módulo com lógica do FileWatcher (watchdog)
- **`setup.py`** — adicionar `watchdog` nas dependências
- **`vscode-extension/src/extension.ts`** — registrar FileSystemWatcher se autoSync=true
- **`vscode-extension/package.json`** — nova setting `autoSync`

---

## Fase 2 — Central Server

### Stack recomendada
- **Backend**: FastAPI (Python) — já usa Python, reutiliza `exporter.py`, `crypto.py`, `git_sync.py`
- **Storage**: disco local (bundles como arquivos) + git repo como backup automático
- **Auth**: JWT tokens, gerados pelo admin via CLI ou API

### API REST (mínima)

```
POST   /api/sessions/push          → upload bundle (multipart)
GET    /api/sessions               → listar sessions do usuário autenticado
GET    /api/sessions/{prefix}      → baixar bundle mais recente
GET    /api/sessions/{prefix}/versions → listar versões
DELETE /api/sessions/{prefix}      → deletar

POST   /api/admin/users            → criar usuário (admin only)
GET    /api/admin/dashboard        → métricas (sessões, tamanhos, tokens estimados)
GET    /api/admin/sessions         → todas as sessões de todos os usuários (admin only)
```

### Mudanças no CLI
- Nova config: `claude-sync server-url https://sync.empresa.com`
- Quando `server-url` configurado: `sync-push`/`sync-pull`/`sync-list` usam HTTP em vez de git
- O git continua como fallback se server não responder
- `claude-sync token --generate` (admin) / `claude-sync token --save TOKEN` (usuário)

### Mudanças na Extensão
- Nova setting: `claudeContextSync.serverUrl` (complementa `defaultRepo`)
- Se serverUrl configurado: runner chama HTTP em vez de git
- Tree providers continuam iguais (mesma interface, diferente backend)

### Estimativa de tokens
- Não há API Anthropic para consultar tokens usados por sessão
- Estimativa local: `len(conteúdo_jsonl) / 4` (aproximação 1 token ≈ 4 chars)
- Armazenar no bundle metadata: `estimatedTokens: int`

### Estrutura do servidor
```
claude-sync-server/           # subpasta dentro do projeto ou repo separado
├── server/
│   ├── main.py               # FastAPI app
│   ├── auth.py               # JWT auth
│   ├── storage.py            # salvar/buscar bundles no disco
│   ├── git_backup.py         # push automático para git repo de backup
│   └── admin.py              # endpoints admin
├── Dockerfile
└── docker-compose.yml
```

---

## Fase 3 — Compartilhamento de Contexto

### O problema de UX central

Não é possível injetar contexto em uma sessão ativa do Claude — ele só lê o contexto
disponível no início de cada sessão. Isso significa que para B "saber o que A está fazendo",
existem dois momentos:

1. **Ao iniciar nova sessão** — Claude lê automaticamente arquivos de contexto do projeto
2. **Mid-session, explicitamente** — usuário pede "leia o arquivo de contexto do time"

### Abordagem principal: CLAUDE.md injection (zero fricção para o usuário)

Claude Code lê automaticamente o `CLAUDE.md` no diretório do projeto ao iniciar qualquer sessão.
O sistema pode **escrever/atualizar esse arquivo** automaticamente com o resumo das sessões
compartilhadas pelos colegas.

**Como funciona:**
1. Usuário A tem auto-sync ativo → sessão sobe para o servidor ao ser modificada
2. Servidor extrai resumo das últimas N mensagens de A (sem expor o conteúdo completo)
3. Servidor atualiza `CLAUDE.md` no projeto de B (ou num arquivo `team-context.md`)
4. Na próxima sessão de B, Claude já sabe o que A está trabalhando sem B precisar fazer nada

**Estrutura do CLAUDE.md (seção injetada automaticamente):**
```markdown
## Team Context (auto-updated: 2026-03-18 15:30)

### usuario-a — projeto: claude-session-sync
Last activity: 2026-03-18 15:28
Working on: implementação do file watcher automático
Key decisions: usando watchdog library, debounce de 30s
Recent summary: [últimas 5 mensagens resumidas pelo servidor ou extraídas pelo Claude]
```

**Vantagem:** O usuário (técnico ou não) não precisa fazer absolutamente nada.
Claude vê o contexto do time automaticamente no início de cada sessão.

### Abordagem secundária: arquivo de referência explícita

Para quem quer "mergulhar fundo" no contexto do colega mid-session:
- Servidor salva um arquivo `~/.claude-context-sync/team/{usuario-a}.context.md`
- Usuário pode dizer ao Claude: "leia o contexto do usuário A em team/usuario-a.context.md"
- Conteúdo: resumo das últimas sessões + arquivos que A estava editando

### Abordagem para "continuar exatamente onde A parou" (caso avançado)

Quando B quer **importar a sessão completa** de A (para replicar o estado exato):

```
~/.claude/projects/
├── c--users-b-documents-projetos-meu-projeto/   ← sessões de B (intactas)
│   └── {session_b}.jsonl
└── shared--usuario-a--claude-session-sync/      ← sessão de A importada separada
    └── {session_a}.jsonl
```

**Problema de UX:** B precisaria abrir esse diretório no Claude Code separadamente.
**Solução na extensão VSCode:** Comando "Open Shared Session in New Window" que executa
`vscode.commands.executeCommand('vscode.openFolder', uri, { forceNewWindow: true })`
abrindo automaticamente a sessão de A numa nova janela — sem precisar usar terminal.

**Se o ambiente não for VSCode** (sistema próprio do parceiro): a extensão não ajuda.
Nesse caso, a abordagem do CLAUDE.md é a única que funciona de forma universal.

### Fluxo de compartilhamento

```bash
# Usuário A — compartilhar sessão com B (ou com um grupo/projeto)
claude-sync share {session_id} --with usuario-b
claude-sync share {session_id} --with @time-backend   # grupo

# Usuário B — ver o que foi compartilhado
claude-sync inbox
# → usuario-a | claude-session-sync | 2026-03-18 | "Implementando X..."

# Opção 1: atualizar CLAUDE.md do projeto atual com contexto de A (recomendado)
claude-sync inbox apply {session_prefix} --to-claude-md

# Opção 2: importar sessão completa em diretório separado
claude-sync inbox pull {session_prefix}
# → Importado em ~/.claude/projects/shared--usuario-a--claude-session-sync/
```

### Na Extensão
- Nova seção na sidebar: **Shared With Me** (só aparece se serverUrl configurado)
- Cada item: nome do usuário que compartilhou + projeto + firstPrompt
- Dois botões: "Inject to CLAUDE.md" e "Import to New Window"

### Controle de acesso
- Default: sessões são privadas
- `share` cria uma entrada no servidor: `{session_prefix, shared_by, shared_with, created_at}`
- Admin pode ver todos os compartilhamentos e revogar via dashboard

---

## Fase 4 — Admin Dashboard

### Interface web simples (server-side rendered)
- FastAPI + Jinja2 templates (sem framework JS separado)
- Rota `/admin` protegida por login básico ou token admin

### Telas
1. **Usuários**: lista, token de acesso, data de criação, botão revogar
2. **Sessões**: por usuário, projeto, tamanho, tokens estimados, última atualização
3. **Compartilhamentos**: quem compartilhou com quem, revogar acesso
4. **Storage**: tamanho total, bundles mais antigos, limpeza

---

## Ordem de implementação recomendada

```
[DONE] Fase 1a: File Watcher no CLI (watchdog)         ← src/watcher.py + comando watch
[ ]    Fase 1b: Auto Sync na extensão VSCode           ← depende só da extensão
[ ]    Fase 2a: Central Server básico (push/pull/list) ← core do servidor
[ ]    Fase 2b: CLI adapta para HTTP quando configurado ← muda sync-push/pull
[ ]    Fase 2c: Extensão suporta serverUrl             ← UI continua igual
[ ]    Fase 3:  Compartilhamento + inbox               ← depende do servidor
[ ]    Fase 4:  Admin dashboard                        ← depende do servidor
```

Fase 1a concluída e testada em 2026-03-19. Fase 1b (extensão) pendente.
Fases 2-4 são um projeto maior que pode ser desenvolvido em paralelo.

---

## Status de implementação (atualizado 2026-03-19)

### ✅ Fase 1a — File Watcher CLI (CONCLUÍDO)

**Arquivos criados/modificados:**
- `src/watcher.py` — módulo completo com `SessionWatcher`, `_DebounceHandler`, helpers de PID e log
- `src/cli.py` — comando `watch` com flags `--daemon`, `--stop`, `--status`, `--debounce`, `--repo`
- `setup.py` — `watchdog` adicionado nas dependências

**Comportamento:**
- Monitora `~/.claude/projects/**/*.jsonl` via watchdog
- Debounce de 30s após última modificação → dispara `sync-push --session {id} --auto --compress`
- Daemon: escreve PID em `~/.claude-context-sync/watch.pid`, log em `~/.claude-context-sync/logs/watch.log`
- `--status` lê PID e verifica se processo está vivo + mostra último sync

**Bug corrigido em 2026-03-19:**
- Daemon usava `python -m claude_context_sync.cli` que falha com instalação editable no Python 3.14+
- Fix: daemon agora usa `_resolve_executable()` para chamar o executável `claude-sync` diretamente

**Testado:**
- Watcher detecta mudanças no `.jsonl` da sessão ativa e dispara push (log confirmado)
- `--status` mostra corretamente se está rodando

**Pendente na Fase 1a:**
- `claude-sync watch --daemon` + `--status` às vezes Aborted! no PowerShell quando há dois
  executáveis no PATH (Python 3.13 e 3.14). Fix: `pip install -e .` no Python correto

---

### ⬜ Fase 1b — Auto Sync na extensão VSCode (PENDENTE)

- Nova setting: `claudeContextSync.autoSync: boolean`
- Status bar "Auto Sync: ON" + timestamp do último sync
- Chama `claude-sync watch --daemon` via CLI runner ao ativar

---

### ⬜ Fases 2-4 — Central Server, Sharing, Dashboard (PENDENTE)

Ver detalhes nas seções abaixo.

---

## Viabilidade

| Aspecto | Viável? | Observação |
|---|---|---|
| File watcher auto-push | Sim | watchdog é simples e cross-platform |
| Servidor HTTP central | Sim | FastAPI, poucos endpoints, mesmo Python |
| Compartilhar sem sobrescrever | Sim | import para project dir diferente já funciona |
| Visibilidade de tokens | Parcial | estimativa local (não há API Anthropic para isso) |
| Admin dashboard | Sim | Jinja2 templates simples |
| Git como backup do servidor | Sim | git_sync.py já existe, só precisar rodar no servidor |
| Usuários não técnicos | Sim | daemon + hooks = zero interação necessária |

---

## Verificação

**Fase 1 — File Watcher:**
```bash
claude-sync watch --daemon
# Abrir o Claude Code e começar uma sessão
# Aguardar 30s após última mensagem
# Verificar: git log em ~/.claude-sync-git mostra novo commit automático
claude-sync watch --status  # deve mostrar "running, last sync: X"
claude-sync watch --stop
```

**Fase 2 — Servidor:**
```bash
cd claude-sync-server && docker-compose up
claude-sync server-url http://localhost:8000
claude-sync token --save TOKEN
claude-sync sync-push  # deve usar HTTP em vez de git
curl http://localhost:8000/api/sessions  # deve listar o bundle enviado
```

**Fase 3 — Compartilhamento:**
```bash
# Terminal Usuário A
claude-sync share {session_id} --with usuario-b

# Terminal Usuário B
claude-sync inbox
claude-sync inbox pull {prefix}
# Verificar: ~/.claude/projects/shared--usuario-a--{projeto}/ criado com .jsonl correto
# Abrir Claude Code → projeto shared deve aparecer separado dos projetos de B
```
