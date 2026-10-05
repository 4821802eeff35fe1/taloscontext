import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { endpoints, errorText, type AuthFlow, type TelegramAccount } from "@/lib/api";
import { errorLabel, statusLabel } from "@/i18n/labels";
import { dateTime } from "@/lib/format";
import { Card, EmptyState } from "@/components/ui/Card";
import { ErrorState, SkeletonRows } from "@/components/ui/primitives";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Dialog } from "@/components/ui/Dialog";
import { ConfirmDialog } from "@/components/ui/overlays";
import { toast } from "@/components/ui/toast";
import { Plus, Refresh } from "@/components/ui/icons";

function AddAccountDialog({
  workspaceId,
  open,
  onOpenChange,
}: {
  workspaceId: string;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const { t } = useTranslation("channels");
  const client = useQueryClient();
  const [step, setStep] = useState<"phone" | "code" | "2fa">("phone");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [flowId, setFlowId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Flow failures carry a machine code; the server message is only a fallback.
  const flowError = (flow: AuthFlow) =>
    flow.error_code
      ? errorLabel(flow.error_code, { seconds: flow.wait_seconds ?? 0 })
      : flow.state === "EXPIRED"
        ? t("accounts.flow.expired")
        : t("accounts.flow.failed", { state: statusLabel(flow.state, "flow") });

  const reset = () => {
    setStep("phone");
    setPhone("");
    setCode("");
    setPassword("");
    setFlowId(null);
    setError(null);
  };

  const startLogin = useMutation({
    mutationFn: () => endpoints.startTelegramAuth(workspaceId, phone),
    onSuccess: (flow) => {
      if (flow.state === "FAILED") {
        setError(flow.error_code ? flowError(flow) : t("accounts.flow.codeRefused"));
        return;
      }
      setFlowId(flow.flow_id);
      setStep("code");
      setError(null);
    },
    onError: (e) => setError(errorText(e)),
  });

  const submitCode = useMutation({
    mutationFn: () => endpoints.submitTelegramCode(workspaceId, flowId!, code),
    onSuccess: (flow) => {
      if (flow.state === "PASSWORD_REQUIRED") {
        setStep("2fa");
        setError(null);
        return;
      }
      if (flow.state !== "COMPLETED") {
        setError(flowError(flow));
        return;
      }
      client.invalidateQueries({
        queryKey: ["telegram-accounts", workspaceId],
      });
      onOpenChange(false);
      reset();
    },
    onError: (e) => setError(errorText(e)),
  });

  const submit2FA = useMutation({
    mutationFn: () =>
      endpoints.submitTelegramPassword(workspaceId, flowId!, password),
    onSuccess: (flow) => {
      if (flow.state !== "COMPLETED") {
        setError(flowError(flow));
        return;
      }
      client.invalidateQueries({
        queryKey: ["telegram-accounts", workspaceId],
      });
      onOpenChange(false);
      reset();
    },
    onError: (e) => setError(errorText(e)),
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        onOpenChange(v);
        if (!v) reset();
      }}
      title={t("accounts.add.title")}
      description={
        step === "phone"
          ? t("accounts.add.phoneHint")
          : step === "code"
            ? t("accounts.add.codeHint")
            : t("accounts.add.passwordHint")
      }
    >
      {step === "phone" && (
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            startLogin.mutate();
          }}
        >
          <div>
            <label className="label" htmlFor="tg-phone">{t("accounts.add.phone")}</label>
            <input
              id="tg-phone"
              type="tel"
              autoComplete="tel"
              className="input"
              placeholder="+15551234567"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              required
            />
          </div>
          {error && <p role="alert" className="text-sm text-danger">{error}</p>}
          <button
            className="btn-primary w-full"
            disabled={startLogin.isPending}
          >
            {t("accounts.add.sendCode")}
          </button>
        </form>
      )}

      {step === "code" && (
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            submitCode.mutate();
          }}
        >
          <div>
            <label className="label" htmlFor="tg-code">{t("accounts.add.code")}</label>
            <input
              id="tg-code"
              inputMode="numeric"
              autoComplete="one-time-code"
              className="input"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              required
              autoFocus
            />
          </div>
          {error && <p role="alert" className="text-sm text-danger">{error}</p>}
          <button
            className="btn-primary w-full"
            disabled={submitCode.isPending}
          >
            {t("accounts.add.verify")}
          </button>
        </form>
      )}

      {step === "2fa" && (
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            submit2FA.mutate();
          }}
        >
          <div>
            <label className="label" htmlFor="tg-password">{t("accounts.add.password")}</label>
            <input
              id="tg-password"
              type="password"
              autoComplete="current-password"
              className="input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoFocus
            />
          </div>
          {error && <p role="alert" className="text-sm text-danger">{error}</p>}
          <button className="btn-primary w-full" disabled={submit2FA.isPending}>
            {t("common:action.confirm")}
          </button>
        </form>
      )}
    </Dialog>
  );
}

