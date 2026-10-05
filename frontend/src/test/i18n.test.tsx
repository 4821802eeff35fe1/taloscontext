import { describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import i18n, {
  LANGUAGE_STORAGE_KEY,
  browserLanguage,
  initialLanguage,
  languageFromLocale,
  storedLanguage,
} from "@/i18n";
import { applyLanguage } from "@/i18n/language";
import { auditActionLabel, notificationText, statusLabel } from "@/i18n/labels";
import { useLanguageSync } from "@/hooks/useLanguage";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ApiError, localizeApiError, endpoints, type User } from "@/lib/api";
import { dateTime, number, rub } from "@/lib/format";

/** Intl uses narrow/no-break spaces; compare with plain spaces. */
const plain = (s: string) => s.replace(/[\u00a0\u202f]/g, " ");

function Shell() {
  const { t } = useTranslation();
  return <nav>{t("nav.item.calendar")}</nav>;
}

describe("language rendering", () => {
  it("renders English by default", () => {
    render(<Shell />);
    expect(screen.getByText("Calendar")).toBeInTheDocument();
  });

  it("renders Russian", async () => {
    await act(() => applyLanguage("ru"));
    render(<Shell />);
    expect(screen.getByText("Календарь")).toBeInTheDocument();
  });

  it("switches a mounted UI without reload", async () => {
    render(
      <>
        <Shell />
        <StatusBadge status="PENDING_APPROVAL" />
      </>,
    );
    expect(screen.getByText("Pending approval")).toBeInTheDocument();
    await act(() => applyLanguage("ru"));
    expect(screen.getByText("Календарь")).toBeInTheDocument();
    expect(screen.getByText("Ожидает подтверждения")).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("ru");
  });
});

describe("language resolution", () => {
  it("persists an explicit choice for the next load", () => {
    applyLanguage("ru");
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe("ru");
    expect(storedLanguage()).toBe("ru");
    expect(initialLanguage()).toBe("ru");
  });

  it("maps browser locales: ru* -> ru, anything else -> en", () => {
    expect(languageFromLocale("ru")).toBe("ru");
    expect(languageFromLocale("ru-RU")).toBe("ru");
    expect(languageFromLocale("ru_UA")).toBe("ru");
    expect(languageFromLocale("en-GB")).toBe("en");
    expect(languageFromLocale("de-DE")).toBe("en");
    expect(languageFromLocale(undefined)).toBe("en");
  });

  it("falls back to the browser locale without a stored choice", () => {
    vi.spyOn(navigator, "languages", "get").mockReturnValue(["ru-RU", "en-US"]);
    expect(browserLanguage()).toBe("ru");
    expect(initialLanguage()).toBe("ru");
  });

  it("a manual choice beats the browser locale", () => {
    vi.spyOn(navigator, "languages", "get").mockReturnValue(["ru-RU"]);
    applyLanguage("en");
    expect(initialLanguage()).toBe("en");
  });

  it("the saved account preference beats the local choice", async () => {
    applyLanguage("ru");
    const update = vi.spyOn(endpoints, "updateMe");
    function Probe({ user }: { user: User }) {
      useLanguageSync(user);
      return <Shell />;
    }
    const client = new QueryClient();
    await act(async () => {
      render(
        <QueryClientProvider client={client}>
          <Probe user={{ id: "u1", email: "a@b.c", full_name: "", language: "en" } as User} />
        </QueryClientProvider>,
      );
    });
    expect(i18n.language).toBe("en");
    expect(screen.getByText("Calendar")).toBeInTheDocument();
    expect(update).not.toHaveBeenCalled();
  });

  it("an explicit pre-login choice is saved to an account without a preference", async () => {
    applyLanguage("ru");
    const update = vi.spyOn(endpoints, "updateMe").mockResolvedValue({} as User);
    function Probe({ user }: { user: User }) {
      useLanguageSync(user);
      return null;
    }
    await act(async () => {
      render(<Probe user={{ id: "u2", email: "a@b.c", full_name: "", language: null } as User} />);
    });
    expect(update).toHaveBeenCalledWith({ language: "ru" });
  });
});

