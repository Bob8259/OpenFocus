import json
import os
import sys

class LocaleManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LocaleManager, cls).__new__(cls)
            cls._instance.current_locale = "zh_CN"
            cls._instance.translations = {}
            cls._instance.loaded_locales = {}
            cls._instance.loaded_locales = {}
            # cls._instance.base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            cls._instance.load_locale(cls._instance.current_locale)
        return cls._instance

    def set_language(self, lang_code):
        """Set the current language and load the corresponding locale file if not loaded."""
        if lang_code == self.current_locale and lang_code in self.loaded_locales:
            return

        self.current_locale = lang_code
        self.load_locale(lang_code)

    def load_locale(self, lang_code):
        """Load a locale file."""
        if lang_code in self.loaded_locales:
            self.translations = self.loaded_locales[lang_code]
            return

        from utils.path_utils import get_resource_path
        locale_path = get_resource_path(os.path.join("locales", f"{lang_code}.json"))
        try:
            with open(locale_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.loaded_locales[lang_code] = data
                self.translations = data
                print(f"Loaded locale: {lang_code}")
        except FileNotFoundError:
            print(f"Locale file not found: {locale_path}")
            # Fallback to empty dict or keep previous? 
            # If not found, maybe invalid lang code, don't switch translations if possible or switch to empty
            if not self.translations:
                self.translations = {}
        except Exception as e:
            print(f"Error loading locale {lang_code}: {e}")

    def get_text(self, key, default=None):
        """Get a translated string by key."""
        val = self.translations.get(key, default)
        if val is None:
            return key # Return key if translation missing
        return val

# Global instance
locale_manager = LocaleManager()
