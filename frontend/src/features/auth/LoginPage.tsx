import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { endpoints, errorText } from "@/lib/api";
import { Segmented } from "@/components/ui/forms";
import { storedLanguage, type Language } from "@/i18n";
import { useLanguage } from "@/hooks/useLanguage";

export function LoginPage() {
  const { t } = useTranslation("auth");
  const { language, setLanguage } = useLanguage();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [workspaceName, setWorkspaceName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const client = useQueryClient();
  const navigate = useNavigate();

  const mutation = useMutation({
    mutationFn: async () => {
      if (mode === "login") {
        return endpoints.login(email, password);
      }
      return endpoints.register({
        email,
        password,
        full_name: fullName,
        workspace_name: workspaceName,
        // Only an explicit choice becomes the account preference.
        language: storedLanguage(),
      });
    },
    onSuccess: async () => {
      setError(null);
      await client.invalidateQueries({ queryKey: ["me"] });
      navigate({ to: "/" });
    },
    onError: (err) => setError(errorText(err)),
  });

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface px-4">
      <div className="card w-full max-w-sm p-6">
        <div className="mb-6 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="h-6 w-6 rounded-md bg-accent" />
            <span className="text-sm font-semibold">ChannelOS</span>
          </div>
          <Segmented<Language>
            ariaLabel={t("common:language.label")}
            value={language}
            onChange={(lang) => setLanguage(lang, { signedIn: false })}
            options={[
              { value: "en", label: "EN" },
              { value: "ru", label: "RU" },
            ]}
          />
        </div>
        <h1 className="text-lg font-semibold text-ink">
          {mode === "login" ? t("signIn") : t("createWorkspace")}
        </h1>
        <form
          className="mt-5 space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            mutation.mutate();
          }}
        >
          {mode === "register" && (
            <div>
              <label className="label" htmlFor="auth-full-name">
                {t("fullName")}
              </label>
              <input id="auth-full-name" className="input" autoComplete="name" value={fullName}
                onChange={(e) => setFullName(e.target.value)} />
            </div>
          )}
          <div>
            <label className="label" htmlFor="auth-email">
              {t("email")}
            </label>
            <input id="auth-email" type="email" required autoComplete="email" className="input" value={email}
              onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="auth-password">
              {t("password")}
            </label>
            <input id="auth-password" type="password" required minLength={8}
              autoComplete={mode === "login" ? "current-password" : "new-password"} className="input"
              value={password} onChange={(e) => setPassword(e.target.value)} />
            {mode === "register" && <p className="mt-1 text-xs text-ink-faint">{t("passwordHint")}</p>}
          </div>
          {mode === "register" && (
            <div>
              <label className="label" htmlFor="auth-workspace-name">
                {t("workspaceName")}
              </label>
              <input id="auth-workspace-name" required className="input" value={workspaceName}
                onChange={(e) => setWorkspaceName(e.target.value)} />
            </div>
          )}

          {error && <p role="alert" className="text-sm text-danger">{error}</p>}

          <button type="submit" className="btn-primary w-full" disabled={mutation.isPending}>
            {mode === "login" ? t("signIn") : t("createAccount")}
          </button>
        </form>

        <button
          className="mt-4 text-xs text-ink-muted hover:text-ink"
          onClick={() => {
            setError(null);
            setMode(mode === "login" ? "register" : "login");
          }}
        >
          {mode === "login" ? t("switchToRegister") : t("switchToLogin")}
        </button>
      </div>
    </div>
  );
}
