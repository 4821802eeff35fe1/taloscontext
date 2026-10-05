/**
 * i18n bootstrap. Translations live in ./locales/<lang>/<namespace>.json and
 * are bundled (no runtime fetch), so the first paint is already localized.
 *
 * Language resolution (highest first):
 *   1. the signed-in user's saved preference (applied by useLanguageSync)
 *   2. an explicit choice stored in localStorage
 *   3. the browser locale (ru, ru-RU, ru-* -> Russian, anything else -> English)
 *   4. English
 */
import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import enAi from "./locales/en/ai.json";
import enAnalytics from "./locales/en/analytics.json";
import enAuth from "./locales/en/auth.json";
import enAutomation from "./locales/en/automation.json";
import enChannels from "./locales/en/channels.json";
import enCommon from "./locales/en/common.json";
import enContent from "./locales/en/content.json";
import enDashboard from "./locales/en/dashboard.json";
import enErrors from "./locales/en/errors.json";
import enMedia from "./locales/en/media.json";
import enSettings from "./locales/en/settings.json";
import enSystem from "./locales/en/system.json";
import ruAi from "./locales/ru/ai.json";
import ruAnalytics from "./locales/ru/analytics.json";
import ruAuth from "./locales/ru/auth.json";
import ruAutomation from "./locales/ru/automation.json";
import ruChannels from "./locales/ru/channels.json";
import ruCommon from "./locales/ru/common.json";
import ruContent from "./locales/ru/content.json";
import ruDashboard from "./locales/ru/dashboard.json";
import ruErrors from "./locales/ru/errors.json";
import ruMedia from "./locales/ru/media.json";
import ruSettings from "./locales/ru/settings.json";
import ruSystem from "./locales/ru/system.json";

export const SUPPORTED_LANGUAGES = ["en", "ru"] as const;
export type Language = (typeof SUPPORTED_LANGUAGES)[number];
export const FALLBACK_LANGUAGE: Language = "en";
export const LANGUAGE_STORAGE_KEY = "channelos-language";
export const NAMESPACES = [
  "common", "auth", "dashboard", "content", "channels", "media", "ai",
  "analytics", "automation", "settings", "system", "errors",
] as const;

export const resources = {
  en: {
    common: enCommon, auth: enAuth, dashboard: enDashboard, content: enContent, channels: enChannels,
    media: enMedia, ai: enAi, analytics: enAnalytics, automation: enAutomation, settings: enSettings,
    system: enSystem, errors: enErrors,
  },
  ru: {
    common: ruCommon, auth: ruAuth, dashboard: ruDashboard, content: ruContent, channels: ruChannels,
    media: ruMedia, ai: ruAi, analytics: ruAnalytics, automation: ruAutomation, settings: ruSettings,
    system: ruSystem, errors: ruErrors,
  },
} as const;

export function isLanguage(value: unknown): value is Language {
  return typeof value === "string" && (SUPPORTED_LANGUAGES as readonly string[]).includes(value);
}

/** Maps a BCP-47 tag to a supported language: ru / ru-RU / ru-* -> ru, everything else -> en. */
export function languageFromLocale(tag: string | null | undefined): Language {
  return tag && tag.toLowerCase().split(/[-_]/)[0] === "ru" ? "ru" : "en";
}

export function storedLanguage(): Language | null {
  try {
    const value = localStorage.getItem(LANGUAGE_STORAGE_KEY);
    return isLanguage(value) ? value : null;
  } catch {
    return null;
  }
}

export function browserLanguage(): Language {
  const langs = typeof navigator !== "undefined" ? (navigator.languages?.length ? navigator.languages : [navigator.language]) : [];
  return languageFromLocale(langs[0]);
}

export function initialLanguage(): Language {
  return storedLanguage() ?? browserLanguage();
}

i18n.use(initReactI18next).init({
  resources,
  lng: initialLanguage(),
  fallbackLng: FALLBACK_LANGUAGE,
  supportedLngs: SUPPORTED_LANGUAGES,
  ns: NAMESPACES,
  defaultNS: "common",
  interpolation: { escapeValue: false }, // React escapes output
  returnNull: false,
  react: { useSuspense: false },
});

if (typeof document !== "undefined") {
  document.documentElement.lang = i18n.language;
  i18n.on("languageChanged", (lng) => {
    document.documentElement.lang = lng;
  });
}

export default i18n;
