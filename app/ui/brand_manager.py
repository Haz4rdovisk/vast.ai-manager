"""Service to map AI models to their respective brand icons."""
import os
from PySide6.QtGui import QIcon
from pathlib import Path

class BrandManager:
    _icons_cache = {}
    
    # Mapping of keywords in model names/repos to brand keys
    BRAND_MAP = {
        "llama": "llama",
        "mistral": "mistral",
        "mixtral": "mistral",
        "gemma": "gemma",
        "qwen": "qwen",
        "nemotron": "nemotron",
        "phi": "phi",
        "cohere": "cohere",
        "command": "cohere",
        "deepseek": "deepseek",
        "ollama": "ollama",
        "gpt": "openai",
        "openai": "openai",
        "claude": "claude",
        "huggingface": "huggingface",
        "groq": "groq",
        "google": "google",
        "microsoft": "microsoft",
        "nvidia": "nvidia",
    }

    @classmethod
    def get_icon(cls, name_or_repo: str) -> QIcon:
        """Returns the appropriate brand icon based on the model name."""
        name_lower = name_or_repo.lower()
        
        brand_key = "huggingface"
        for keyword, key in cls.BRAND_MAP.items():
            if keyword in name_lower:
                brand_key = key
                break
        
        if brand_key in cls._icons_cache:
            return cls._icons_cache[brand_key]
        
        # Load icon from assets
        icon_path = Path(__file__).parent.parent / "assets" / "brands" / f"{brand_key}.png"
        if not icon_path.exists():
            icon_path = Path(__file__).parent.parent / "assets" / "brands" / "huggingface.png"
            
        icon = QIcon(str(icon_path))
        cls._icons_cache[brand_key] = icon
        return icon

    @classmethod
    def get_brand_name(cls, name_or_repo: str) -> str:
        """Returns the human-readable brand name."""
        name_lower = name_or_repo.lower()
        for keyword, key in cls.BRAND_MAP.items():
            if keyword in name_lower:
                return key.capitalize()
        return "AI Model"
