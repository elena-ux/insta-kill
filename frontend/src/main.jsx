import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/dm-sans/400.css";
import "@fontsource/dm-sans/500.css";
import "@fontsource/dm-sans/600.css";
import "@fontsource/dm-sans/700.css";
import "./styles.css";

function Icon({ arrow = false }) {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      aria-hidden="true"
    >
      {arrow ? (
        <path d="M4 12h15m-6-6 6 6-6 6" />
      ) : (
        <>
          <circle cx="10.7" cy="10.7" r="6.7" />
          <path d="m16 16 4.5 4.5" />
        </>
      )}
    </svg>
  );
}
const examples = [
  "cheap dinner",
  "beginner running route",
  "learn Python types",
];
function dateLabel(value, includeYear = false) {
  if (!value) return "Date unavailable";
  const stamp =
    value.endsWith("Z") || /[+-]\d\d:\d\d$/.test(value) ? value : value + "Z";
  return (
    new Intl.DateTimeFormat("en-GB", {
      month: "short",
      day: "numeric",
      ...(includeYear ? { year: "numeric" } : {}),
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "UTC",
    }).format(new Date(stamp)) + " UTC"
  );
}
function DraftForm({ userId, setUserId }) {
  const [content, setContent] = useState("");
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function prepare(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setPreview(null);
    try {
      const response = await fetch("/posts/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: Number(userId), content }),
        signal: AbortSignal.timeout(15000),
      });
      const body = await response.json();
      if (!response.ok)
        throw new Error(
          typeof body.detail === "string"
            ? body.detail
            : "Check the author and draft text.",
        );
      setPreview(body);
    } catch (error) {
      setError(error.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="workspace">
      <section className="work-area">
        <form className="draft-form" onSubmit={prepare}>
          <label className="field-label" htmlFor="draft-author">
            Author ID
          </label>
          <input
            id="draft-author"
            type="number"
            min="1"
            required
            value={userId}
            onChange={(e) => {
              setUserId(e.target.value);
              setPreview(null);
            }}
          />
          <label className="field-label" htmlFor="draft-content">
            Your post
          </label>
          <textarea
            id="draft-content"
            rows={5}
            required
            maxLength={5000}
            value={content}
            onChange={(e) => {
              setContent(e.target.value);
              setPreview(null);
            }}
            placeholder="What would you like to share?"
          />
          <p className="field-help">
            Preview only. Your draft is not published or saved.
          </p>
          <button className="primary-button" disabled={busy} type="submit">
            {busy ? "Preparing…" : "Preview draft"}
            <Icon arrow />
          </button>
        </form>
        {error && (
          <p className="error-state" role="alert">
            {error}
          </p>
        )}
        {preview && (
          <section className="draft-preview" aria-live="polite">
            <h2>Draft preview</h2>
            <p className="field-help">Member {preview.user_id}</p>
            <p>{preview.content}</p>
          </section>
        )}
      </section>
      <aside className="context-note">
        <h2>Ready to read.</h2>
        <p>
          Preview how your text reads. Empty drafts are rejected and extra
          spaces at the beginning and end are removed.
        </p>
        <div className="learning-note">
          <span>From Weeks 1–2</span>
          <p>
            A typed post and a small service that validates the draft before
            anything is stored.
          </p>
        </div>
      </aside>
    </div>
  );
}

function App() {
  const [catalogue, setCatalogue] = useState(null);
  const [collection, setCollection] = useState("community");
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    fetch("/dataset", { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("Dataset information unavailable");
        return response.json();
      })
      .then((info) => {
        setCatalogue(info);
        setCollection(info.default_collection);
        setUserId(
          String(info.collections[info.default_collection].first_user_id || 1),
        );
      })
      .catch(() => {});
    fetch("/health", { signal: controller.signal })
      .then((response) => setConnected(response.ok))
      .catch(() => setConnected(false));
    return () => controller.abort();
  }, []);
  const dataset = catalogue?.collections?.[collection];
  const isMovieLens = dataset?.source === "movielens";
  const searchExamples = isMovieLens
    ? ["Toy Story", "Star Wars", "The Matrix"]
    : examples;
  const [view, setView] = useState("search"),
    [query, setQuery] = useState(""),
    [mode, setMode] = useState("semantic");
  const [strategy, setStrategy] = useState("for_you"),
    [userId, setUserId] = useState("1"),
    [limit, setLimit] = useState(5);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [data, setData] = useState(null);
  const [searched, setSearched] = useState(false),
    [revision, setRevision] = useState(0);
  const pending = useRef(false),
    input = useRef(null);
  async function execute(options = {}) {
    if (pending.current) return;
    const nextQuery = options.query ?? query,
      nextMode = options.mode ?? mode,
      nextStrategy = options.strategy ?? strategy;
    if (view === "search" && !nextQuery.trim()) {
      setError("Enter a few words to find a conversation.");
      input.current?.focus();
      return;
    }
    pending.current = true;
    setBusy(true);
    setError("");
    setData(null);
    setSearched(true);
    try {
      const params =
        view === "search"
          ? new URLSearchParams({
              q: nextQuery.trim(),
              mode: nextMode,
              limit: String(limit),
              collection,
            })
          : new URLSearchParams({
              user_id: userId,
              strategy: nextStrategy,
              limit: String(limit),
              collection,
            });
      const response = await fetch(
        `/${view === "search" ? "search" : "feed"}?${params}`,
        { signal: AbortSignal.timeout(120000) },
      );
      const body = await response.json();
      if (!response.ok)
        throw new Error(
          typeof body.detail === "string"
            ? body.detail
            : view === "search"
              ? "Check your search settings and try again."
              : "Check the user ID and feed settings, then try again.",
        );
      setData(body);
      setRevision((n) => n + 1);
    } catch (e) {
      setError(
        e.name === "TimeoutError"
          ? view === "search"
            ? "This is taking longer than expected. Try By words, or retry in a moment."
            : "This is taking longer than expected. Try another feed strategy, or retry."
          : e.message === "Failed to fetch"
            ? "We could not reach InstaKill. Check that the app is running, then retry."
            : e.message,
      );
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  function changeView(next) {
    if (next === view || pending.current) return;
    setView(next);
    setData(null);
    setError("");
    setSearched(false);
    document.title = `InstaKill · ${next === "search" ? "Discover" : next === "draft" ? "Draft" : "Feed"}`;
  }
  function changeMode(next) {
    setMode(next);
    if (searched && query.trim()) void execute({ mode: next });
  }
  function changeStrategy(next) {
    setStrategy(next);
    if (searched) void execute({ strategy: next });
  }
  const isSearch = view === "search";
  const isDraft = view === "draft";
  const items = data
    ? isSearch
      ? data.results.map((hit) => ({ ...hit.post, score: hit.score }))
      : data.posts.map((post) => ({ ...post, id: post.post_id }))
    : [];
  const activeMode = data?.mode ?? mode,
    activeStrategy = data?.strategy ?? strategy;
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="masthead">
        <div className="nav-inner">
          <a className="wordmark" href="/search/" aria-label="InstaKill home">
            instakill<span>.</span>
          </a>
          <nav aria-label="Main navigation">
            {[
              ["search", "Discover"],
              ["feed", "Your feed"],
              ["draft", "Draft"],
            ].map(([id, label]) => (
              <button
                className={view === id ? "nav-item active" : "nav-item"}
                aria-current={view === id ? "page" : undefined}
                disabled={busy}
                key={id}
                onClick={() => changeView(id)}
              >
                {label}
              </button>
            ))}
          </nav>
          <span className="community-label">
            {isMovieLens
              ? "The MovieLens catalogue"
              : "The classroom community"}
          </span>
        </div>
      </header>
      <main id="main" className="page">
        <div className="page-heading">
          <h1>
            {isDraft ? (
              "Prepare a post."
            ) : isSearch ? (
              <>
                Find your kind
                <br /> of conversation.
              </>
            ) : (
              <>
                A little more
                <br /> your kind of feed.
              </>
            )}
          </h1>
          <p>
            {isDraft
              ? "Write a draft and check it before sharing."
              : isMovieLens
                ? "Explore the MovieLens films and compare the three feed strategies using the original rating history."
                : isSearch
                  ? "Ideas, recommendations and everyday discoveries. Find a post, even when you don’t have the exact words."
                  : "The same community, a different order. Compare a simple formula, the latest posts, and a model’s predictions."}
          </p>
        </div>
        {catalogue && (
          <div className="collection-controls">
            <label className="field-label" htmlFor="collection">
              Explore
            </label>
            <select
              id="collection"
              value={collection}
              disabled={busy}
              onChange={(e) => {
                const next = e.target.value;
                setCollection(next);
                setUserId(
                  String(catalogue.collections[next].first_user_id || 1),
                );
                setData(null);
                setError("");
                setSearched(false);
                setQuery("");
              }}
            >
              {Object.entries(catalogue.collections)
                .filter(([, value]) => value.posts > 0)
                .map(([name]) => (
                  <option value={name} key={name}>
                    {name === "movies" ? "Movies" : "Community"}
                  </option>
                ))}
            </select>
            {dataset && (
              <p className="field-help dataset-summary">
                {dataset.posts.toLocaleString("en-GB")}{" "}
                {isMovieLens ? "films" : "posts"}
                {" · "}
                {dataset.users} users{" · "}
                {dataset.likes.toLocaleString("en-GB")} likes.
              </p>
            )}
          </div>
        )}
        {isDraft ? (
          <DraftForm key={collection} userId={userId} setUserId={setUserId} />
        ) : (
          <div className="workspace">
            <section
              className="work-area"
              aria-label={
                isSearch ? "Search community posts" : "Community feed"
              }
            >
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void execute();
                }}
              >
                {isSearch ? (
                  <>
                    <label className="field-label" htmlFor="query">
                      What are you looking for?
                    </label>
                    <div className="search-box">
                      <span className="search-icon">
                        <Icon />
                      </span>
                      <input
                        ref={input}
                        id="query"
                        name="query"
                        maxLength={500}
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        placeholder={
                          isMovieLens
                            ? "A film title…"
                            : "A good meal, a new route, a little help…"
                        }
                        autoComplete="off"
                        aria-describedby="search-help"
                      />
                      <button
                        className="primary-button"
                        type="submit"
                        disabled={busy}
                      >
                        {busy ? "Searching…" : "Search posts"}
                        <Icon arrow />
                      </button>
                    </div>
                    <p className="field-help" id="search-help">
                      {isMovieLens
                        ? "Search the original MovieLens film titles."
                        : "A few words are enough. Our demo posts are in English."}
                    </p>
                    <div className="examples" aria-label="Try an example">
                      <span>Try</span>
                      {searchExamples.map((example) => (
                        <button
                          type="button"
                          key={example}
                          disabled={busy}
                          onClick={() => {
                            setQuery(example);
                            void execute({ query: example });
                          }}
                        >
                          {example}
                          <Icon arrow />
                        </button>
                      ))}
                    </div>
                  </>
                ) : (
                  <div className="feed-controls">
                    <div>
                      <label className="field-label" htmlFor="user-id">
                        Your user ID
                      </label>
                      <input
                        id="user-id"
                        name="user-id"
                        type="number"
                        min="1"
                        required
                        value={userId}
                        onChange={(e) => setUserId(e.target.value)}
                        aria-describedby="user-help"
                      />
                      <p className="field-help" id="user-help">
                        {dataset?.users > 0
                          ? `Demo users: ${dataset.first_user_id}–${dataset.last_user_id}. `
                          : "Enter an existing user ID. "}
                        This chooses a feed; it does not sign you in.
                      </p>
                    </div>
                    <button
                      className="primary-button"
                      type="submit"
                      disabled={busy}
                    >
                      {busy ? "Loading…" : "Load feed"}
                      <Icon arrow />
                    </button>
                  </div>
                )}
                <div className="controls-row">
                  <fieldset className="segmented">
                    <legend className="sr-only">
                      {isSearch ? "Search method" : "Feed strategy"}
                    </legend>
                    {(isSearch
                      ? [
                          ["semantic", "By meaning"],
                          ["keyword", "By words"],
                        ]
                      : [
                          ["for_you", "For you"],
                          ["chronological", "Latest"],
                          ["learned", "Learned"],
                        ]
                    ).map(([value, label]) => (
                      <label
                        className={
                          (isSearch ? mode : strategy) === value
                            ? "segment selected"
                            : "segment"
                        }
                        key={value}
                      >
                        <input
                          type="radio"
                          name="method"
                          value={value}
                          checked={(isSearch ? mode : strategy) === value}
                          disabled={busy}
                          onChange={() =>
                            isSearch ? changeMode(value) : changeStrategy(value)
                          }
                        />
                        <span>{label}</span>
                      </label>
                    ))}
                  </fieldset>
                  <label className="limit-label">
                    Show
                    <select
                      aria-label="Result limit"
                      value={limit}
                      disabled={busy}
                      onChange={(e) => setLimit(Number(e.target.value))}
                    >
                      {[5, 10, 20, 50].map((n) => (
                        <option value={n} key={n}>
                          {n} posts
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              </form>
              <div className="results-space" aria-busy={busy}>
                <div className="sr-only" role="status" aria-live="polite">
                  {busy
                    ? isSearch
                      ? "Searching posts."
                      : "Loading feed."
                    : data
                      ? `${items.length} posts returned.`
                      : ""}
                </div>
                {busy ? (
                  <div className="loading-state">
                    <div className="loading-line" />
                    <h2>
                      {isSearch
                        ? "Finding the conversation…"
                        : "Putting your feed in order…"}
                    </h2>
                    <p>
                      {isSearch && mode === "semantic"
                        ? "The first search can take longer while search by meaning gets ready."
                        : "Just a moment."}
                    </p>
                  </div>
                ) : error ? (
                  <div className="error-state" role="alert">
                    <h2>
                      {isSearch
                        ? "Let’s try that again."
                        : "Your feed couldn’t load."}
                    </h2>
                    <p>{error}</p>
                    <button
                      type="button"
                      className="text-button"
                      onClick={() => void execute()}
                    >
                      Retry
                      <Icon arrow />
                    </button>
                  </div>
                ) : data ? (
                  <>
                    <div className="results-heading">
                      <h2>
                        {isSearch ? (
                          <>
                            Results for <span>“{data.query}”</span>
                          </>
                        ) : activeStrategy === "for_you" ? (
                          "Selected for you"
                        ) : activeStrategy === "learned" ? (
                          "Ranked by the model"
                        ) : (
                          "The latest conversations"
                        )}
                      </h2>
                      <span>
                        {items.length} {items.length === 1 ? "post" : "posts"}
                      </span>
                    </div>
                    {items.length ? (
                      <ol className="post-list result-reveal" key={revision}>
                        {items.map((post, index) => (
                          <li key={post.id}>
                            <article className="post">
                              <div
                                className={`avatar tone-${post.user_id % 3}`}
                                aria-hidden="true"
                              >
                                {String(post.user_id).padStart(2, "0")}
                              </div>
                              <div className="post-body">
                                <div className="post-meta">
                                  <strong>
                                    {post.user_id === dataset?.catalogue_user_id
                                      ? "MovieLens catalogue"
                                      : `Member ${post.user_id}`}
                                  </strong>
                                  <span>Post {post.id}</span>
                                </div>
                                <p>{post.content}</p>
                                <div className="post-footer">
                                  <time dateTime={post.created_at}>
                                    {dateLabel(post.created_at, isMovieLens)}
                                  </time>
                                  <span className="score">
                                    {isSearch
                                      ? activeMode === "semantic"
                                        ? `Similarity ${post.score.toFixed(3)}`
                                        : `${post.score} matching ${post.score === 1 ? "word" : "words"}`
                                      : activeStrategy === "for_you"
                                        ? `Feed score ${post.score.toFixed(3)}`
                                        : activeStrategy === "learned"
                                          ? `Estimated like ${(post.score * 100).toFixed(1)}%`
                                          : "Newest first"}
                                  </span>
                                </div>
                              </div>
                              <span
                                className="rank"
                                aria-label={`Rank ${index + 1}`}
                              >
                                {String(index + 1).padStart(2, "0")}
                              </span>
                            </article>
                          </li>
                        ))}
                      </ol>
                    ) : (
                      <div className="empty-state">
                        <h3>
                          {isSearch
                            ? "No posts found."
                            : "You’re all caught up."}
                        </h3>
                        <p>
                          {isSearch
                            ? "Try a broader phrase or switch to By meaning."
                            : "There are no eligible posts for this member. Try another user ID."}
                        </p>
                      </div>
                    )}
                    {items.length > 0 && (
                      <p className="result-note">
                        {isSearch
                          ? activeMode === "semantic"
                            ? "Similar meaning is a clue, not a guarantee. Check whether a post fits what you need."
                            : "Matching words counts shared words. It can miss a good post that uses a different phrase."
                          : activeStrategy === "learned"
                            ? isMovieLens
                              ? "Model estimates from MovieLens history, not measured like rates. Films you’ve already liked are left out."
                              : "Model estimates on synthetic posts, not measured like rates. Your own posts and posts you’ve already liked are left out."
                            : "Your own posts and posts you’ve already liked are left out."}
                      </p>
                    )}
                  </>
                ) : (
                  <div className="welcome-state">
                    <div className="welcome-mark" aria-hidden="true">
                      <Icon />
                    </div>
                    <h2>
                      {isSearch
                        ? "Something worth finding."
                        : "See what changes the order."}
                    </h2>
                    <p>
                      {isSearch
                        ? "Start with a question or try one of the examples above. Your next useful conversation could use entirely different words."
                        : "Load a member’s feed, then switch between For you, Latest and Learned to compare the order."}
                    </p>
                  </div>
                )}
              </div>
            </section>
            <aside className="context-note">
              <div className="note-symbol" aria-hidden="true">
                <Icon arrow />
              </div>
              <h2>
                {isSearch
                  ? "Different words.\nShared meaning."
                  : "Your interests.\nA different order."}
              </h2>
              <p>
                {isSearch
                  ? isMovieLens
                    ? "Search compares film titles. The imported data does not include plots or reviews."
                    : "“Cheap dinner” and “a budget-friendly restaurant” can point to the same idea. Search by meaning helps make that connection."
                  : activeStrategy === "learned"
                    ? "Learned uses six signals, including the categories you have liked, to estimate which posts you might like next. The model was trained on MovieLens."
                    : "For you balances fresh posts, authors you follow and community likes. Latest simply puts the newest posts first."}
              </p>
              <p className="note-limit">
                {isSearch
                  ? "Looking for a specific name or phrase? Try By words."
                  : activeStrategy === "learned"
                    ? "No likes yet? The model still scores posts, with no category preference or activity history."
                    : "No follows yet? You can still discover fresh and popular posts from the community."}
              </p>
              <div className="learning-note">
                <span>
                  {isSearch
                    ? "From Week 3"
                    : activeStrategy === "learned"
                      ? "From Week 5"
                      : "From Week 4"}
                </span>
                <p>
                  {isSearch
                    ? "Finding relevant posts beyond exact word matches."
                    : activeStrategy === "learned"
                      ? "Using a trained model to score posts, one batch at a time."
                      : "Making a ranking policy visible and explainable."}
                </p>
              </div>
            </aside>
          </div>
        )}
        <footer className="page-footer">
          <span role="status">{connected ? "Connected" : "Connecting…"}</span>
          <span>
            {isMovieLens
              ? "Classroom demo · MovieLens latest-small"
              : dataset
                ? "Classroom demo · Synthetic community data"
                : "Classroom demo"}
          </span>
        </footer>
      </main>
    </>
  );
}
createRoot(document.getElementById("root")).render(<App />);
