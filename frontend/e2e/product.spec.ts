import {
  test,
  expect,
  type Page,
  type APIRequestContext,
  type Cookie,
} from "@playwright/test";
const apiBase = process.env.E2E_API_URL || "http://localhost:8100";
const headers = { "X-ChannelOS-Client": "playwright" };
let ws: string, email: string, cookies: Cookie[];
const password = "supersecret123";
async function post(request: APIRequestContext, path: string, data?: unknown) {
  const r = await request.post(apiBase + "/api/v1" + path, { headers, data });
  expect(r.ok(), await r.text()).toBeTruthy();
  return r.status() === 204 ? undefined : r.json();
}
async function get(request: APIRequestContext, path: string) {
  const r = await request.get(apiBase + "/api/v1" + path);
  expect(r.ok(), await r.text()).toBeTruthy();
  return r.json();
}
async function open(page: Page, path: string) {
  await page.goto(path);
  await expect(page.getByText("Dev mode:", { exact: false })).toBeVisible();
}
test.describe.serial("daily product flow with fake providers", () => {
  test("register and login → dashboard", async ({ page }) => {
    email = `e2e-${Date.now()}@example.com`;
    await page.goto("/login");
    await page
      .getByRole("button", { name: "Need a workspace? Create one" })
      .click();
    await page.getByLabel("Full name", { exact: true }).fill("E2E User");
    await page.getByLabel("Email", { exact: true }).fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page
      .getByLabel("Workspace name", { exact: true })
      .fill("E2E Network");
    await page
      .getByRole("button", { name: "Create account", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Overview", exact: true }),
    ).toBeVisible();
    ws = (await get(page.request, "/workspaces"))[0].id;
    await page.getByRole("button", { name: "Sign out", exact: true }).click();
    await page.getByLabel("Email", { exact: true }).fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Overview", exact: true }),
    ).toBeVisible();
    cookies = await page.context().cookies();
  });
  test.beforeEach(async ({ page }, info) => {
    if (info.title.startsWith("register")) return;
    await page.context().addCookies(cookies);
  });
  test("fake account → import five channels → create channel set", async ({
    page,
  }) => {
    await open(page, "/accounts?add=1");
    await page.getByPlaceholder("+15551234567").fill("+15551234567");
    await page.getByRole("button", { name: "Send code", exact: true }).click();
    await page.getByLabel("Verification code", { exact: true }).fill("00000");
    await page.getByRole("button", { name: "Verify", exact: true }).click();
    await expect
      .poll(
        async () =>
          (await get(page.request, `/workspaces/${ws}/channels`)).length,
      )
      .toBe(5);
    await open(page, "/channel-sets?create=1");
    await page.getByLabel("Name", { exact: true }).fill("Five channels");
    const checks = page.getByRole("dialog").getByRole("checkbox");
    for (let i = 0; i < 5; i++) await checks.nth(i).check();
    await page
      .getByRole("button", { name: "Create channel set", exact: true })
      .click();
    await expect(page.getByText("5 / 5 ready")).toBeVisible();
  });
  test("AI generate → transform → version history → approve → worker publishes 5", async ({
    page,
  }) => {
    await open(page, "/content?generate=1");
    await page
      .getByLabel("Instruction", { exact: true })
      .fill("Educational post about CTR and conversion rates");
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("combobox").click();
    await page
      .getByRole("option", { name: "Five channels", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Generate post", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Submit for approval", exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Shorten", exact: true }).click();
    await expect
      .poll(async () => {
        const r = await get(
          page.request,
          `/workspaces/${ws}/jobs?type=AI_REWRITE`,
        );
        return r.items[0]?.status;
      })
      .toBe("SUCCESS");
    await page
      .getByRole("button", { name: "Version history", exact: true })
      .click();
    await expect(page.getByRole("dialog").getByText(/shorten/)).toBeVisible();
    await page.getByRole("button", { name: "Close", exact: true }).click();
    await page
      .getByRole("button", { name: "Submit for approval", exact: true })
      .click();
    await page.getByRole("button", { name: "Approve", exact: true }).click();
    await page
      .getByRole("button", { name: "Publish now", exact: true })
      .click();
    await expect(
      page.getByText("5 / 5 published", { exact: true }),
    ).toBeVisible({ timeout: 45000 });
    const items = await get(page.request, `/workspaces/${ws}/content`);
    expect(items.items[0].status).toBe("PUBLISHED");
  });
  test("partial failure → retry failed leaves successes untouched", async ({
    page,
  }) => {
    const sets = await get(page.request, `/workspaces/${ws}/channel-sets`);
    const set = await get(
      page.request,
      `/workspaces/${ws}/channel-sets/${sets[0].id}`,
    );
    // Fake channel entity ids use 1001..1005, see fake provider.
    const control = await page.request.put(
      apiBase + `/api/v1/workspaces/${ws}/dev/fake-telegram/failures`,
      { headers, data: { entity_ids: [1002] } },
    );
    expect(control.ok()).toBeTruthy();
    const c = await post(page.request, `/workspaces/${ws}/content`, {
      title: "Partial failure test",
      telegram_html: "A post for retry verification",
      channel_set_id: set.id,
    });
    await post(page.request, `/workspaces/${ws}/content/${c.id}/submit`);
    await post(page.request, `/workspaces/${ws}/content/${c.id}/approve`);
    await post(page.request, `/workspaces/${ws}/content/${c.id}/publish-now`);
    await open(page, `/content?post=${c.id}`);
    await expect(
      page.getByText("4 / 5 published", { exact: true }),
    ).toBeVisible({ timeout: 45000 });
    const before = (
      await get(
        page.request,
        `/workspaces/${ws}/distributions?content_id=${c.id}`,
      )
    )[0];
    await page.request.put(
      apiBase + `/api/v1/workspaces/${ws}/dev/fake-telegram/failures`,
      { headers, data: { entity_ids: [] } },
    );
    await page
      .getByRole("button", { name: "Retry 1 failed", exact: true })
      .click();
    await expect(
      page.getByText("5 / 5 published", { exact: true }),
    ).toBeVisible({ timeout: 45000 });
    const after = (
      await get(
        page.request,
        `/workspaces/${ws}/distributions?content_id=${c.id}`,
      )
    )[0];
    for (const pub of before.publications.filter(
      (p: { status: string }) => p.status === "SUCCESS",
    )) {
      expect(
        after.publications.find((p: { id: string }) => p.id === pub.id)
          .telegram_message_id,
      ).toBe(pub.telegram_message_id);
    }
  });
  test("calendar drag persists reschedule and keyboard change time works", async ({
    page,
  }) => {
    const set = (await get(page.request, `/workspaces/${ws}/channel-sets`))[0];
    const c = await post(page.request, `/workspaces/${ws}/content`, {
      title: "Calendar drag test",
      telegram_html: "Calendar post",
      channel_set_id: set.id,
    });
    await post(page.request, `/workspaces/${ws}/content/${c.id}/submit`);
    await post(page.request, `/workspaces/${ws}/content/${c.id}/approve`);
    const at = new Date();
    at.setDate(at.getDate() + 2);
    at.setHours(12, 0, 0, 0);
    await post(page.request, `/workspaces/${ws}/content/${c.id}/schedule`, {
      scheduled_at: at.toISOString(),
    });
    await open(page, "/calendar");
    const handle = page.getByRole("button", {
      name: "Move Calendar drag test",
      exact: true,
    });
    await expect(handle).toBeVisible();
    const source = await handle.boundingBox(),
      target = await page
        .getByTestId("calendar-day")
        .filter({ hasText: "Calendar drag test" })
        .locator("xpath=following-sibling::div[1]")
        .boundingBox();
    expect(source).not.toBeNull();
    expect(target).not.toBeNull();
    await page.mouse.move(
      source!.x + source!.width / 2,
      source!.y + source!.height / 2,
    );
    await page.mouse.down();
    await page.mouse.move(
      target!.x + target!.width / 2,
      target!.y + target!.height / 2,
      { steps: 20 },
    );
    await page.mouse.up();
    await expect
      .poll(async () =>
        new Date(
          (await get(page.request, `/workspaces/${ws}/content/${c.id}`))
            .scheduled_at,
        ).getTime(),
      )
      .not.toBe(at.getTime());
    await page
      .getByTestId("calendar-day")
      .filter({ hasText: "Calendar drag test" })
      .getByRole("button", { name: "Change time" })
      .click();
    await expect(
      page.getByRole("dialog", { name: "Reschedule post" }),
    ).toBeVisible();
  });
  test("knowledge, tone and schedule forms persist through the UI", async ({
    page,
  }) => {
    await open(page, "/knowledge");
    await page.getByRole("button", { name: "Add entry", exact: true }).click();
    await page.getByLabel("Entry title").fill("Current support contact");
    await page
      .getByLabel("Entry text")
      .fill("Support email: support@example.com");
    await page.getByRole("button", { name: "Save entry", exact: true }).click();
    await expect(
      page.getByRole("button", {
        name: "Current support contact",
        exact: true,
      }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Preview", exact: true }).click();
    await expect(
      page
        .getByRole("dialog")
        .getByText("Support email: support@example.com", { exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Close", exact: true }).click();
    await open(page, "/tone");
    await page
      .getByRole("button", { name: "Create profile", exact: true })
      .click();
    await page
      .getByRole("dialog")
      .getByLabel("name", { exact: true })
      .fill("Editorial voice");
    await page
      .getByRole("button", { name: "Save profile", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Editorial voice", exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Make default", exact: true })
      .click();
    await expect(
      page.getByText("Editorial voice · Workspace default", { exact: true }),
    ).toBeVisible();
    await open(page, "/schedules");
    await page
      .getByRole("button", { name: "Create schedule", exact: true })
      .click();
    await page
      .getByRole("dialog")
      .getByLabel("Name", { exact: true })
      .fill("Daily editorial");
    await page
      .getByRole("button", { name: "Preview slots", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Save schedule", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Daily editorial", exact: true }),
    ).toBeVisible();
  });
  test("settings, knowledge, tone, series, audit, jobs, palette and mobile render", async ({
    page,
  }) => {
    for (const [path, title] of [
      ["/settings", "Settings"],
      ["/knowledge", "Knowledge"],
      ["/tone", "Tone of voice"],
      ["/series", "Series"],
      ["/sources", "Sources"],
      ["/ideas", "Ideas inbox"],
      ["/jobs", "Jobs"],
      ["/audit", "Audit log"],
      ["/notifications", "Notifications"],
    ]) {
      await open(page, path);
      await expect(
        page.getByRole("heading", { name: title, exact: true }).first(),
      ).toBeVisible();
    }
    await page.keyboard.press("Control+k");
    await expect(
      page.getByRole("dialog", { name: "Commands and search" }),
    ).toBeVisible();
    await page.getByLabel("Search commands and posts").fill("calendar");
    await page
      .getByRole("option", { name: "Open Calendar", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Calendar", exact: true }),
    ).toBeVisible();
    await expect(page.getByTestId("calendar-day").first()).toBeVisible();
    await page.screenshot({
      path: "test-results/ux-calendar-desktop.png",
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(
      page.getByRole("button", { name: "Open navigation" }),
    ).toBeVisible();
    await page.screenshot({
      path: "test-results/ux-calendar-mobile.png",
      fullPage: false,
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
  });
  test("budget exhausted blocks AI and foreign workspace access is refused", async ({
    page,
  }) => {
    const update = await page.request.put(
      apiBase + `/api/v1/workspaces/${ws}/settings/budget`,
      {
        headers,
        data: {
          daily_budget_rub: "0",
          monthly_budget_rub: "0",
          max_cost_per_post_rub: "0",
          budget_warning_pct: 80,
        },
      },
    );
    expect(update.ok()).toBeTruthy();
    await open(page, "/content?generate=1");
    await page.getByLabel("Instruction").fill("Blocked by budget");
    await page
      .getByRole("button", { name: "Generate post", exact: true })
      .click();
    await expect(
      page
        .getByRole("dialog")
        .getByText(/budget/i)
        .last(),
    ).toBeVisible();
    const stranger = "00000000-0000-4000-8000-000000000001";
    expect(
      (
        await page.request.get(
          apiBase + `/api/v1/workspaces/${stranger}/content`,
        )
      ).status(),
    ).toBe(404);
  });
});
