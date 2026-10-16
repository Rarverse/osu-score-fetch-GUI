import {
  ArrowUpRight,
  Check,
  ChevronRight,
  Circle,
  CircleAlert,
  Command,
  ExternalLink,
  Keyboard,
  LoaderCircle,
  Search,
  Star,
  Trophy,
} from "lucide-react";
import { type FormEvent, useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import { ApiError, getScores, waitForRetry } from "./api";
import introEn from "./content/intro.en.md?raw";
import intro from "./content/intro.md?raw";
import { language, locale, t } from "./i18n";
import ModeIcon from "./ModeIcon";
import {
  modeLabels,
  type Ruleset,
  type Score,
  type ScoresResponse,
} from "./types";
import WaitingPanel, { type WaitingState } from "./WaitingPanel";

const number = (value: number | null, digits = 0) =>
  value === null
    ? "—"
    : value.toLocaleString(locale, {
        maximumFractionDigits: digits,
        minimumFractionDigits: digits,
      });

function ScoreRow({ score, position }: { score: Score; position: number }) {
  return (
    <article className="score-row">
      <span className="position">{String(position).padStart(2, "0")}</span>
      <div
        className="map-cover"
        style={
          score.cover_url
            ? { backgroundImage: `url(${score.cover_url})` }
            : undefined
        }
      >
        <Keyboard size={22} aria-hidden="true" />
      </div>
      <div className="map-info">
        {score.beatmap_id ? (
          <a
            href={`https://osu.ppy.sh/beatmaps/${score.beatmap_id}`}
            target="_blank"
            rel="noreferrer"
            className="map-title"
          >
            {score.beatmap_title}
            <ArrowUpRight size={13} />
          </a>
        ) : (
          <strong className="map-title">{score.beatmap_title}</strong>
        )}
        <p>
          {score.artist} <span>·</span> {score.version}
        </p>
        <div className="map-tags">
          <span className="difficulty" title={t("srTitle")}>
            <Star size={11} fill="currentColor" />
            {number(score.star_rating, 2)}
          </span>
          {score.mods.length ? (
            score.mods.map((mod) => (
              <span className="mod" key={mod}>
                {mod}
              </span>
            ))
          ) : (
            <span className="no-mod">NM</span>
          )}
        </div>
      </div>
      <span className={`grade grade-${score.rank}`}>{score.rank}</span>
      <div className="accuracy">
        <strong>
          {number(score.accuracy * 100, 2)}
          <small>%</small>
        </strong>
        <span>{number(score.max_combo)}× combo</span>
      </div>
      <div className="score-pp">
        <strong>{number(score.pp, 2)}</strong>
        <span>pp</span>
      </div>
    </article>
  );
}

export default function App() {
  const [username, setUsername] = useState("");
  const [useOwnApi, setUseOwnApi] = useState(false);
  const [apiClientId, setApiClientId] = useState("");
  const [apiClientSecret, setApiClientSecret] = useState("");
  const [limit, setLimit] = useState(20);
  const [mode, setMode] = useState<Ruleset>("mania");
  const [loading, setLoading] = useState(false);
  const [waiting, setWaiting] = useState<WaitingState | null>(null);
  const [error, setError] = useState("");
  const [result, setResult] = useState<ScoresResponse | null>(null);
  const [cache, setCache] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const request = useRef<AbortController | null>(null);
  const secureContext =
    window.isSecureContext ||
    ["localhost", "127.0.0.1", "::1"].includes(location.hostname);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        input.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      request.current?.abort();
    };
  }, []);

  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = username.trim();
    if (!name) {
      input.current?.focus();
      return;
    }
    await fetchScores(name, mode);
  }

  async function fetchScores(
    name: string,
    selectedMode: Ruleset,
    selectedLimit = limit,
  ) {
    const credentials = useOwnApi
      ? { clientId: apiClientId.trim(), clientSecret: apiClientSecret.trim() }
      : undefined;
    if (
      credentials &&
      (!/^\d+$/.test(credentials.clientId) || !credentials.clientSecret)
    ) {
      setError(t("invalidCredentials"));
      return;
    }
    if (credentials && !secureContext) {
      setError(t("httpsRequired"));
      return;
    }
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    setError("");
    setResult(null);
    setWaiting(null);
    try {
      for (let attempt = 0; attempt <= 5; attempt++) {
        try {
          const response = await getScores(
            name,
            selectedLimit,
            selectedMode,
            controller.signal,
            credentials,
          );
          if (!controller.signal.aborted) {
            setResult(response.data);
            setCache(response.cache);
          }
          break;
        } catch (failure) {
          if (controller.signal.aborted) throw failure;
          if (!(failure instanceof ApiError) || !failure.isBusy) throw failure;
          if (attempt === 5) throw new Error(t("busyExhausted"));
          // Respect Retry-After, back off, and stagger clients to avoid retry bursts.
          const milliseconds =
            Math.max(failure.retryAfter, 3 * 2 ** attempt) * 1000 +
            Math.random() * 2000;
          setWaiting({
            until: Date.now() + milliseconds,
            attempt: attempt + 1,
          });
          await waitForRetry(milliseconds, controller.signal);
        }
      }
    } catch (failure) {
      if (!controller.signal.aborted)
        setError(
          failure instanceof TypeError
            ? t("networkError")
            : failure instanceof Error
              ? failure.message
              : t("queryFailed"),
        );
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
        setWaiting(null);
      }
    }
  }

  function changeMode(next: Ruleset) {
    if (next === mode) return;
    setMode(next);
    setError("");
    if (result) void fetchScores(result.player.username, next);
  }

  function changeLimit(next: number) {
    setLimit(next);
    if (result) void fetchScores(result.player.username, mode, next);
  }

  function cancelWaiting() {
    request.current?.abort();
    setWaiting(null);
    setLoading(false);
  }

  const customIntro = language === "zh" ? intro : introEn;

  return (
    <div className="app-shell">
      <header className="site-header">
        <a className="brand" href="/" aria-label={t("home")}>
          <span className="brand-icon">
            <i />
            <i />
            <i />
          </span>
          {t("appName")}
        </a>
        <a
          className="header-link"
          href="https://osu.ppy.sh"
          target="_blank"
          rel="noreferrer"
        >
          {t("visitOsu")}
          <ArrowUpRight size={14} />
        </a>
      </header>
      <main>
        <section className="hero" aria-labelledby="page-title">
          <h1 id="page-title">{t("appName")}</h1>
          {customIntro.trim() && (
            <div className="hero-description custom-copy">
              <Markdown>{customIntro}</Markdown>
            </div>
          )}
          <form className="search-panel" onSubmit={search}>
            <div className="search-input-wrap">
              <Search size={21} aria-hidden="true" />
              <label className="sr-only" htmlFor="username">
                {t("playerLabel")}
              </label>
              <input
                id="username"
                ref={input}
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder={t("playerPlaceholder")}
                autoComplete="off"
                maxLength={32}
                disabled={loading}
                required
              />
              <kbd>
                <Command size={11} /> K
              </kbd>
            </div>
            <button className="search-button" disabled={loading} type="submit">
              {loading ? (
                <LoaderCircle size={17} className="spin" />
              ) : (
                <Search size={17} />
              )}
              {waiting ? t("waiting") : loading ? t("querying") : t("query")}
              {!loading && <ChevronRight size={16} />}
            </button>
            <div className="search-options">
              <div
                className="mode-badge"
                role="img"
                aria-label={t("currentMode", { mode: modeLabels[mode] })}
              >
                <ModeIcon mode={mode} />
              </div>
              <fieldset className="mode-tabs">
                <legend className="sr-only">{t("mode")}</legend>
                {(Object.keys(modeLabels) as Ruleset[]).map((value) => (
                  <button
                    type="button"
                    key={value}
                    aria-pressed={mode === value}
                    disabled={loading}
                    onClick={() => changeMode(value)}
                  >
                    <ModeIcon mode={value} />
                    {modeLabels[value]}
                  </button>
                ))}
              </fieldset>
              <label htmlFor="limit">{t("bestPerformance")}</label>
              <select
                id="limit"
                value={limit}
                onChange={(event) => changeLimit(Number(event.target.value))}
                disabled={loading}
              >
                <option value={20}>Top 20</option>
                <option value={50}>Top 50</option>
              </select>
            </div>
          </form>
          <details className="api-credentials">
            <summary>{t("ownApi")}</summary>
            <div className="api-credentials-content">
              <p>{t("ownApiDescription")}</p>
              <label className="api-credentials-toggle">
                <input
                  type="checkbox"
                  checked={useOwnApi}
                  onChange={(event) => setUseOwnApi(event.target.checked)}
                  disabled={!secureContext}
                />
                {t("ownApi")}
              </label>
              <label>
                {t("clientId")}
                <input
                  inputMode="numeric"
                  autoComplete="off"
                  value={apiClientId}
                  onChange={(event) => setApiClientId(event.target.value)}
                  disabled={!useOwnApi}
                />
              </label>
              <label>
                {t("clientSecret")}
                <input
                  type="password"
                  autoComplete="new-password"
                  value={apiClientSecret}
                  onChange={(event) => setApiClientSecret(event.target.value)}
                  disabled={!useOwnApi}
                />
              </label>
              <p className="api-credentials-note">{t("credentialsInMemory")}</p>
              {!secureContext && (
                <p className="api-credentials-note">{t("httpsRequired")}</p>
              )}
              <a
                href="https://osu.ppy.sh/home/account/edit"
                target="_blank"
                rel="noreferrer"
              >
                {t("createOauth")}
                <ExternalLink size={12} />
              </a>
            </div>
          </details>
          <div className="search-note">
            <Check size={13} />
            {t("noLogin")}
            <span>·</span>
            {t("publicScores")}
          </div>
        </section>

        {error && (
          <div className="error-panel" role="alert">
            <CircleAlert size={20} />
            <div>
              <strong>{t("unableToQuery")}</strong>
              <p>{error}</p>
            </div>
          </div>
        )}
        {waiting && <WaitingPanel waiting={waiting} onCancel={cancelWaiting} />}
        {loading && !waiting && (
          <section className="loading-panel" role="status" aria-live="polite">
            <LoaderCircle size={24} className="spin" />
            <div>
              <strong>{t("loadingScores")}</strong>
              <p>{t("loadingMode", { mode: modeLabels[mode] })}</p>
            </div>
          </section>
        )}
        {result && (
          <section
            className="results"
            aria-label={t("playerScores")}
            aria-live="polite"
          >
            <div className="player-card">
              <div className="player-identity">
                {result.player.avatar_url ? (
                  <img
                    src={result.player.avatar_url}
                    alt=""
                    className="avatar"
                  />
                ) : (
                  <div className="avatar avatar-empty">
                    <Keyboard />
                  </div>
                )}
                <div>
                  <a
                    href={`https://osu.ppy.sh/users/${result.player.user_id}/${result.mode}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <h2>
                      {result.player.username}
                      <ArrowUpRight size={16} />
                    </h2>
                  </a>
                  <p>
                    {result.player.country} <span>·</span>{" "}
                    {modeLabels[result.mode]} <span>·</span> #
                    {result.player.user_id}
                  </p>
                </div>
              </div>
              <div className="player-stats">
                <div>
                  <span>{t("performance")}</span>
                  <strong>
                    {number(result.player.pp, 2)}
                    <small>pp</small>
                  </strong>
                </div>
                <div>
                  <span>{t("globalRank")}</span>
                  <strong>
                    {result.player.global_rank === null
                      ? "—"
                      : `#${number(result.player.global_rank)}`}
                  </strong>
                </div>
                <div>
                  <span>{t("accuracy")}</span>
                  <strong>
                    {number(result.player.hit_accuracy, 2)}
                    <small>%</small>
                  </strong>
                </div>
              </div>
            </div>
            <div className="results-heading">
              <div>
                <Trophy size={17} />
                <h2>{t("bestPerformance")}</h2>
                <span>{t("scoreCount", { count: result.scores.length })}</span>
              </div>
              <span className="cache-status">
                <span className="live-dot" />
                {cache === "MEMORY"
                  ? t("browserCached")
                  : cache === "HIT"
                    ? t("cached")
                    : t("fetched")}
              </span>
            </div>
            {result.scores.length ? (
              <div className="score-list">
                {result.scores.map((score, index) => (
                  <ScoreRow
                    key={`${score.score_id}-${score.beatmap_id}-${score.played_at}`}
                    score={score}
                    position={index + 1}
                  />
                ))}
              </div>
            ) : (
              <div className="empty-scores">
                <Keyboard size={30} />
                <h3>{t("noScores")}</h3>
                <p>{t("noScoresMode", { mode: modeLabels[result.mode] })}</p>
              </div>
            )}
            <div className="result-footnote">
              <span>{t("srNote")}</span>
              <span>
                {t("updated", {
                  date: new Date(result.fetched_at).toLocaleString(locale),
                })}
              </span>
            </div>
          </section>
        )}
        {!result && !loading && !error && (
          <section className="start-panel" aria-label={t("instructions")}>
            <Search size={28} aria-hidden="true" />
            <h2>{t("startTitle")}</h2>
            <p>{t("startDescription")}</p>
          </section>
        )}
        <div className="feature-strip">
          <div>
            <Trophy size={17} />
            <span>{t("bestPerformance")}</span>
            <small>Best performance</small>
          </div>
          <div>
            <Star size={17} />
            <span>{t("keyStats")}</span>
            <small>pp · Accuracy · SR</small>
          </div>
          <div>
            <Circle size={17} />
            <span>{t("fourModes")}</span>
            <small>osu! · taiko · catch · mania</small>
          </div>
        </div>
      </main>
      <footer>
        <div>
          <span className="footer-brand">rarverse</span>
        </div>
        <p>{t("unofficial")}</p>
        <a
          href="https://github.com/Rarverse/osu-score-fetch-GUI"
          target="_blank"
          rel="noreferrer"
        >
          GitHub
          <ExternalLink size={12} />
        </a>
      </footer>
    </div>
  );
}
