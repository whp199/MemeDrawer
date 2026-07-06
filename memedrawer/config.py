import os
import json
from pathlib import Path
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

CONFIG_DIR_NAME = "memedrawer"
CONFIG_FILE_NAME = "config.json"

class AppConfig(BaseModel):
    provider: str = Field("gemini", description="AI Provider: 'gemini' or 'openai' (LM-Studio)")
    gemini_api_key: Optional[str] = Field(None, description="Google Gemini API Key")
    gemini_model: str = Field("gemini-2.5-flash", description="Gemini Vision Model name")
    openai_api_key: Optional[str] = Field(None, description="OpenAI / LM-Studio API Key (optional for local)")
    openai_base_url: str = Field("http://localhost:1234/v1", description="OpenAI-compatible base URL")
    openai_model: str = Field("local-model", description="Model name in LM-Studio / OpenAI")
    concurrency: int = Field(3, description="Number of concurrent requests (set to 1 for sequential processing, highly recommended for local models)")
    rename_files: bool = Field(True, description="Rename files using descriptive descriptions from LLM")
    rename_format: str = Field("{suggested_filename}", description="Naming format: e.g. '{suggested_filename}'")
    reaction_images_dir: str = Field("reaction images", description="Directory folder name for generic reaction images")
    board_sorting: bool = Field(True, description="Sort files under 4chan-like board folders (e.g. /g/, /pol/, /a/) if applicable")

def get_config_paths() -> tuple[Path, Path]:
    """Returns (local_path, global_path) for config file locations."""
    local_path = Path.cwd() / "memedrawer_config.json"
    
    # Global path: ~/.config/memedrawer/config.json or equivalent on non-linux
    home = Path.home()
    if os.name == 'nt': # Windows
        global_dir = home / "AppData" / "Roaming" / CONFIG_DIR_NAME
    else: # Linux/Mac
        global_dir = home / ".config" / CONFIG_DIR_NAME
    global_path = global_dir / CONFIG_FILE_NAME
    return local_path, global_path

def load_config() -> AppConfig:
    """Loads configuration from local, global, or environment variables."""
    local_path, global_path = get_config_paths()
    config_dict = {}

    # 1. Load from global config first
    if global_path.exists():
        try:
            with open(global_path, "r", encoding="utf-8") as f:
                config_dict.update(json.load(f))
        except Exception:
            pass # Fall back if corrupted

    # 2. Override with local config
    if local_path.exists():
        try:
            with open(local_path, "r", encoding="utf-8") as f:
                config_dict.update(json.load(f))
        except Exception:
            pass

    # 3. Override with environment variables
    env_mappings = {
        "MEMEDRAWER_PROVIDER": "provider",
        "GEMINI_API_KEY": "gemini_api_key",
        "GEMINI_MODEL": "gemini_model",
        "OPENAI_API_KEY": "openai_api_key",
        "OPENAI_BASE_URL": "openai_base_url",
        "OPENAI_MODEL": "openai_model",
        "MEMEDRAWER_CONCURRENCY": "concurrency",
    }
    for env_var, config_key in env_mappings.items():
        val = os.environ.get(env_var)
        if val is not None:
            if config_key == "concurrency":
                try:
                    config_dict[config_key] = int(val)
                except ValueError:
                    pass
            else:
                config_dict[config_key] = val

    # Instantiate model with defaults + overrides
    return AppConfig(**config_dict)

def save_config(config: AppConfig, local: bool = False) -> Path:
    """Saves config either locally (current dir) or globally (home dir)."""
    local_path, global_path = get_config_paths()
    target_path = local_path if local else global_path

    # Ensure parent directory exists
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(config.model_dump(), f, indent=4)
        
    return target_path
