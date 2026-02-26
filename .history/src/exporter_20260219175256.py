"""
Exporter - Exporta sessões do Claude Code para bundle portável

Responsável por:
1. Localizar sessões na estrutura .claude
2. Ler mensagens JSONL
3. Normalizar caminhos usando PathTransformer
4. Gerar bundle JSON com checksum
"""

import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .path_transformer import PathTransformer


class SessionExporter:
    """Exporta sessões do Claude Code para bundles portáveis"""

    def __init__(self, transformer: Optional[PathTransformer] = None):
        """
        Inicializa o exporter

        Args:
            transformer: PathTransformer para normalização de caminhos
        """
        self.transformer = transformer or PathTransformer()
        self.claude_dir = Path.home() / ".claude"

    def find_project_by_session(self, session_id: str) -> Optional[Path]:
        """
        Encontra diretório do projeto que contém a sessão

        Args:
            session_id: UUID da sessão

        Returns:
            Path do diretório do projeto ou None se não encontrado
        """
        projects_dir = self.claude_dir / "projects"

        if not projects_dir.exists():
            return None

        # Procurar em todos os projetos
        for project_dir in projects_dir.iterdir():
            if not project_dir.is_dir():
                continue

            session_file = project_dir / f"{session_id}.jsonl"
            if session_file.exists():
                return project_dir

        return None

    def read_sessions_index(self, project_dir: Path) -> Dict:
        """Lê o arquivo sessions-index.json"""
        index_file = project_dir / "sessions-index.json"

        if not index_file.exists():
            return {"version": 1, "entries": []}

        with open(index_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def find_session_metadata(self, index: Dict, session_id: str) -> Optional[Dict]:
        """Encontra metadados da sessão no índice"""
        for entry in index.get("entries", []):
            if entry.get("sessionId") == session_id:
                return entry
        return None

    def read_jsonl(self, file_path: Path) -> List[Dict]:
        """
        Lê arquivo JSONL (newline-delimited JSON)

        Args:
            file_path: Caminho do arquivo .jsonl

        Returns:
            Lista de mensagens
        """
        messages = []

        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        messages.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        print(f"Warning: Failed to parse line: {e}")

        return messages

    def normalize_paths_in_messages(self, messages: List[Dict]) -> List[Dict]:
        """
        Normaliza todos os caminhos nas mensagens

        Args:
            messages: Lista de mensagens da sessão

        Returns:
            Mensagens com caminhos normalizados
        """
        for msg in messages:
            # Normalizar campo 'cwd' se existir
            if 'cwd' in msg and msg['cwd']:
                try:
                    msg['cwd'] = self.transformer.normalize(msg['cwd'])
                except Exception as e:
                    print(f"Warning: Failed to normalize cwd '{msg['cwd']}': {e}")

            # Normalizar outros campos que possam conter caminhos
            if 'projectPath' in msg and msg['projectPath']:
                try:
                    msg['projectPath'] = self.transformer.normalize(msg['projectPath'])
                except Exception:
                    pass

        return messages

    def normalize_metadata(self, metadata: Dict) -> Dict:
        """Normaliza caminhos nos metadados da sessão"""
        if 'projectPath' in metadata and metadata['projectPath']:
            try:
                metadata['projectPath'] = self.transformer.normalize(metadata['projectPath'])
            except Exception:
                pass

        if 'fullPath' in metadata and metadata['fullPath']:
            try:
                metadata['fullPath'] = self.transformer.normalize(metadata['fullPath'])
            except Exception:
                pass

        return metadata

    def calculate_checksum(self, data: Dict) -> str:
        """
        Calcula checksum SHA256 dos dados da sessão

        Args:
            data: Dados da sessão

        Returns:
            Hash SHA256 em hexadecimal
        """
        # Serializar de forma determinística (sorted keys)
        json_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(json_str.encode('utf-8')).hexdigest()

    def export_session(self, session_id: str, output_path: str) -> bool:
        """
        Exporta sessão para arquivo bundle

        Args:
            session_id: UUID da sessão a exportar
            output_path: Caminho do arquivo bundle de saída

        Returns:
            True se exportação foi bem-sucedida

        Raises:
            FileNotFoundError: Se sessão não for encontrada
            ValueError: Se dados estiverem corrompidos
        """
        # 1. Localizar sessão
        project_dir = self.find_project_by_session(session_id)

        if project_dir is None:
            raise FileNotFoundError(f"Session '{session_id}' not found in Claude projects")

        print(f"Found session in: {project_dir}")

        # 2. Ler metadados
        index = self.read_sessions_index(project_dir)
        session_meta = self.find_session_metadata(index, session_id)

        if session_meta is None:
            # Criar metadados básicos se não existir no índice
            session_meta = {
                "sessionId": session_id,
                "projectPath": str(project_dir)
            }

        # 3. Ler mensagens JSONL
        session_file = project_dir / f"{session_id}.jsonl"
        messages = self.read_jsonl(session_file)

        print(f"Read {len(messages)} messages from session")

        # 4. Normalizar caminhos
        messages = self.normalize_paths_in_messages(messages)
        session_meta = self.normalize_metadata(session_meta)

        # 5. Criar bundle
        bundle = {
            "version": "1.0.0",
            "exportedAt": datetime.now().isoformat(),
            "sourceDevice": self.transformer.current_device,
            "session": {
                "sessionId": session_id,
                "messages": messages,
                "metadata": session_meta
            }
        }

        # 6. Calcular checksum
        bundle['checksum'] = self.calculate_checksum(bundle['session'])

        # 7. Salvar bundle
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        with open(output, 'w', encoding='utf-8') as f:
            json.dump(bundle, f, indent=2, ensure_ascii=False)

        print(f"[OK] Exported {len(messages)} messages to {output}")
        print(f"   Checksum: {bundle['checksum']}")

        return True

    def list_sessions(self, project_path: Optional[str] = None) -> List[Dict]:
        """
        Lista todas as sessões disponíveis

        Args:
            project_path: Caminho do projeto (opcional, lista todos se None)

        Returns:
            Lista de dicionários com informações das sessões
        """
        sessions = []
        projects_dir = self.claude_dir / "projects"

        if not projects_dir.exists():
            return sessions

        # Se projeto específico fornecido
        if project_path:
            project_hash = self._encode_path(project_path)
            project_dir = projects_dir / project_hash

            if project_dir.exists():
                index = self.read_sessions_index(project_dir)
                return index.get("entries", [])

        # Listar todos os projetos
        for project_dir in projects_dir.iterdir():
            if not project_dir.is_dir():
                continue

            index = self.read_sessions_index(project_dir)
            for entry in index.get("entries", []):
                entry['_projectDir'] = str(project_dir.name)
                sessions.append(entry)

        return sessions

    def _encode_path(self, path: str) -> str:
        """
        Codifica caminho do projeto para nome de diretório

        Args:
            path: Caminho do projeto (ex: C:\\Users\\fsf\\Documents\\projetos\\fcst)

        Returns:
            Nome codificado (ex: c--Users-fsf-Documents-projetos-fcst)
        """
        # Converter para lowercase e substituir separadores
        encoded = path.lower().replace("\\", "-").replace("/", "-").replace(":", "-")
        return encoded