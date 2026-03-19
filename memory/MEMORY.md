# claude-session-sync — Memória do Projeto

## Versão atual: 0.5.2
Instalado em: `C:\Users\fsf\Documents\projetos\claude-session-sync`
Executável: `C:\Users\fsf\AppData\Local\Programs\Python\Python314\Scripts\claude-sync.exe`
Reinstalar após mudanças: `python -m pip install -e .`
**Atenção:** Pode haver dois claude-sync no PATH (Python313 e Python314). Se `--status` der Aborted!, rodar `pip install -e .` no Python correto.

## Arquitetura
- `src/cli.py` — todos os comandos Click (incluindo `watch`)
- `src/git_sync.py` — GitSync, push/pull/list/backup, organização por pastas de projeto
- `src/crypto.py` — AES-256-GCM, passphrase-based (não key-based), salt por bundle
- `src/hooks.py` — HooksManager, instala/remove hooks no ~/.claude/settings.json
- `src/exporter.py` — exporta sessão para bundle JSON, inclui scan direto de .jsonl sem index
- `src/path_transformer.py` — mapeamento de paths entre máquinas, config padrão do repo
- `src/watcher.py` — FileWatcher daemon (watchdog), debounce 30s, auto sync-push

## Convenções
- Bundles organizados por projeto no repo: `~/.claude-sync-git/{projeto}/`
- Backups locais (não commitados): `~/.claude-sync-git/backups/{projeto}/`
- `.gitignore` do repo sync inclui `backups/` (criado automaticamente)
- Nome de arquivo bundle: `{session_id}_{YYYYMMDD-HHMMSS}.bundle.gz[.enc]`
- HOOK_MARKER = `"claude-context-sync"` (usado para detectar/remover hooks)

## Decisões técnicas importantes
- **Crypto**: passphrase salva com XOR-obfuscation + machine pad. Key derivada do salt do bundle
  (PBKDF2-HMAC-SHA256). Salt aleatório por bundle → mesmo passphrase funciona em qualquer máquina.
- **Hooks usam path absoluto** do executável (resolvido em `_build_hooks()` via `_resolve_executable()`)
  porque o PATH do sistema não inclui Python Scripts quando o Claude Code roda hooks.
- **SessionEnd hook dispara na extensão VSCode** — confirmado. SessionStart também.
- **`sync-pull --auto` falha com código 1** quando não há bundle disponível — é comportamento esperado.
- **Daemon watch usa `_resolve_executable()`** para encontrar o binário — não usa `python -m` pois
  falha com instalação editable no Python 3.14+.
- **`--bundle-file`** no sync-pull permite baixar bundle exato pelo nome (evita pegar versão errada).
- **`--repo` não é injetado no comando `list`** — apenas em sync-push/pull/sync-list.

## Comandos principais
```
claude-sync repo                    # mostra repo configurado
claude-sync repo <url>              # configura repo
claude-sync hooks-install           # mostra status se já instalado
claude-sync hooks-install --force   # atualiza hooks para versão atual
claude-sync sync-push               # exporta e envia sessão para git
claude-sync sync-push --all         # push de todas as sessões do projeto
claude-sync sync-pull               # baixa e importa sessão do git
claude-sync sync-pull --all         # baixa todas as sessões disponíveis
claude-sync sync-list               # lista sessões agrupadas por projeto
claude-sync crypto-setup            # configura passphrase de encriptação
claude-sync watch                   # monitora mudanças e auto-push (foreground)
claude-sync watch --daemon          # inicia watcher em background
claude-sync watch --status          # verifica se daemon está rodando
claude-sync watch --stop            # para o daemon
```

## Plano de expansão — Central Server + Sharing
Ver arquivo: `C:\Users\fsf\.claude\plans\distributed-splashing-falcon.md`
- **Fase 1a (DONE):** File Watcher CLI — `src/watcher.py` + comando `watch`
- **Fase 1b (pendente):** Auto Sync na extensão VSCode (toggle + status bar)
- **Fase 2 (pendente):** Central Server HTTP (FastAPI) substituindo/complementando git
- **Fase 3 (pendente):** Compartilhamento de sessões entre usuários (inbox, CLAUDE.md injection)
- **Fase 4 (pendente):** Admin dashboard web

## Extensão VSCode
- Publisher: DaleuStudio
- Versão atual no Marketplace: 0.1.0 (0.5.2 em processo de publicação via GitHub Actions)
- Binário embutido no VSIX: `vscode-extension/bin/claude-sync-win32.exe`
- Auto-publish no Marketplace: push de tag `v*` no GitHub dispara Actions
- Secret necessário: `VSCE_PAT` no repositório GitHub (Personal Access Token do Azure DevOps, scope Marketplace→Manage)

## Arquivos de referência detalhados
- `memory/roadmap.md` — backlog antigo (pode estar desatualizado)
- `memory/bugs-fixes.md` — histórico de bugs resolvidos
- `C:\Users\fsf\.claude\plans\distributed-splashing-falcon.md` — plano completo Fases 1-4
