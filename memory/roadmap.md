# Roadmap — claude-session-sync

## Próximo passo: Extensão VSCode

### Objetivo
Transformar o CLI em uma extensão VSCode publicável no Marketplace, com interface gráfica
para facilitar uso sem precisar do terminal.

### Stack
- TypeScript + VSCode Extension API
- Chama o CLI Python via `child_process.execFile` (reutiliza todo o backend existente)
- Publicação via `vsce` no VSCode Marketplace

### Funcionalidades planejadas

#### Fase 1 — Status Bar + Comandos básicos
- Botão `↑ Sync` na status bar → chama `claude-sync sync-push` com picker de sessão
- Botão `↓ Pull` na status bar → chama `claude-sync sync-pull` com picker do repo remoto
- Notificação nativa do VSCode quando sync termina (sucesso ou erro)
- Comando `Claude Sync: Configure Repository` abre input box para configurar URL do repo
- Substitui necessidade dos hooks manuais (extensão detecta eventos diretamente)

#### Fase 2 — Painel lateral (TreeView)
- Sidebar com sessões agrupadas por projeto (igual ao `sync-list`)
- Click em sessão → importa diretamente
- Ícone de status por sessão (sincronizado / local apenas / desatualizado)

#### Fase 3 — Configuração via UI
- Wizard de configuração inicial (repo URL, criptografia, device name)
- Sem necessidade de editar arquivos JSON manualmente

### Estrutura de pastas sugerida para a extensão
```
claude-session-sync-vscode/
├── package.json          (manifest da extensão)
├── src/
│   ├── extension.ts      (entry point, ativa/desativa)
│   ├── statusBar.ts      (botões na barra inferior)
│   ├── syncProvider.ts   (chama CLI python)
│   ├── sessionTree.ts    (TreeView do painel lateral)
│   └── config.ts         (lê/escreve configurações)
├── README.md
└── CHANGELOG.md
```

### Ponto de atenção
O CLI Python precisa estar instalado e no PATH (ou configurar path absoluto na extensão).
Alternativa futura: empacotar um binário standalone com PyInstaller.

---

## Backlog CLI (antes ou junto com extensão)

### ~~Bug: sync-pull --auto exit code 1~~ — RESOLVIDO
- Erros transientes (rede/git) agora saem com exit 0 silenciosamente no modo `--auto`

### Feature: restore-backup
- Comando `claude-sync restore-backup` lista backups em `~/.claude-sync-git/backups/`
- Agrupados por projeto e ordenados por data
- Permite restaurar sessão para um estágio anterior sem precisar do repo remoto
- Base já existe: `save_local_backup()` grava um .bundle.gz por push/pull

### Feature: hooks automáticos — WIP, não estável no Windows
- Código implementado mas com bugs conhecidos (ver bugs-fixes.md)
- Issue aberta no GitHub para rastrear
- **Workaround:** usar `sync-push` e `sync-pull` manualmente até resolução

---

## Histórico de versões

### v0.5.0 (atual)
- Organização do repo por pasta de projeto (`sanitize_project_name`)
- Backup local automático em `~/.claude-sync-git/backups/`
- Display agrupado no `sync-list` e `sync-pull` (por sessão, versões com data)
- `hooks-install --force` para atualizar hooks sem duplicar
- `hooks-install` sem `--force` mostra comandos instalados atualmente
- Hooks usam path absoluto do executável (fix para PATH do sistema)
- `claude-sync repo` sem args mostra repo configurado
- Backup local após cada `sync-push` bem-sucedido
- `.gitignore` automático no repo sync

### v0.4.0
- Encriptação AES-256-GCM com passphrase (redesign completo)
- Hooks automáticos (SessionEnd/SessionStart)
- Logs estruturados

### v0.3.0
- Release inicial público
