import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { endpoints, ApiError } from "@/lib/api";

export function LoginPage() {
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
      return endpoints.register(email, password, fullName, workspaceName);
    },
    onSuccess: async () => {
      setError(null);
      await client.invalidateQueries({ queryKey: ["me"] });
      navigate({ to: "/" });
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Could not reach the ChannelOS API — check that the backend is running.");
    },
  });

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface px-4">
      <div className="card w-full max-w-sm">
        <div className="mb-6 flex items-center gap-2">
          <div className="h-6 w-6 rounded-md bg-accent" />
          <span className="text-sm font-semibold">ChannelOS</span>
        </div>
        <h1 className="text-lg font-semibold text-ink">
          {mode === "login" ? "Sign in" : "Create workspace"}
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
              <label className="label">Full name</label>
              <input className="input" value={fullName} onChange={(e) => setFullName(e.target.value)} />
            </div>
          )}
          <div>
            <label className="label">Email</label>
            <input
              type="email"
              required
              className="input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div>
            <label className="label">Password</label>
            <input
              type="password"
              required
              minLength={8}
              className="input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          {mode === "register" && (
            <div>
              <label className="label">Workspace name</label>
              <input
                required
                className="input"
                value={workspaceName}
                onChange={(e) => setWorkspaceName(e.target.value)}
              />
            </div>
          )}

          {error && <p className="text-sm text-danger">{error}</p>}

          <button type="submit" className="btn-primary w-full" disabled={mutation.isPending}>
            {mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>

        <button
          className="mt-4 text-xs text-ink-muted hover:text-ink"
          onClick={() => setMode(mode === "login" ? "register" : "login")}
        >
          {mode === "login" ? "Need a workspace? Create one" : "Already have an account? Sign in"}
        </button>
      </div>
    </div>
  );
}