describe("enum and error localization", () => {
  it("statuses use central mappings", async () => {
    await i18n.changeLanguage("ru");
    expect(statusLabel("PENDING_APPROVAL", "content")).toBe("Ожидает подтверждения");
    expect(statusLabel("NO_POST_PERMISSION", "channel")).toBe("Нет прав на публикацию");
    expect(statusLabel("SOME_NEW_STATUS")).toBe("Some new status");
  });

  it("audit actions are machine values rendered per language", async () => {
    await i18n.changeLanguage("ru");
    expect(auditActionLabel("content.created")).toBe("Пост создан");
    expect(auditActionLabel("content.approved")).toBe("Пост подтверждён");
    expect(auditActionLabel("telegram.account_connected")).toBe("Telegram-аккаунт добавлен");
    expect(auditActionLabel("content.ai_shorten")).toBe("AI-правка: Сокращение");
  });

  it("API errors are localized by code with parameters", async () => {
    await i18n.changeLanguage("ru");
    expect(localizeApiError("AUTH_INVALID_CREDENTIALS", {}, "Invalid email or password")).toBe(
      "Неверный email или пароль.",
    );
    expect(
      plain(localizeApiError("BUDGET_EXCEEDED", { kind: "daily", spent: "120", limit: "100" }, "x")),
    ).toBe("Бюджет на AI исчерпан (дневной): потрачено 120,00 ₽ из 100,00 ₽.");
    expect(localizeApiError("AUTH_RATE_LIMITED", { retry_after: 30 }, "x")).toBe(
      "Слишком много попыток входа. Повторите через 30 с.",
    );
    // Unknown codes keep the server text rather than hiding it.
    expect(localizeApiError("SOMETHING_NEW", {}, "Server said no")).toBe("Server said no");
    const error = new ApiError(403, "Not a member", null, null, "WORKSPACE_ACCESS_DENIED");
    expect(error.message).toBe("У вас нет доступа к этому рабочему пространству.");
  });

  it("notifications render from kind and metadata", async () => {
    await i18n.changeLanguage("ru");
    const text = notificationText({
      kind: "post.partially_published",
      message: "English fallback",
      metadata: { title: "Новости", published: 2, total: 5, failed: 3 },
    });
    expect(text).toBe("«Новости» опубликован в 2 из 5 каналов; ошибок: 3.");
    // Old rows without parameters keep their stored text.
    expect(notificationText({ kind: "post.published", message: "Legacy", metadata: {} })).toBe("Legacy");
  });
});

describe("formatting", () => {
  it("dates follow the UI language and keep UTC input", async () => {
    const iso = "2026-10-05T23:42:00Z";
    expect(plain(dateTime(iso, "UTC", "full"))).toBe("Oct 5, 2026, 11:42 PM");
    await i18n.changeLanguage("ru");
    expect(plain(dateTime(iso, "UTC", "full"))).toBe("5 окт. 2026 г., 23:42");
    expect(plain(dateTime(iso, "Europe/Moscow", "time"))).toBe("02:42");
  });

  it("numbers and money", async () => {
    expect(number(1250430)).toBe("1,250,430");
    expect(plain(rub("1249.52"))).toBe("RUB 1,249.52");
    await i18n.changeLanguage("ru");
    expect(plain(number(1250430))).toBe("1 250 430");
    expect(plain(rub("1249.52"))).toBe("1 249,52 ₽");
  });

  it("Russian plurals: пост / канал", async () => {
    await i18n.changeLanguage("ru");
    const t = i18n.getFixedT("ru", "common");
    expect(t("count.posts", { count: 1 })).toBe("1 пост");
    expect(t("count.posts", { count: 2 })).toBe("2 поста");
    expect(t("count.posts", { count: 5 })).toBe("5 постов");
    expect(t("count.posts", { count: 21 })).toBe("21 пост");
    expect(t("count.channels", { count: 1 })).toBe("1 канал");
    expect(t("count.channels", { count: 3 })).toBe("3 канала");
    expect(t("count.channels", { count: 11 })).toBe("11 каналов");
    expect(plain(t("count.posts", { count: 1250 }))).toBe("1 250 постов");
  });

  it("English plurals", () => {
    const t = i18n.getFixedT("en", "common");
    expect(t("count.posts", { count: 1 })).toBe("1 post");
    expect(t("count.posts", { count: 2 })).toBe("2 posts");
    expect(t("count.channels", { count: 1250 })).toBe("1,250 channels");
  });
});
