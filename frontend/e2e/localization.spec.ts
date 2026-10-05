import { test, expect, type Page, type Cookie } from "@playwright/test";

const apiBase = process.env.E2E_API_URL || "http://localhost:8100";
const headers = { "X-ChannelOS-Client": "playwright" };
const password = "supersecret123";
let email: string, ws: string, cookies: Cookie[];

// English UI words that must not appear anywhere on a Russian page. Data on
// these pages is created in Russian below, so any hit is untranslated UI.
const ENGLISH_UI = [
  "Settings", "Calendar", "Channels", "Jobs", "Costs", "Overview", "Posts", "Notifications",
  "Save", "Delete", "Edit", "Cancel", "Create", "Add", "Search", "Loading", "Retry", "Refresh",
  "Upload", "Today", "Month", "Week", "Schedule", "Approve", "Reject", "Publish", "Sign out",
  "No channels", "No matching", "All statuses", "Spend", "Budget", "Forecast", "Language",
  "General", "Security", "Storage", "Members", "Previous", "Next",
];

async function expectNoEnglishUi(page: Page) {
  const text = await page.locator("body").innerText();
  const hits = ENGLISH_UI.filter((w) => new RegExp(`\\b${w}\\b`).test(text));
  expect(hits, `untranslated UI on ${page.url()}`).toEqual([]);
}

async function chooseLanguage(page: Page, label: "Interface language" | "Язык интерфейса", option: string) {
  await page.getByRole("combobox", { name: label }).click();
  await page.getByRole("option", { name: option, exact: true }).click();
}

async function meLanguage(page: Page) {
  const r = await page.request.get(apiBase + "/api/v1/auth/me");
  return (await r.json()).language;
}

test.describe.serial("localization", () => {
  test.beforeAll(async ({ browser }) => {
    email = `l10n-${Date.now()}@example.com`;
    const context = await browser.newContext();
    const r = await context.request.post(apiBase + "/api/v1/auth/register", {
      headers,
      data: { email, password, full_name: "Тестовый Пользователь", workspace_name: "Локализация" },
    });
    expect(r.ok(), await r.text()).toBeTruthy();
    ws = (await (await context.request.get(apiBase + "/api/v1/workspaces")).json())[0].id;
    cookies = await context.cookies();
    await context.close();
  });

  test.beforeEach(async ({ page }) => {
    await page.context().addCookies(cookies);
  });

  test("A: English → Russian in Settings, survives reload", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible();
    await chooseLanguage(page, "Interface language", "Русский");
    await expect(page.getByRole("heading", { name: "Настройки", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Календарь" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Каналы", exact: true })).toBeVisible();
    await expect.poll(() => meLanguage(page)).toBe("ru");
    await page.reload();
    await expect(page.getByRole("heading", { name: "Настройки", exact: true })).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("lang", "ru");
    // Saved on the account: a fresh browser (no localStorage) also opens in Russian.
    const fresh = await page.context().browser()!.newContext({ locale: "en-US" });
    await fresh.addCookies(cookies);
    const other = await fresh.newPage();
    await other.goto("/settings");
    await expect(other.getByRole("heading", { name: "Настройки", exact: true })).toBeVisible();
    await fresh.close();
  });

  test("B: Russian → English, survives reload", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Настройки", exact: true })).toBeVisible();
    await chooseLanguage(page, "Язык интерфейса", "English");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible();
    await expect.poll(() => meLanguage(page)).toBe("en");
    await page.reload();
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Calendar" })).toBeVisible();
    // back to Russian for the next scenarios
    await chooseLanguage(page, "Interface language", "Русский");
    await expect.poll(() => meLanguage(page)).toBe("ru");
  });

  test("C: Russian UI does not translate post content", async ({ page }) => {
    const r = await page.request.post(apiBase + `/api/v1/workspaces/${ws}/content`, {
      headers,
      data: { title: "Launch notes", telegram_html: "<p>Hello world, this post stays in English.</p>" },
    });
    expect(r.ok(), await r.text()).toBeTruthy();
    const post = await r.json();
    await page.goto(`/content?post=${post.id}`);
    await expect(page.getByRole("button", { name: "Отправить на подтверждение" })).toBeVisible();
    await expect(page.getByText("Hello world, this post stays in English.").first()).toBeVisible();
    await expect(page.getByText("Launch notes").first()).toBeVisible();
    const stored = await (await page.request.get(apiBase + `/api/v1/workspaces/${ws}/content/${post.id}`)).json();
    expect(stored.telegram_html).toContain("Hello world, this post stays in English.");
    expect(stored.title).toBe("Launch notes");
  });

  test("D: Russian pages have no untranslated UI", async ({ page }) => {
    for (const [path, heading] of [
      ["/calendar", "Календарь"],
      ["/channels", "Каналы"],
      ["/jobs", "Задачи"],
      ["/costs", "Расходы на AI"],
      ["/settings", "Настройки"],
    ]) {
      await page.goto(path);
      await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible();
      await page.waitForLoadState("networkidle");
      await expectNoEnglishUi(page);
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
        `horizontal overflow on ${path}`,
      ).toBeTruthy();
    }
    await page.setViewportSize({ width: 390, height: 844 });
    for (const path of ["/calendar", "/settings", "/jobs"]) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
        `horizontal overflow on mobile ${path}`,
      ).toBeTruthy();
    }
    await page.screenshot({ path: "test-results/l10n-settings-mobile-ru.png", fullPage: true });
  });
});
