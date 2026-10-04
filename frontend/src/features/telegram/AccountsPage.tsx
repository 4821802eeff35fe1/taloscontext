import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { endpoints, ApiError, type TelegramAccount } from "@/lib/api";
import { Card, EmptyState } from "@/components/ui/Card";
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
  const client = useQueryClient();
  const [step, setStep] = useState<"phone" | "code" | "2fa">("phone");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [flowId, setFlowId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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
        setError(flow.error ?? "Telegram refused to send a code");
        return;
      }
      setFlowId(flow.flow_id);
      setStep("code");
      setError(null);
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : "Failed to send code"),
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
        setError(flow.error ?? `Login is ${flow.state.toLowerCase()}`);
        return;
      }
      client.invalidateQueries({
        queryKey: ["telegram-accounts", workspaceId],
      });
      onOpenChange(false);
      reset();
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : "Invalid code"),
  });

  const submit2FA = useMutation({
    mutationFn: () =>
      endpoints.submitTelegramPassword(workspaceId, flowId!, password),
    onSuccess: (flow) => {
      if (flow.state !== "COMPLETED") {
        setError(flow.error ?? `Login is ${flow.state.toLowerCase()}`);
        return;
      }
      client.invalidateQueries({
        queryKey: ["telegram-accounts", workspaceId],
      });
      onOpenChange(false);
      reset();
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : "Invalid password"),
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        onOpenChange(v);
        if (!v) reset();
      }}
      title="Add Telegram account"
      description={
        step === "phone"
          ? "Enter the phone number of the Telegram account you want to connect."
          : step === "code"
            ? "Enter the verification code sent to that account."
            : "This account has Two-Step Verification enabled. Enter the password."
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
            <label className="label">Phone number</label>
            <input
              className="input"
              placeholder="+15551234567"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              required
            />
          </div>
          {error && <p className="text-sm text-danger">{error}</p>}
          <button
            className="btn-primary w-full"
            disabled={startLogin.isPending}
          >
            Send code
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
            <label className="label">Verification code</label>
            <input
              aria-label="Verification code"
              className="input"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              required
              autoFocus
            />
          </div>
          {error && <p className="text-sm text-danger">{error}</p>}
          <button
            className="btn-primary w-full"
            disabled={submitCode.isPending}
          >
            Verify
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
            <label className="label">Two-step verification password</label>
            <input
              type="password"
              className="input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoFocus
            />
          </div>
          {error && <p className="text-sm text-danger">{error}</p>}
          <button className="btn-primary w-full" disabled={submit2FA.isPending}>
            Confirm
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
  const client = useQueryClient();

  const [confirm, setConfirm] = useState<"disconnect" | "delete" | null>(null);
  const refresh = useMutation({
    mutationFn: () =>
      endpoints.refreshTelegramChannels(workspaceId, account.id),
    onSuccess: () => {
      toast.success("Channel import queued");
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
      <div>
        <p className="text-sm text-ink">
          {account.first_name} {account.last_name}{" "}
          <span className="text-ink-faint">
            {account.username ? `@${account.username}` : ""}
          </span>
        </p>
        <p className="text-xs text-ink-faint">{account.phone_masked}</p>
        {account.last_error && (
          <p className="mt-0.5 text-xs text-danger">{account.last_error}</p>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={account.status} />
        <button
          className="btn-ghost"
          title="Refresh channels"
          onClick={() => refresh.mutate()}
        >
          <Refresh className="h-4 w-4" />
        </button>
        <button
          className="btn-secondary"
          onClick={() => setConfirm("disconnect")}
        >
          Disconnect
        </button>
        <button className="btn-danger" onClick={() => setConfirm("delete")}>
          Delete
        </button>
      </div>
      <ConfirmDialog
        open={!!confirm}
        onOpenChange={(v) => !v && setConfirm(null)}
        title={
          confirm === "delete"
            ? "Delete this account?"
            : "Disconnect this account?"
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
  const [dialogOpen, setDialogOpen] = useState(
    new URLSearchParams(window.location.search).has("add"),
  );
  const accounts = useQuery({
    queryKey: ["telegram-accounts", workspaceId],
    queryFn: () => endpoints.telegramAccounts(workspaceId),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">Telegram accounts</h1>
        <button className="btn-primary" onClick={() => setDialogOpen(true)}>
          <Plus className="h-4 w-4" /> Add account
        </button>
      </div>

      <Card>
        {accounts.data && accounts.data.length > 0 ? (
          <div className="divide-y divide-surface-border">
            {accounts.data.map((a) => (
              <AccountRow key={a.id} workspaceId={workspaceId} account={a} />
            ))}
          </div>
        ) : (
          <EmptyState
            title="No Telegram accounts connected"
            description="Connect a Telegram user account to start importing channels you administer."
            action={
              <button
                className="btn-primary"
                onClick={() => setDialogOpen(true)}
              >
                Add account
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
