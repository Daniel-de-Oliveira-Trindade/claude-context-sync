"""
PathTransformer - Converte caminhos absolutos em variáveis template e vice-versa

Resolve o problema de caminhos Windows diferentes entre dispositivos usando
variáveis template como ${PROJECTS}, ${HOME}, ${CLAUDE_DIR}.
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional


class PathTransformer:
    """Transforma caminhos absolutos em templates portáveis entre dispositivos"""

    def __init__(self, config_path: Optional[str] = None):
        """
        Inicializa o PathTransformer com configuração de mapeamentos

        Args:
            config_path: Caminho para arquivo path_mappings.json (opcional)
        """
        if config_path is None:
            # Usar configuração padrão no diretório do projeto
            project_root = Path(__file__).parent.parent
            config_path = project_root / "config" / "path_mappings.json"

        self.config_path = Path(config_path)
        self.mappings = self._load_mappings()
        self.current_device = self.mappings.get("currentDevice", "desktop")

    def _load_mappings(self) -> Dict:
        """Carrega mapeamentos de configuração ou retorna padrão"""
        if not self.config_path.exists():
            # Retornar configuração padrão
            return {
                "devices": {
                    "desktop": {
                        "USER": os.environ.get("USERNAME", "user"),
                        "HOME": str(Path.home()),
                        "PROJECTS": str(Path.home() / "Documents" / "projetos"),
                        "CLAUDE_DIR": str(Path.home() / ".claude")
                    }
                },
                "currentDevice": "desktop"
            }

        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save_mappings(self):
        """Salva mapeamentos atuais no arquivo de configuração"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.mappings, f, indent=2)

    def normalize(self, absolute_path: str, source_device: Optional[str] = None) -> str:
        """
        Converte caminho absoluto para variável template

        Args:
            absolute_path: Caminho absoluto Windows (ex: C:\\Users\\fsf\\Documents\\projetos\\fcst)
            source_device: ID do dispositivo de origem (usa currentDevice se None)

        Returns:
            Caminho com template (ex: ${PROJECTS}/fcst)

        Examples:
            >>> transformer.normalize("C:\\Users\\fsf\\Documents\\projetos\\fcst")
            "${PROJECTS}/fcst"
            >>> transformer.normalize("C:\\Users\\fsf\\.claude")
            "${CLAUDE_DIR}"
        """
        if not absolute_path:
            return absolute_path

        device_id = source_device or self.current_device

        if device_id not in self.mappings["devices"]:
            raise ValueError(f"Device '{device_id}' not found in configuration")

        mapping = self.mappings["devices"][device_id]

        # Normalizar barras para Unix style
        path = absolute_path.replace("\\", "/")

        # Tentar substituir com as variáveis em ordem de especificidade
        # (mais específica primeiro para evitar substituições parciais)
        sorted_vars = sorted(
            mapping.items(),
            key=lambda x: len(x[1]),
            reverse=True
        )

        for var, value in sorted_vars:
            value_normalized = value.replace("\\", "/")
            if path.startswith(value_normalized):
                relative = path[len(value_normalized):].lstrip("/")
                if relative:
                    return f"${{{var}}}/{relative}"
                else:
                    return f"${{{var}}}"

        # Se não encontrou match, retorna o caminho original
        return absolute_path

    def denormalize(self, template_path: str, target_device: Optional[str] = None) -> str:
        """
        Converte variável template para caminho absoluto

        Args:
            template_path: Caminho com template (ex: ${PROJECTS}/fcst)
            target_device: ID do dispositivo de destino (usa currentDevice se None)

        Returns:
            Caminho absoluto Windows (ex: C:\\Users\\fsf\\Documents\\projetos\\fcst)

        Examples:
            >>> transformer.denormalize("${PROJECTS}/fcst", "laptop")
            "D:\\Projects\\fcst"
        """
        if not template_path:
            return template_path

        device_id = target_device or self.current_device

        if device_id not in self.mappings["devices"]:
            raise ValueError(f"Device '{device_id}' not found in configuration")

        mapping = self.mappings["devices"][device_id]
        result = template_path

        # Substituir todas as variáveis template
        for var, value in mapping.items():
            result = result.replace(f"${{{var}}}", value)

        # Converter para Windows style
        result = result.replace("/", "\\")

        return result

    def add_device(self, device_id: str, user: str, home: str,
                   projects: str, claude_dir: Optional[str] = None):
        """
        Adiciona novo dispositivo à configuração

        Args:
            device_id: Identificador único do dispositivo
            user: Nome de usuário Windows
            home: Diretório home do usuário
            projects: Diretório de projetos
            claude_dir: Diretório .claude (opcional, deduzido de home se None)
        """
        if claude_dir is None:
            claude_dir = str(Path(home) / ".claude")

        self.mappings["devices"][device_id] = {
            "USER": user,
            "HOME": home,
            "PROJECTS": projects,
            "CLAUDE_DIR": claude_dir
        }

        self.save_mappings()

    def set_current_device(self, device_id: str):
        """Define o dispositivo atual"""
        if device_id not in self.mappings["devices"]:
            raise ValueError(f"Device '{device_id}' not found in configuration")

        self.mappings["currentDevice"] = device_id
        self.current_device = device_id
        self.save_mappings()

    def list_devices(self) -> Dict[str, Dict[str, str]]:
        """Retorna lista de dispositivos configurados"""
        return self.mappings["devices"]

    def validate_mappings(self) -> tuple[bool, list[str]]:
        """
        Valida configuração de mapeamentos

        Returns:
            Tupla (válido, lista_de_erros)
        """
        errors = []

        if "devices" not in self.mappings:
            errors.append("Missing 'devices' key in configuration")
            return False, errors

        if not self.mappings["devices"]:
            errors.append("No devices configured")

        for device_id, mapping in self.mappings["devices"].items():
            required_keys = ["USER", "HOME", "PROJECTS", "CLAUDE_DIR"]
            for key in required_keys:
                if key not in mapping:
                    errors.append(f"Device '{device_id}' missing required key: {key}")

        current = self.mappings.get("currentDevice")
        if current and current not in self.mappings["devices"]:
            errors.append(f"Current device '{current}' not found in devices")

        return len(errors) == 0, errors