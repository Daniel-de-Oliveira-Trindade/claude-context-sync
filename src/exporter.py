"""
Exporter - Exports Claude Code sessions to a portable bundle file

Responsibilities:
1. Locate sessions in the .claude directory structure
2. Read JSONL messages
3. Normalize paths using PathTransformer
4. Export file-history and todos for the session
5. Generate a JSON bundle with SHA256 checksum (with optional gzip compression)
"""

import gzip
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

from .path_transformer import PathTransformer


class SessionExporter:
    """Exports Claude Code sessions to portable bundles"""

    def __init__(self, transformer: Optional[PathTransformer] = None):
        """
        Initialize the exporter.

        Args:
            transformer: PathTransformer for path normalization
        """
        self.transformer = transformer or PathTransformer()
        self.claude_dir = Path.home() / ".claude"

    def find_project_by_session(self, session_id: str) -> Optional[Path]:
        """
        Find the project directory that contains the given session.

        Args:
            session_id: Session UUID

        Returns:
            Path to the project directory, or None if not found
        """
        projects_dir = self.claude_dir / "projects"

        if not projects_dir.exists():
            return None

        for project_dir in projects_dir.iterdir():
            if not project_dir.is_dir():
                continue

            session_file = project_dir / f"{session_id}.jsonl"
            if session_file.exists():
                return project_dir

        return None

    def read_sessions_index(self, project_dir: Path) -> Dict:
        """Read the sessions-index.json file for a project directory."""
        index_file = project_dir / "sessions-index.json"

        if not index_file.exists():
            return {"version": 1, "entries": []}

        with open(index_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def find_session_metadata(self, index: Dict, session_id: str) -> Optional[Dict]:
        """Find session metadata in the sessions index."""
        for entry in index.get("entries", []):
            if entry.get("sessionId") == session_id:
                return entry
        return None

    def read_jsonl(self, file_path: Path, show_progress: bool = False) -> List[Dict]:
        """
        Read a JSONL (newline-delimited JSON) file.

        Args:
            file_path: Path to the .jsonl file
            show_progress: Show a progress bar

        Returns:
            List of parsed message dicts
        """
        messages = []
        lines = file_path.read_text(encoding='utf-8').splitlines()

        if show_progress and TQDM_AVAILABLE:
            iterator = tqdm(lines, desc="Reading messages", unit="msg")
        else:
            iterator = lines

        for line in iterator:
            line = line.strip()
            if line:
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"Warning: Failed to parse line: {e}")

        return messages

    def normalize_paths_in_messages(self, messages: List[Dict], show_progress: bool = False) -> List[Dict]:
        """
        Normalize all paths in session messages to template variables.

        Args:
            messages: List of session messages
            show_progress: Show a progress bar

        Returns:
            Messages with normalized paths
        """
        if show_progress and TQDM_AVAILABLE:
            iterator = tqdm(messages, desc="Normalizing paths", unit="msg")
        else:
            iterator = messages

        for msg in iterator:
            if 'cwd' in msg and msg['cwd']:
                try:
                    msg['cwd'] = self.transformer.normalize(msg['cwd'])
                except Exception as e:
                    print(f"Warning: Failed to normalize cwd '{msg['cwd']}': {e}")

            if 'projectPath' in msg and msg['projectPath']:
                try:
                    msg['projectPath'] = self.transformer.normalize(msg['projectPath'])
                except Exception:
                    pass

        return messages

    def normalize_metadata(self, metadata: Dict) -> Dict:
        """Normalize paths in session metadata to template variables."""
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

    def export_file_history(self, session_id: str) -> Dict[str, str]:
        """
        Export all file-history entries for the session.

        Args:
            session_id: Session UUID

        Returns:
            Dict of {filename: content}, or {} if no file-history exists
        """
        fh_dir = self.claude_dir / "file-history" / session_id
        if not fh_dir.exists():
            return {}

        files = {}
        for f in fh_dir.iterdir():
            if f.is_file():
                try:
                    files[f.name] = f.read_text(encoding='utf-8', errors='replace')
                except Exception as e:
                    print(f"Warning: Failed to read file-history entry '{f.name}': {e}")

        return files

    def export_todos(self, session_id: str) -> List:
        """
        Export the todo list for the session.

        Args:
            session_id: Session UUID

        Returns:
            List of todo items, or [] if none exist
        """
        todos_file = self.claude_dir / "todos" / f"{session_id}-agent-{session_id}.json"
        if not todos_file.exists():
            return []

        try:
            with open(todos_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Failed to read todos: {e}")
            return []

    def calculate_checksum(self, data: Dict) -> str:
        """
        Calculate a SHA256 checksum for the session data.

        Args:
            data: Session data dict

        Returns:
            SHA256 hash as a hex string
        """
        json_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(json_str.encode('utf-8')).hexdigest()

    def export_session(self, session_id: str, output_path: str, compress: bool = False) -> bool:
        """
        Export a session to a bundle file.

        Args:
            session_id: UUID of the session to export
            output_path: Output bundle file path
            compress: If True, compress the bundle with gzip (.gz)

        Returns:
            True if the export succeeded

        Raises:
            FileNotFoundError: If the session is not found
            ValueError: If the session data is corrupted
        """
        # 1. Locate session
        project_dir = self.find_project_by_session(session_id)

        if project_dir is None:
            raise FileNotFoundError(f"Session '{session_id}' not found in Claude projects")

        print(f"Found session in: {project_dir}")

        # 2. Read metadata
        index = self.read_sessions_index(project_dir)
        session_meta = self.find_session_metadata(index, session_id)

        if session_meta is None:
            session_meta = {
                "sessionId": session_id,
                "projectPath": str(project_dir)
            }

        # 3. Read JSONL messages
        session_file = project_dir / f"{session_id}.jsonl"
        show_progress = True
        messages = self.read_jsonl(session_file, show_progress=show_progress)

        print(f"Read {len(messages)} messages from session")

        # 4. Normalize paths
        messages = self.normalize_paths_in_messages(messages, show_progress=show_progress)
        session_meta = self.normalize_metadata(session_meta)

        # 5. Export file-history and todos
        print("Exporting file-history and todos...")
        file_history = self.export_file_history(session_id)
        todos = self.export_todos(session_id)

        # 6. Build bundle
        bundle = {
            "version": "1.1.0",
            "exportedAt": datetime.now().isoformat(),
            "sourceDevice": self.transformer.current_device,
            "session": {
                "sessionId": session_id,
                "messages": messages,
                "metadata": session_meta,
                "fileHistory": file_history,
                "todos": todos,
            }
        }

        # 7. Calculate checksum
        bundle['checksum'] = self.calculate_checksum(bundle['session'])

        # 8. Save bundle (with or without compression)
        output = Path(output_path)
        if compress and output.suffix != '.gz':
            output = Path(str(output) + '.gz')

        output.parent.mkdir(parents=True, exist_ok=True)

        if compress:
            with gzip.open(output, 'wt', encoding='utf-8') as f:
                json.dump(bundle, f, indent=2, ensure_ascii=False)
        else:
            with open(output, 'w', encoding='utf-8') as f:
                json.dump(bundle, f, indent=2, ensure_ascii=False)

        suffix = " (compressed)" if compress else ""
        print(f"[OK] Exported {len(messages)} messages to {output}{suffix}")
        print(f"   Checksum: {bundle['checksum']}")
        if file_history:
            print(f"   File-history: {len(file_history)} entries")
        if todos:
            print(f"   Todos: {len(todos)} items")

        return True

    def list_sessions(self, project_path: Optional[str] = None) -> List[Dict]:
        """
        List all available sessions.

        Args:
            project_path: Filter by project path (optional, lists all if None)

        Returns:
            List of dicts with session information
        """
        sessions = []
        projects_dir = self.claude_dir / "projects"

        if not projects_dir.exists():
            return sessions

        if project_path:
            project_hash = self._encode_path(project_path)
            project_dir = projects_dir / project_hash

            if project_dir.exists():
                index = self.read_sessions_index(project_dir)
                return index.get("entries", [])

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
        Encode a project path to a directory name (Claude Code's format).

        Args:
            path: Project path

        Returns:
            Encoded name (e.g. c--users-alice-documents-projects-my-app)
        """
        encoded = path.lower().replace("\\", "-").replace("/", "-").replace(":", "-")
        return encoded
