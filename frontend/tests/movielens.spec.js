import { test, expect } from "@playwright/test";
import path from "node:path";

for (const width of [1440, 390]) {
  test(`MovieLens feed and user histories at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const info = await (
      await page.request.get("/dataset?collection=movies")
    ).json();
    expect(info.source).toBe("movielens");
    expect(info.posts).toBe(9724);
    expect(info.users).toBe(610);
    expect(info.likes).toBe(48580);
    await page.goto("/search/");
    await page
      .getByRole("combobox", { name: "Explore" })
      .selectOption("movies");
    await expect(page.locator(".dataset-summary")).toContainText("9,724 films");
    await expect(page.locator(".dataset-summary")).not.toContainText(
      "Feed as of",
    );
    await page.getByRole("radio", { name: "By words", exact: true }).check();
    await page.getByRole("button", { name: "Toy Story", exact: true }).click();
    await expect(page.locator(".post").first()).toContainText("Toy Story");
    await page.getByRole("radio", { name: "By meaning", exact: true }).check();
    await expect(page.locator(".post")).toHaveCount(5, { timeout: 120000 });
    await expect(page.locator(".post").first()).toContainText("Toy Story");
    await expect(page.locator(".score").first()).toContainText("Similarity");
    await page.getByRole("button", { name: "Your feed", exact: true }).click();
    await expect(page.locator("#user-help")).toContainText("1–610");
    await page.getByRole("radio", { name: "Learned", exact: true }).check();
    await page.getByRole("button", { name: "Load feed" }).click();
    await expect(page.locator(".post")).toHaveCount(5);
    const firstIds = await page.locator(".post-meta span").allTextContents();
    await expect(page.locator(".score").first()).toContainText(
      "Estimated like",
    );
    await expect(page.locator(".post-meta strong").first()).toHaveText(
      "MovieLens catalogue",
    );
    await expect(page.locator(".result-note")).toContainText(
      "MovieLens history",
    );
    const expected = await (
      await page.request.get(
        "/feed?user_id=1&strategy=learned&limit=5&collection=movies",
      )
    ).json();
    expect(firstIds).toEqual(
      expected.posts.map((post) => `Post ${post.post_id}`),
    );
    expect(expected.posts.some((post) => post.post_id > 30)).toBeTruthy();
    await page.screenshot({
      path: path.join(
        process.env.INSTAKILL_EVIDENCE_DIR,
        `movielens-${width}.png`,
      ),
      fullPage: true,
    });
    await page.getByRole("spinbutton", { name: "Your user ID" }).fill("442");
    await page
      .getByRole("combobox", { name: "Result limit" })
      .selectOption("20");
    await page.getByRole("button", { name: "Load feed" }).click();
    await expect(page.locator(".post")).toHaveCount(20);
    expect(await page.locator(".post-meta span").allTextContents()).not.toEqual(
      firstIds,
    );
    for (const name of ["Latest", "For you", "Learned"]) {
      await page.getByRole("radio", { name, exact: true }).check();
      await expect(page.locator(".post")).toHaveCount(20);
    }
    await page.getByRole("spinbutton", { name: "Your user ID" }).fill("999");
    await page.getByRole("button", { name: "Load feed" }).click();
    await expect(page.getByRole("alert")).toContainText("does not exist");
    await page
      .getByRole("combobox", { name: "Explore" })
      .selectOption("community");
    await expect(page.locator(".dataset-summary")).toContainText("36 posts");
    await page.getByRole("button", { name: "Draft", exact: true }).click();
    await page
      .getByRole("textbox", { name: "Your post", exact: true })
      .fill("  A shared campus film night.  ");
    await page
      .getByRole("button", { name: "Preview draft", exact: true })
      .click();
    await expect(page.locator(".draft-preview > p").last()).toHaveText(
      "A shared campus film night.",
    );
    await page.screenshot({
      path: path.join(process.env.INSTAKILL_EVIDENCE_DIR, `draft-${width}.png`),
      fullPage: true,
    });
    await page
      .getByRole("textbox", { name: "Your post", exact: true })
      .fill("   ");
    await page
      .getByRole("button", { name: "Preview draft", exact: true })
      .click();
    await expect(page.getByRole("alert")).toContainText(
      "Content must not be blank",
    );
    const unchanged = await (
      await page.request.get("/dataset?collection=community")
    ).json();
    expect(unchanged.posts).toBe(36);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
    expect(errors).toEqual([]);
  });
}
