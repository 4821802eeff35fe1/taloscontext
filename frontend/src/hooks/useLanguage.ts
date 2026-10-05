import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { storedLanguage, type Language } from "@/i18n";
import { applyLanguage, currentLanguage } from "@/i18n/language";
import { endpoints, type User } from "@/lib/api";

/**
 * Keeps the UI language and the user's saved preference in sync:
 *  - a saved preference always wins (it's applied when the session loads);
 *  - an explicit choice made before signing in (stored locally) is saved to
 *    the account the first time it loads without a preference;
 *  - a language only inferred from the browser is never written to the account.
 */
export function useLanguageSync(user: User | undefined) {
  const synced = useRef<string | null>(null);
  useEffect(() => {
    if (!user || synced.current === user.id) return;
    synced.current = user.id;
    if (user.language) {
      applyLanguage(user.language);
    } else {
      const explicit = storedLanguage();
      if (explicit) void endpoints.updateMe({ language: explicit }).catch(() => undefined);
    }
  }, [user]);
}

/** Language switcher state: change applies instantly and persists locally and on the account. */
export function useLanguage() {
  const { i18n } = useTranslation();
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: (language: Language) => endpoints.updateMe({ language }),
    onSuccess: (user) => client.setQueryData(["me"], user),
  });
  return {
    language: (i18n.language === "ru" ? "ru" : "en") as Language,
    setLanguage: (lang: Language, { signedIn = true } = {}) => {
      if (lang === currentLanguage() && storedLanguage() === lang) return;
      applyLanguage(lang);
      if (signedIn) save.mutate(lang);
    },
    saving: save.isPending,
  };
}
