# Claude Session Sync — Guia de Setup Completo

## Pré-requisitos

- Python 3.10+ instalado com pip
- Git instalado
- ngrok (para expor o servidor — opcional, só para testes entre máquinas)

---

## 1. Instalar o CLI

```bash
cd /caminho/para/claude-session-sync
pip install -e .
```

Confirmar que funcionou:
```bash
claude-sync --version
```

---

## 2. Instalar dependências do servidor

```bash
cd /caminho/para/claude-session-sync/claude-sync-server
pip install fastapi uvicorn python-multipart
```

---

## 3. Subir o servidor

Abra um terminal dedicado para o servidor e deixe rodando:

### Windows (PowerShell)
```powershell
$env:SYNC_DATA_DIR="C:\Users\SEU_USUARIO\.claude-sync-server"
cd C:\caminho\para\claude-session-sync\claude-sync-server
python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
```

### Linux / macOS
```bash
export SYNC_DATA_DIR="$HOME/.claude-sync-server"
cd /caminho/para/claude-session-sync/claude-sync-server
python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
```

> **Importante:** use `--host 0.0.0.0` para aceitar conexões de outras máquinas.
> Sem isso, só `localhost` consegue acessar.

Confirmar que subiu:
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

---

## 4. Criar o primeiro usuário admin

Em outro terminal (com o servidor já rodando), execute **uma única vez**:

### Windows
```powershell
cd C:\caminho\para\claude-session-sync\claude-sync-server
python -c "
import os
os.environ['SYNC_DATA_DIR'] = 'C:\\Users\\SEU_USUARIO\\.claude-sync-server'
from server.auth import generate_token
token = generate_token('SEU_NOME', is_admin=True)
print('Token:', token)
"
```

### Linux / macOS
```bash
cd /caminho/para/claude-session-sync/claude-sync-server
python -c "
import os
os.environ['SYNC_DATA_DIR'] = '$HOME/.claude-sync-server'
from server.auth import generate_token
token = generate_token('SEU_NOME', is_admin=True)
print('Token:', token)
"
```

**Guarde o token — ele aparece só uma vez.**

---

## 5. Configurar o CLI na máquina

```bash
# Aponta para o servidor (use localhost se for a própria máquina)
claude-sync server-url http://localhost:8000

# Salva o token gerado no passo anterior
claude-sync token --save SEU_TOKEN_AQUI
```

Confirmar configuração:
```bash
claude-sync server-url       # deve mostrar a URL
claude-sync token --show     # deve mostrar token mascarado
```

---

## 6. Ativar o File Watcher (auto-push)

O watcher monitora `~/.claude/projects/` e faz push automático ao servidor
quando detecta mudança em qualquer sessão do Claude Code.

```bash
# Iniciar em background
claude-sync watch --daemon

# Verificar se está rodando
claude-sync watch --status

# Ver o log em tempo real
# Windows:
Get-Content "$env:USERPROFILE\.claude-context-sync\logs\watch.log" -Wait
# Linux/macOS:
tail -f ~/.claude-context-sync/logs/watch.log

# Parar
claude-sync watch --stop
```

---

## 7. Testar push e pull manualmente

```bash
# Ver sessões locais disponíveis
claude-sync list

# Subir uma sessão para o servidor
claude-sync sync-push --session ID_DA_SESSAO --compress

# Listar sessões no servidor
claude-sync sync-list

# Baixar uma sessão do servidor
claude-sync sync-pull ID_DA_SESSAO
```

---

## 8. Expor o servidor com ngrok (para acesso de outras máquinas)

O ngrok cria um túnel público para o servidor local.

### Instalação
1. Baixe em [ngrok.com/download](https://ngrok.com/download)
2. Crie conta grátis em ngrok.com
3. Copie o authtoken da sua conta

### Configurar e rodar
```bash
# Configurar token (só uma vez)
ngrok config add-authtoken SEU_AUTHTOKEN_NGROK

# Expor a porta 8000
ngrok http 8000
```

Vai aparecer algo como:
```
Forwarding   https://abc123.ngrok-free.app -> http://localhost:8000
```

A URL `https://abc123.ngrok-free.app` é o endereço público do seu servidor.

### Na outra máquina

```bash
claude-sync server-url https://abc123.ngrok-free.app
claude-sync token --save TOKEN_DO_USUARIO
claude-sync sync-list           # deve listar sessões do servidor
claude-sync sync-pull 097f3474  # baixa sessão específica
```

> **Atenção:** A URL do ngrok muda a cada vez que você reinicia. Para URL fixa,
> use um domínio estático no plano pago, ou hospede o servidor em uma VPS.

---

## 9. Criar usuários adicionais (admin)

Com o servidor rodando e você autenticado como admin:

```bash
claude-sync token --create-user NOME_DO_USUARIO
# Imprime o token do novo usuário — repasse para ele
```

---

## Resumo do fluxo entre duas máquinas

```
Máquina A (você):
  1. claude-sync watch --daemon   → auto-push ao detectar mudanças
  2. Sessões sobem para o servidor automaticamente

Máquina B (colega):
  1. claude-sync server-url http://IP_DO_SERVIDOR:8000
  2. claude-sync token --save TOKEN
  3. claude-sync sync-pull ID_SESSAO   → importa sessão de A
  4. Abre Claude Code na pasta do projeto → sessão disponível
```

---

## Solução de problemas comuns

| Problema | Causa | Solução |
|---|---|---|
| `Aborted!` no `watch --status` | Dois Python no PATH | Rodar `pip install -e .` no Python correto |
| `watch --daemon` retorna PID mas `--status` diz "not running" | Executável antigo no PATH | `pip install -e .` e verificar qual `claude-sync` está no PATH |
| Push vai para git em vez do servidor | `server-url` não configurado ou token inválido | `claude-sync server-url` e `claude-sync token --show` |
| `401 Unauthorized` no servidor | Token inválido ou SYNC_DATA_DIR diferente entre criação e uso | Recriar usuário com o mesmo `SYNC_DATA_DIR` do servidor |
| `git push exit 128` | Sem autenticação SSH/HTTPS | Mudar remote para HTTPS: `git remote set-url origin https://...` |

---

## 10. Compartilhamento de sessões entre usuários

### Usuário A compartilha uma sessão:
```bash
claude-sync share SESSION_PREFIX --with USUARIO_B
# Exemplo: claude-sync share 097f3474 --with maria
```

### Usuário B vê o que foi compartilhado:
```bash
claude-sync inbox
```

### Usuário B baixa a sessão:
```bash
claude-sync inbox --pull SHARE_ID --project-path /caminho/do/projeto
```

---

## 11. Auto Sync via extensão VSCode

Na extensão, clique no botão $(radio-tower) na barra do "Local Sessions" para ligar/desligar o Auto Sync.

Ou configure nas settings do VSCode:
- `claudeContextSync.serverUrl` — URL do servidor central
- `claudeContextSync.serverToken` — token de acesso
- `claudeContextSync.autoSync` — ligar auto sync automaticamente

---

## 12. Configuração pelo administrador (para ambientes gerenciados)

O admin pode pré-configurar as settings do VSCode para todos os usuários:
1. Instala a extensão em cada máquina
2. Define `serverUrl` e `serverToken` nas settings (via UI ou settings.json)
3. A extensão sincroniza automaticamente com o servidor na próxima abertura
4. Ativa `autoSync: true` para que o watcher inicie automaticamente
