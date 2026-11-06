import json
from offtec.core.config import LOCALE_DIR

LANGUAGES = {"pt_BR":"language.pt", "en":"language.en", "ar":"language.ar", "hi":"language.hi", "es":"language.es"}

class Translator:
    def __init__(self, lang="pt_BR"):
        self.lang = lang if lang in LANGUAGES else "pt_BR"
        self.catalogs = {}
        for code in LANGUAGES:
            try:
                self.catalogs[code] = json.loads((LOCALE_DIR / f"{code}.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self.catalogs[code] = {}
    def set_language(self, lang):
        if lang in LANGUAGES: self.lang = lang
    def t(self, key, **values):
        value = self.catalogs.get(self.lang, {}).get(key) or self.catalogs["pt_BR"].get(key, key)
        value=value.format(**values)
        # Isolate Arabic phrases so adjacent Latin labels/identifiers keep order
        # in terminals that implement Unicode bidirectional controls.
        return "\u2067"+value+"\u2069" if self.lang=="ar" else value
