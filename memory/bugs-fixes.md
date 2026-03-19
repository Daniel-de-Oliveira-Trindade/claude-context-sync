# Bugs resolvidos — claude-session-sync

## crypto-setup erro genérico
- **Problema**: `from .crypto import setup_key` estava dentro do `try/except Exception` principal,
  capturando o `ImportError` como erro genérico
- **Fix**: separar o import em bloco `try/except ImportError` próprio antes do try principal

## import .enc falhava com JSON decode error
- **Problema**: design antigo salvava key derivada com salt da máquina → bundle encriptado na
  máquina A não podia ser decriptado na máquina B
- **Fix**: redesign completo — salva passphrase (XOR-obfuscado), key sempre derivada do salt
  embutido no bundle. Mesmo passphrase funciona em qualquer máquina.

## sync-pull sem args dava "Missing argument SESSION_ID_PREFIX"
- **Causa**: pacote não reinstalado após mudança de código
- **Fix**: `pip install -e .` sempre que mudar assinatura de comandos

## get_bundle_labels() não reconhecia .bundle.gz.enc
- **Problema**: filtro só checava `.bundle` e `.bundle.gz`
- **Fix**: adicionada terceira condição para `.bundle.gz.enc`

## Label mostrava "c:\" no commit git
- **Problema**: `Path(clean).parts[0]` retornava drive root no Windows
- **Fix**: usar `Path(clean).name` (último componente do path)

## hooks-install encoding error (Windows cp1252)
- **Problema**: caractere `→` (U+2192) não encodável em cp1252
- **Fix**: substituído por `:`

## Hook não rodava — executável não encontrado
- **Problema 1**: hook usava `claude-context-sync` mas só existe `claude-sync` como executável
- **Problema 2**: PATH do sistema não inclui Python Scripts quando Claude Code roda hooks
- **Fix**: `_resolve_executable()` em hooks.py resolve path absoluto do `claude-sync.exe`
  usando o diretório Scripts do mesmo Python que está rodando

## sync-pull --auto exit code 1 na abertura da IDE
- **Status**: RESOLVIDO
- **Problema**: erros de rede/git no SessionStart hook causavam exit 1 → IDE mostrava erro assustador
- **Fix**: no `except Exception` do `sync-pull --auto`, detecta erros transientes
  (`CalledProcessError` ou mensagem contendo "git"/"ssh"/"network"/"connection"/"timeout"/"remote")
  → loga no hook.log mas sai com exit 0. Erros reais (não transientes) ainda saem com exit 1.
