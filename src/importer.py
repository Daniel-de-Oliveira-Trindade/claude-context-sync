"""
Importer - Imports session bundles into Claude Code

Responsibilities:
1. Read and validate JSON bundle (supports .gz)
2. Denormalize paths for the local device
3. Create directory structure
4. Write messages to JSONL
5. Restore file-history and todos
6. Update sessions-index.json
"""

import gzip
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

from .path_transformer import PathTransformer


class SessionImporter:
    """Imports session bundles into Claude Code"""

    def __init__(self, transformer: Optional[PathTransformer] = None):
        """
        Initialize the importer.

        Args:
            transformer: PathTransformer for path denormalization
        """
        self.transformer = transformer or PathTransformer()
        self.claude_dir = Path.home() / ".claude"

    def read_bundle(self, bundle_path: str) -> Dict:
        """
        Read a bundle JSON file (auto-detects gzip by extension).

        Args:
            bundle_path: Path to the bundle file (.bundle or .bundle.gz)

        Returns:
            Dict with bundle data

        Raises:
            FileNotFoundError: If the bundle file does not exist
            json.JSONDecodeError: If the bundle is corrupted
        """
        bundle_file = Path(bundle_path)

        if not bundle_file.exists():
            raise FileNotFoundError(f"Bundle file not found: {bundle_path}")

        if bundle_file.suffix == '.gz':
            with gzip.open(bundle_file, 'rt', encoding='utf-8') as f:
                return json.load(f)
        else:
            with open(bundle_file, 'r', encoding='utf-8') as f:
                return json.load(f)

    def calculate_checksum(self, data: Dict) -> str:
        """
        Calculate a SHA256 checksum for the given data.

        Args:
            data: Session data dict

        Returns:
            SHA256 hash as a hex string
        """
        json_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(json_str.encode('utf-8')).hexdigest()

    def validate_bundle(self, bundle: Dict) -> tuple[bool, list[str]]:
        """
        Validate bundle integrity (required fields + checksum).

        Args:
            bundle: Bundle data dict

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        required_fields = ['version', 'checksum', 'session']
        for field in required_fields:
            if field not in bundle:
                errors.append(f"Missing required field: {field}")

        if errors:
            return False, errors

        expected = bundle['checksum']
        actual = self.calculate_checksum(bundle['session'])

        if expected != actual:
            errors.append(f"Checksum mismatch! Expected {expected}, got {actual}")
            errors.append("Bundle may be corrupted or tampered with")

        session = bundle['session']
        required_session_fields = ['sessionId', 'messages']
        for field in required_session_fields:
            if field not in session:
                errors.append(f"Missing required session field: {field}")

        return len(errors) == 0, errors

    def denormalize_paths_in_messages(self, messages: List[Dict], show_progress: bool = False) -> List[Dict]:
        """
        Denormalize template-variable paths in messages to absolute local paths.

        Args:
            messages: List of session messages
            show_progress: Show a progress bar

        Returns:
            Messages with denormalized paths
        """
        if show_progress and TQDM_AVAILABLE:
            iterator = tqdm(messages, desc="Denormalizing paths", unit="msg")
        else:
            iterator = messages

        for msg in iterator:
            if 'cwd' in msg and msg['cwd']:
                try:
                    msg['cwd'] = self.transformer.denormalize(msg['cwd'])
                except Exception as e:
                    print(f"Warning: Failed to denormalize cwd '{msg['cwd']}': {e}")

            if 'projectPath' in msg and msg['projectPath']:
                try:
                    msg['projectPath'] = self.transformer.denormalize(msg['projectPath'])
                except Exception:
                    pass

        return messages

    def denormalize_metadata(self, metadata: Dict) -> Dict:
        """Denormalize template-variable paths in session metadata to absolute local paths."""
        if 'projectPath' in metadata and metadata['projectPath']:
            try:
                metadata['projectPath'] = self.transformer.denormalize(metadata['projectPath'])
            except Exception:
                pass

        if 'fullPath' in metadata and metadata['fullPath']:
            try:
                session_id = metadata.get('sessionId')
                if session_id:
                    project_path = metadata.get('projectPath', '')
                    project_hash = self._encode_path(project_path)
                    projects_dir = self.claude_dir / "projects"
                    metadata['fullPath'] = str(projects_dir / project_hash / f"{session_id}.jsonl")
            except Exception:
                pass

        return metadata

    def write_jsonl(self, file_path: Path, messages: List[Dict], show_progress: bool = False):
        """
        Write messages to a JSONL (newline-delimited JSON) file.

        Args:
            file_path: Output file path
            messages: List of messages to write
            show_progress: Show a progress bar
        """
        if show_progress and TQDM_AVAILABLE:
            iterator = tqdm(messages, desc="Writing messages", unit="msg")
        else:
            iterator = messages

        with open(file_path, 'w', encoding='utf-8') as f:
            for msg in iterator:
                f.write(json.dumps(msg, ensure_ascii=False) + '\n')

    def import_file_history(self, session_id: str, file_history: Dict[str, str], show_progress: bool = False):
        """
        Restore the file-history for the session.

        Args:
            session_id: Session UUID
            file_history: Dict of {filename: content}
            show_progress: Show a progress bar
        """
        if not file_history:
            return

        fh_dir = self.claude_dir / "file-history" / session_id
        fh_dir.mkdir(parents=True, exist_ok=True)

        if show_progress and TQDM_AVAILABLE:
            iterator = tqdm(file_history.items(), desc="Restoring file-history", unit="file")
        else:
            iterator = file_history.items()

        for filename, content in iterator:
            try:
                (fh_dir / filename).write_text(content, encoding='utf-8')
            except Exception as e:
                print(f"Warning: Failed to write file-history entry '{filename}': {e}")

    def import_todos(self, session_id: str, todos: List):
        """
        Restore the todo list for the session.

        Args:
            session_id: Session UUID
            todos: List of todo items
        """
        if not todos:
            return

        todos_dir = self.claude_dir / "todos"
        todos_dir.mkdir(parents=True, exist_ok=True)
        todos_file = todos_dir / f"{session_id}-agent-{session_id}.json"

        try:
            with open(todos_file, 'w', encoding='utf-8') as f:
                json.dump(todos, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Warning: Failed to write todos: {e}")

    def update_sessions_index(self, project_dir: Path, session_meta: Dict):
        """
        Update or create the sessions-index.json file for the project.

        Args:
            project_dir: Project directory path
            session_meta: Session metadata dict
        """
        index_file = project_dir / "sessions-index.json"

        if index_file.exists():
            with open(index_file, 'r', encoding='utf-8') as f:
                index = json.load(f)
        else:
            index = {
                "version": 1,
                "entries": [],
                "originalPath": session_meta.get('projectPath', str(project_dir))
            }

        session_id = session_meta['sessionId']
        existing_idx = None

        for idx, entry in enumerate(index['entries']):
            if entry.get('sessionId') == session_id:
                existing_idx = idx
                break

        if existing_idx is not None:
            index['entries'][existing_idx] = session_meta
        else:
            index['entries'].append(session_meta)

        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2, ensure_ascii=False)

    def import_session(self, bundle_path: str, force: bool = False,
                       project_path_override: Optional[str] = None) -> bool:
        """
        Import a session from a bundle file.

        Args:
            bundle_path: Path to the bundle file (.bundle or .bundle.gz)
            force: If True, overwrite an existing session
            project_path_override: Local project path on this device.
                If None, defaults to the current working directory.

        Returns:
            True if the import succeeded

        Raises:
            FileNotFoundError: If the bundle file does not exist
            ValueError: If the bundle is invalid
        """
        # 1. Read bundle (auto-detects gzip by extension)
        bundle = self.read_bundle(bundle_path)

        compressed = Path(bundle_path).suffix == '.gz'
        print(f"Read bundle from: {bundle_path}{' (compressed)' if compressed else ''}")
        print(f"  Version: {bundle.get('version')}")
        print(f"  Exported at: {bundle.get('exportedAt')}")
        print(f"  Source device: {bundle.get('sourceDevice')}")

        # 2. Validate bundle
        valid, errors = self.validate_bundle(bundle)

        if not valid:
            raise ValueError(f"Invalid bundle:\n" + "\n".join(f"  - {e}" for e in errors))

        print("[OK] Bundle validation passed")

        # 3. Extract data
        session = bundle['session']
        session_id = session['sessionId']
        messages = session['messages']
        metadata = session.get('metadata', {})
        file_history = session.get('fileHistory', {})
        todos = session.get('todos', [])

        if 'sessionId' not in metadata:
            metadata['sessionId'] = session_id

        show_progress = len(messages) > 200

        # 4. Denormalize paths
        messages = self.denormalize_paths_in_messages(messages, show_progress=show_progress)
        metadata = self.denormalize_metadata(metadata)

        # 5a. Determine project_path: override > cwd
        if project_path_override:
            project_path = str(Path(project_path_override).resolve())
            metadata['projectPath'] = project_path
            project_hash = self._encode_path(project_path)
            metadata['fullPath'] = str(
                self.claude_dir / "projects" / project_hash / f"{session_id}.jsonl"
            )
            print(f"Target project path: {project_path} (overridden)")
        else:
            project_path = metadata.get('projectPath', str(Path.cwd()))
            print(f"Target project path: {project_path}")
            print(f"  (run from inside the project folder or use --project-path to change)")

        # 5b. Create directory structure
        project_hash = self._encode_path(project_path)
        project_dir = self.claude_dir / "projects" / project_hash
        project_dir.mkdir(parents=True, exist_ok=True)

        print(f"Project directory: {project_dir}")

        # 6. Check if session already exists
        session_file = project_dir / f"{session_id}.jsonl"

        if session_file.exists() and not force:
            raise FileExistsError(
                f"Session '{session_id}' already exists. Use --force to overwrite."
            )

        # 7. Write JSONL
        self.write_jsonl(session_file, messages, show_progress=show_progress)
        print(f"[OK] Wrote {len(messages)} messages to {session_file}")

        # 8. Restore file-history
        if file_history:
            self.import_file_history(session_id, file_history, show_progress=show_progress)
            print(f"[OK] Restored {len(file_history)} file-history entries")

        # 9. Restore todos
        if todos:
            self.import_todos(session_id, todos)
            print(f"[OK] Restored {len(todos)} todo items")

        # 10. Update sessions index
        self.update_sessions_index(project_dir, metadata)
        print("[OK] Updated sessions index")

        print(f"\n[SUCCESS] Session '{session_id}' imported successfully!")
        print(f"   Messages: {len(messages)}")
        if file_history:
            print(f"   File-history: {len(file_history)} entries")
        if todos:
            print(f"   Todos: {len(todos)} items")
        print(f"   Location: {session_file}")

        return True

    def _encode_path(self, path: str) -> str:
        """
        Encode a project path to a directory name (Claude Code's format).

        Args:
            path: Project path

        Returns:
            Encoded directory name
        """
        encoded = path.lower().replace("\\", "-").replace("/", "-").replace(":", "-")
        return encoded
