import i18n, { LANGUAGE_STORAGE_KEY, type Language } from "./index";

/** Applies a language in the UI and remembers it in this browser. */
export function applyLanguage(lang: Language, { remember = true } = {}) {
  if (remember) {
    try {
      localStorage.setItem(LANGUAGE_STORAGE_KEY, lang);
    } catch {
      // storage unavailable (private mode) — the choice still applies for this tab
    }
  }
  if (i18n.language !== lang) void i18n.changeLanguage(lang);
}

export function currentLanguage(): Language {
  return i18n.language === "ru" ? "ru" : "en";
}

/** BCP-47 tag used for Intl formatting. */
export function intlLocale(lang: string = i18n.language): string {
  return lang === "ru" ? "ru-RU" : "en-US";
}
