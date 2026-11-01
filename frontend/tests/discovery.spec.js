import { test, expect } from "@playwright/test";
import path from "node:path";
const evidence = path.resolve(
  process.env.INSTAKILL_EVIDENCE_DIR || "../docs/evidence/local-run",
);
for (const viewport of [
  { width: 1440, height: 1000 },
  { width: 390, height: 844 },
]) {
  test(`actual search and feed at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto("/search/");
    await page.evaluate(() => document.fonts.ready);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      "Find your kind of conversation.",
    );
    await page.screenshot({
      path: path.join(evidence, `initial-${viewport.width}.png`),
      fullPage: true,
      animations: "disabled",
    });
    await page
      .getByRole("textbox", { name: "What are you looking for?" })
      .fill("inexpensive supper");
    await page
      .getByRole("textbox", { name: "What are you looking for?" })
      .press("Enter");
    await expect(page.locator(".post")).toHaveCount(5, { timeout: 120000 });
    await expect(page.locator(".score").first()).toContainText("Similarity");
    await page.screenshot({
      path: path.join(evidence, `search-${viewport.width}.png`),
      fullPage: true,
      animations: "disabled",
    });
    await page.getByRole("radio", { name: "By words", exact: true }).check();
    await expect(
      page.getByRole("heading", { name: "No posts found." }),
    ).toBeVisible();
    await page
      .getByRole("textbox", { name: "What are you looking for?" })
      .fill("Python");
    await page.getByRole("button", { name: "Search posts" }).click();
    await expect(page.locator(".score").first()).toContainText("matching word");
    await page.getByRole("button", { name: "Your feed", exact: true }).click();
    await page.getByRole("button", { name: "Load feed" }).click();
    await expect(page.locator(".post")).toHaveCount(5);
    const personal = await page.locator(".post-meta").allTextContents();
    await page.screenshot({
      path: path.join(evidence, `feed-${viewport.width}.png`),
      fullPage: true,
      animations: "disabled",
    });
    await page.getByRole("radio", { name: "Latest", exact: true }).check();
    await expect(
      page.getByRole("heading", { name: "The latest conversations" }),
    ).toBeVisible();
    expect(await page.locator(".post-meta").allTextContents()).not.toEqual(
      personal,
    );
    await page.getByRole("spinbutton", { name: "Your user ID" }).fill("999");
    await page.getByRole("button", { name: "Load feed" }).click();
    await expect(page.getByRole("alert")).toContainText("does not exist");
    await page.getByRole("spinbutton", { name: "Your user ID" }).fill("1");
    await page.getByRole("button", { name: "Retry", exact: true }).click();
    await expect(page.locator(".post")).toHaveCount(5);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
    expect(errors).toEqual([]);
  });
}
test("loading, duplicate prevention, errors, recovery and keyboard focus", async ({
  page,
}) => {
  await page.goto("/search/");
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Skip to content" }),
  ).toBeFocused();
  let attempts = 0;
  await page.route("**/search?*", async (route) => {
    attempts++;
    await new Promise((resolve) => setTimeout(resolve, 350));
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        detail:
          "Search by meaning is unavailable. Try By words or retry later.",
      }),
    });
  });
  await page.getByRole("textbox").fill("cheap dinner");
  await page.getByRole("textbox").press("Enter");
  await expect(page.getByRole("button", { name: "Searching…" })).toBeDisabled();
  await page.getByRole("textbox").press("Enter");
  await expect(page.getByRole("alert")).toContainText("By words");
  expect(attempts).toBe(1);
  await page.unroute("**/search?*");
  await page.getByRole("radio", { name: "By words", exact: true }).check();
  await expect(page.locator(".post")).toHaveCount(1);
  await page.emulateMedia({ reducedMotion: "reduce" });
  expect(
    await page
      .locator(".post-list")
      .evaluate((el) => getComputedStyle(el).animationName),
  ).toBe("none");
  await page.setViewportSize({ width: 320, height: 800 });
  await page.evaluate(() => (document.documentElement.style.fontSize = "200%"));
  await expect(page.getByRole("heading", { level: 1 })).toHaveCSS(
    "font-size",
    "76px",
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: path.join(evidence, "keyboard-reduced-motion-320.png"),
    fullPage: true,
    animations: "disabled",
  });
});
