import json
import os

class ConfigManager:
    _instance = None
    CONFIG_FILE = "config.json"
    
    def _get_config_path(self):
        from utils.path_utils import get_config_path
        return get_config_path(self.CONFIG_FILE)

    DEFAULT_CONFIG = {
        "zoom_max": 1.3,
        "smooth_speed": 0.15,
        "zoom_duration": 1.0,
        "audio_mode": "none",
        "system_volume": 1.0,
        "mic_volume": 2.0,
        "language": "zh_CN",
        "record_region": None
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance.config = cls.DEFAULT_CONFIG.copy()
            cls._instance._load_config()
        return cls._instance

    def _load_config(self):
        config_path = self._get_config_path()
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Merge with defaults
                    for key, value in data.items():
                        self.config[key] = value
            except Exception as e:
                print(f"Error loading config: {e}")

    def save_config(self):
        try:
            config_path = self._get_config_path()
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving config: {e}")

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
        self.save_config()

config_manager = ConfigManager()