function AccountRow({
  workspaceId,
  account,
}: {
  workspaceId: string;
  account: TelegramAccount;
}) {
  const { t } = useTranslation("channels");
  const client = useQueryClient();

  const [confirm, setConfirm] = useState<"disconnect" | "delete" | null>(null);
  const refresh = useMutation({
    mutationFn: () =>
      endpoints.refreshTelegramChannels(workspaceId, account.id),
    onSuccess: () => {
      toast.success(t("accounts.importQueued"));
      void client.invalidateQueries({ queryKey: ["channels", workspaceId] });
    },
    onError: (e) => toast.error(e.message),
  });
  const disconnect = useMutation({
    mutationFn: () =>
      endpoints.disconnectTelegramAccount(workspaceId, account.id),
    onSuccess: () =>
      client.invalidateQueries({
        queryKey: ["telegram-accounts", workspaceId],
      }),
  });
  const remove = useMutation({
    mutationFn: () => endpoints.deleteTelegramAccount(workspaceId, account.id),
    onSuccess: () =>
      client.invalidateQueries({
        queryKey: ["telegram-accounts", workspaceId],
      }),
  });

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 py-3">
      <div className="min-w-0">
        <p className="text-sm text-ink">
          {account.first_name} {account.last_name}{" "}
          <span className="text-ink-faint">
            {account.username ? `@${account.username}` : ""}
          </span>
        </p>
        <p className="text-xs text-ink-faint">
          {account.phone_masked} · {t("common:count.channels", { count: account.channel_count })}
        </p>
        {account.flood_wait_until && new Date(account.flood_wait_until) > new Date() && (
          <p className="mt-0.5 text-xs text-warning">
            {t("accounts.floodUntil", { time: dateTime(account.flood_wait_until) })}
          </p>
        )}
        {account.last_error && (
          <p className="mt-0.5 break-words text-xs text-danger">
            {t("accounts.lastError")}: <span className="font-mono">{account.last_error}</span>
          </p>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={account.status} domain="account" />
        <button
          className="btn-ghost"
          title={t("accounts.refreshChannels")}
          aria-label={t("accounts.refreshChannels")}
          disabled={refresh.isPending}
          onClick={() => refresh.mutate()}
        >
          <Refresh className="h-4 w-4" aria-hidden />
        </button>
        <button
          className="btn-secondary"
          onClick={() => setConfirm("disconnect")}
        >
          {t("accounts.disconnect")}
        </button>
        <button className="btn-danger" onClick={() => setConfirm("delete")}>
          {t("common:action.delete")}
        </button>
      </div>
      <ConfirmDialog
        open={!!confirm}
        onOpenChange={(v) => !v && setConfirm(null)}
        title={
          confirm === "delete"
            ? t("accounts.deleteConfirm")
            : t("accounts.disconnectConfirm")
        }
        destructive
        onConfirm={() => {
          if (confirm === "delete") remove.mutate();
          else disconnect.mutate();
          setConfirm(null);
        }}
      />
    </div>
  );
}

export function AccountsPage({ workspaceId }: { workspaceId: string }) {
  const { t } = useTranslation("channels");
  const [dialogOpen, setDialogOpen] = useState(
    new URLSearchParams(window.location.search).has("add"),
  );
  const accounts = useQuery({
    queryKey: ["telegram-accounts", workspaceId],
    queryFn: () => endpoints.telegramAccounts(workspaceId),
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold text-ink">{t("accounts.title")}</h1>
        <button className="btn-primary" onClick={() => setDialogOpen(true)}>
          <Plus className="h-4 w-4" aria-hidden /> {t("accounts.addAccount")}
        </button>
      </div>

      <Card>
        {accounts.isPending ? (
          <SkeletonRows />
        ) : accounts.isError ? (
          <ErrorState error={accounts.error} onRetry={() => void accounts.refetch()} />
        ) : accounts.data.length > 0 ? (
          <div className="divide-y divide-surface-border">
            {accounts.data.map((a) => (
              <AccountRow key={a.id} workspaceId={workspaceId} account={a} />
            ))}
          </div>
        ) : (
          <EmptyState
            title={t("accounts.empty.title")}
            description={t("accounts.empty.description")}
            action={
              <button
                className="btn-primary"
                onClick={() => setDialogOpen(true)}
              >
                {t("accounts.addAccount")}
              </button>
            }
          />
        )}
      </Card>

      <AddAccountDialog
        workspaceId={workspaceId}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
      />
    </div>
  );
}
