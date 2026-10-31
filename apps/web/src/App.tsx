import {
  ArrowUp,
  ArrowUpRight,
  Check,
  ChevronRight,
  ChevronUp,
  CircleAlert,
  Command,
  Download,
  ExternalLink,
  Eye,
  EyeOff,
  Keyboard,
  LoaderCircle,
  Search,
  Star,
  Trophy,
  UserRound,
  X,
} from "lucide-react";
import {
  type FormEvent,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import Markdown from "react-markdown";
import { version } from "../package.json";
import { ApiError, getScores, waitForRetry } from "./api";
import { type ExportProgress, renderBestScores, saveBestScores } from "./b50";
import introEn from "./content/intro.en.md?raw";
import intro from "./content/intro.md?raw";
import { language, locale, t } from "./i18n";
import ModeIcon from "./ModeIcon";
import PageScrollbar from "./PageScrollbar";
import ResultFreshness from "./ResultFreshness";
import RhythmBackground from "./RhythmBackground";
import ScoreLimitSelect from "./ScoreLimitSelect";
import {
  gradeLabel,
  gradeTitle,
  starBackground,
  starColor,
} from "./score-style";
import {
  modeLabels,
  type QueryMode,
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
          <span
            className="difficulty"
            title={t("srTitle")}
            style={{
              color: starColor(score.star_rating),
              backgroundColor: starBackground(score.star_rating),
            }}
          >
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
      <span
        className={`grade grade-${score.rank}`}
        role="img"
        title={gradeTitle(score.rank)}
        aria-label={gradeTitle(score.rank)}
      >
        {gradeLabel(score.rank)}
      </span>
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

interface RecentPlayer {
  id: number;
  name: string;
  avatar: string;
  mode: QueryMode;
}

const recentKey = "raru-recent-players";
function readRecent(): RecentPlayer[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(recentKey) || "[]");
    if (!Array.isArray(value)) return [];
    return value
      .filter(
        (item): item is RecentPlayer =>
          item &&
          Number.isSafeInteger(item.id) &&
          item.id > 0 &&
          typeof item.name === "string" &&
          typeof item.avatar === "string" &&
          ["auto", "osu", "taiko", "fruits", "mania"].includes(item.mode),
      )
      .slice(0, 5);
  } catch {
    return [];
  }
}

export default function App() {
  const [recent, setRecent] = useState(readRecent);
  const [previousResult, setPreviousResult] = useState(false);
  const [searchedName, setSearchedName] = useState("");
  const [pendingName, setPendingName] = useState("");
  const [lastQuery, setLastQuery] = useState<{
    name: string;
    mode: QueryMode;
    limit: number;
  } | null>(null);
  const [preview, setPreview] = useState<{ url: string; blob: Blob } | null>(
    null,
  );
  const [showQuickNav, setShowQuickNav] = useState(false);
  const hero = useRef<HTMLElement>(null);
  const [username, setUsername] = useState("");
  const [apiExpanded, setApiExpanded] = useState(false);
  const [privacyExpanded, setPrivacyExpanded] = useState(false);
  const [useOwnApi, setUseOwnApi] = useState(false);
  const [apiClientId, setApiClientId] = useState("");
  const [apiClientSecret, setApiClientSecret] = useState("");
  const [showApiSecret, setShowApiSecret] = useState(false);
  const [limit, setLimit] = useState(20);
  const [mode, setMode] = useState<QueryMode>("auto");
  const modeTabs = useRef<HTMLFieldSetElement>(null);
  const modeIndicator = useRef<HTMLSpanElement>(null);
  useLayoutEffect(() => {
    const tabs = modeTabs.current;
    const indicator = modeIndicator.current;
    if (!tabs || !indicator) return;
    const update = () => {
      const selected = tabs.querySelector<HTMLButtonElement>(
        `[data-mode="${mode}"]`,
      );
      if (!selected) return;
      indicator.style.width = `${selected.offsetWidth}px`;
      indicator.style.height = `${selected.offsetHeight}px`;
      indicator.style.transform = `translate(${selected.offsetLeft}px, ${selected.offsetTop}px)`;
      indicator.style.opacity = "1";
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(tabs);
    return () => observer.disconnect();
  }, [mode]);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [downloadError, setDownloadError] = useState("");
  const [downloadProgress, setDownloadProgress] =
    useState<ExportProgress | null>(null);
  const [downloadReady, setDownloadReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [waiting, setWaiting] = useState<WaitingState | null>(null);
  const [error, setError] = useState("");
  const [result, setResult] = useState<ScoresResponse | null>(null);
  const [resultLimit, setResultLimit] = useState(20);
  const [cache, setCache] = useState("");
  const [refreshAt, setRefreshAt] = useState<number | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const request = useRef<AbortController | null>(null);
  const downloadInProgress = useRef(false);
  const secureContext =
    window.isSecureContext ||
    ["localhost", "127.0.0.1", "::1"].includes(location.hostname);

  useEffect(() => {
    if (!hero.current) return;
    const observer = new IntersectionObserver(([entry]) =>
      setShowQuickNav(!entry.isIntersecting),
    );
    observer.observe(hero.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    return () => {
      if (preview) URL.revokeObjectURL(preview.url);
    };
  }, [preview]);

  function updateRecent(next: RecentPlayer[]) {
    setRecent(next);
    try {
      localStorage.setItem(recentKey, JSON.stringify(next));
    } catch {
      /* Storage can be unavailable in private browsing. */
    }
  }

  function backToSearch() {
    hero.current?.scrollIntoView({
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "instant"
        : "smooth",
    });
    input.current?.focus({ preventScroll: true });
  }

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
    selectedMode: QueryMode,
    selectedLimit = limit,
  ) {
    request.current?.abort();
    setLoading(false);
    setWaiting(null);
    setPreviousResult(true);
    setDownloadError("");
    setDownloadProgress(null);
    setDownloadReady(false);
    setPreview(null);
    setLastQuery({ name, mode: selectedMode, limit: selectedLimit });
    setPendingName(name);
    const credentials = useOwnApi
      ? { clientId: apiClientId.trim(), clientSecret: apiClientSecret.trim() }
      : undefined;
    if (
      credentials &&
      (!/^[1-9]\d*$/.test(credentials.clientId) || !credentials.clientSecret)
    ) {
      setError(t("invalidCredentials"));
      return;
    }
    if (credentials && !secureContext) {
      setError(t("httpsRequired"));
      return;
    }
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    setError("");
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
            setPreviousResult(false);
            setSearchedName(name);
            updateRecent(
              [
                {
                  id: response.data.player.user_id,
                  name: response.data.player.username,
                  avatar: response.data.player.avatar_url,
                  mode: selectedMode,
                },
                ...recent.filter(
                  (item) => item.id !== response.data.player.user_id,
                ),
              ].slice(0, 5),
            );
            setResultLimit(selectedLimit);
            setCache(response.cache);
            setRefreshAt(response.refreshAt);
          }
          break;
        } catch (failure) {
          if (controller.signal.aborted) throw failure;
          if (!(failure instanceof ApiError) || !failure.isBusy) throw failure;
          if (attempt === 5) throw new Error(t("busyExhausted"));
          // Respect Retry-After, back off, and stagger clients to avoid retry bursts.
          const milliseconds =
            Math.max(failure.retryAfter, Math.min(10, 3 * 2 ** attempt)) *
              1000 +
            Math.random() * 2000;
          setWaiting({
            until: Date.now() + milliseconds,
            attempt: attempt + 1,
            reason: failure.code,
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

  function changeMode(next: QueryMode) {
    if (next === mode) return;
    setMode(next);
    setError("");
    if (result && username.trim().toLowerCase() === searchedName.toLowerCase())
      void fetchScores(searchedName, next);
  }

  function changeLimit(next: number) {
    setLimit(next);
    if (
      next !== limit &&
      result &&
      username.trim().toLowerCase() === searchedName.toLowerCase()
    )
      void fetchScores(searchedName, mode, next);
  }

  function cancelQuery() {
    request.current?.abort();
    setWaiting(null);
    setLoading(false);
  }

  async function downloadScores() {
    if (!result || loading || downloadInProgress.current) return;
    if (preview) {
      saveBestScores(preview.blob, result, resultLimit);
      return;
    }
    downloadInProgress.current = true;
    const controller = new AbortController();
    request.current = controller;
    setExporting(true);
    setDownloadError("");
    setDownloadReady(false);
    try {
      const blob = await renderBestScores(result, resultLimit, (progress) => {
        if (!controller.signal.aborted) setDownloadProgress(progress);
      });
      if (!controller.signal.aborted) {
        setPreview({ blob, url: URL.createObjectURL(blob) });
        saveBestScores(blob, result, resultLimit);
        setDownloadReady(true);
      }
    } catch (failure) {
      if (!controller.signal.aborted)
        setDownloadError(
          failure instanceof Error ? failure.message : t("downloadFailed"),
        );
    } finally {
      downloadInProgress.current = false;
      setExporting(false);
    }
  }

  const selectedModeLabel =
    mode === "auto" ? t("defaultMode") : modeLabels[mode];
  const customIntro = language === "zh" ? intro : introEn;

  return (
    <div className="app-shell">
      <header className="site-header">
        <a className="brand" href="/" aria-label={t("home")}>
          <svg className="brand-icon" viewBox="0 0 28 22" aria-hidden="true">
            <path
              d="M3 18.5 5.1 10h4.4l-2.1 8.5a2 2 0 0 1-2 1.5H4.2a1.2 1.2 0 0 1-1.2-1.5Z"
              fill="#a78cdd"
            />
            <path
              d="M10 18.5 13.1 6h4.4l-3.1 12.5a2 2 0 0 1-2 1.5h-1.2a1.2 1.2 0 0 1-1.2-1.5Z"
              fill="#b99eec"
            />
            <path
              d="M17 18.5 21.1 2h4.4l-4.1 16.5a2 2 0 0 1-2 1.5h-1.2a1.2 1.2 0 0 1-1.2-1.5Z"
              fill="#d3bfff"
            />
          </svg>
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
        <RhythmBackground />
        <section ref={hero} className="hero" aria-labelledby="page-title">
          <h1 id="page-title" className="sr-only">
            {t("query")}
          </h1>
          {customIntro.trim() && (
            <div className="hero-description custom-copy">
              <Markdown
                components={{
                  strong: ({ children }) =>
                    children === "osu!" ? (
                      <span className="osu-wordmark">{children}</span>
                    ) : (
                      <strong>{children}</strong>
                    ),
                }}
              >
                {customIntro}
              </Markdown>
            </div>
          )}
          <form className="search-panel" onSubmit={search}>
            <div className="search-main">
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
                  disabled={loading || exporting}
                  required
                />
                {username && (
                  <button
                    type="button"
                    className="clear-input"
                    aria-label={t("clearInput")}
                    disabled={loading || exporting}
                    onClick={() => {
                      setUsername("");
                      input.current?.focus();
                    }}
                  >
                    <X size={16} />
                  </button>
                )}
                <kbd>
                  {/Mac|iPhone|iPad/.test(navigator.platform) ? (
                    <Command size={11} />
                  ) : (
                    "Ctrl"
                  )}{" "}
                  K
                </kbd>
              </div>
              <button
                className="search-button"
                disabled={loading || exporting}
                type="submit"
              >
                {loading ? (
                  <LoaderCircle size={17} className="spin" />
                ) : (
                  <Search size={17} />
                )}
                {waiting ? t("waiting") : loading ? t("querying") : t("query")}
                {!loading && <ChevronRight size={16} />}
              </button>
            </div>
            <div className="search-options">
              <fieldset className="mode-tabs" ref={modeTabs}>
                <legend className="sr-only">{t("mode")}</legend>
                <span
                  className="mode-indicator"
                  ref={modeIndicator}
                  aria-hidden="true"
                />
                <button
                  type="button"
                  data-mode="auto"
                  aria-pressed={mode === "auto"}
                  disabled={loading || exporting}
                  onClick={() => changeMode("auto")}
                >
                  <UserRound className="mode-icon" aria-hidden="true" />
                  {t("defaultMode")}
                </button>
                {(Object.keys(modeLabels) as Ruleset[]).map((value) => (
                  <button
                    type="button"
                    key={value}
                    data-mode={value}
                    aria-pressed={mode === value}
                    disabled={loading || exporting}
                    onClick={() => changeMode(value)}
                  >
                    <ModeIcon mode={value} />
                    {modeLabels[value]}
                  </button>
                ))}
              </fieldset>
              <ScoreLimitSelect
                value={limit}
                onChange={changeLimit}
                disabled={loading || exporting}
              />
            </div>
          </form>
          {recent.length > 0 && (
            <div className="recent-searches">
              <div className="recent-heading">
                <span>{t("recentSearches")}</span>
                <button
                  type="button"
                  disabled={loading}
                  onClick={() => updateRecent([])}
                >
                  {t("clearRecent")}
                </button>
              </div>
              <div className="recent-list">
                {recent.map((player) => (
                  <div className="recent-player" key={player.id}>
                    <button
                      type="button"
                      disabled={loading || exporting}
                      onClick={() => {
                        setUsername(player.name);
                        setMode(player.mode);
                        void fetchScores(player.name, player.mode);
                      }}
                    >
                      {player.avatar && <img src={player.avatar} alt="" />}
                      <span>
                        {player.name}
                        <small>
                          {player.mode === "auto"
                            ? t("defaultMode")
                            : modeLabels[player.mode]}
                        </small>
                      </span>
                    </button>
                    <button
                      type="button"
                      disabled={loading}
                      aria-label={t("removeRecent", { name: player.name })}
                      onClick={() =>
                        updateRecent(
                          recent.filter((item) => item.id !== player.id),
                        )
                      }
                    >
                      <X size={14} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
          <div className="api-credentials">
            <p className="api-recommendation">{t("ownApiRecommendation")}</p>
            <button
              type="button"
              className="api-credentials-trigger"
              aria-expanded={apiExpanded}
              aria-controls="api-credentials-panel"
              onClick={() => {
                setApiExpanded((expanded) => !expanded);
                setShowApiSecret(false);
              }}
            >
              <ChevronRight size={16} aria-hidden="true" />
              {t("ownApi")}
            </button>
            <div
              id="api-credentials-panel"
              className="api-credentials-panel"
              aria-hidden={!apiExpanded}
              inert={!apiExpanded}
            >
              <div className="api-credentials-body">
                <div className="api-credentials-content">
                  <p>{t("ownApiDescription")}</p>
                  <label className="api-credentials-toggle">
                    <input
                      type="checkbox"
                      checked={useOwnApi}
                      onChange={(event) => {
                        setUseOwnApi(event.target.checked);
                        setShowApiSecret(false);
                      }}
                      disabled={!secureContext || loading || exporting}
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
                      disabled={!useOwnApi || loading || exporting}
                    />
                  </label>
                  <div className="secret-field">
                    <label htmlFor="api-client-secret">
                      {t("clientSecret")}
                    </label>
                    <div className="secret-input">
                      <input
                        id="api-client-secret"
                        type={showApiSecret ? "text" : "password"}
                        autoComplete="new-password"
                        autoCapitalize="none"
                        spellCheck={false}
                        value={apiClientSecret}
                        onChange={(event) =>
                          setApiClientSecret(event.target.value)
                        }
                        disabled={!useOwnApi || loading || exporting}
                      />
                      <button
                        type="button"
                        aria-controls="api-client-secret"
                        aria-label={t(
                          showApiSecret ? "hideSecret" : "showSecret",
                        )}
                        onClick={() => setShowApiSecret((visible) => !visible)}
                        disabled={!useOwnApi}
                      >
                        {showApiSecret ? (
                          <EyeOff size={17} />
                        ) : (
                          <Eye size={17} />
                        )}
                        {t(showApiSecret ? "hide" : "show")}
                      </button>
                    </div>
                  </div>
                  <p className="api-credentials-note">
                    {t("credentialsInMemory")}
                  </p>
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
              </div>
            </div>
          </div>
        </section>

        {error && (
          <div className="error-panel" role="alert">
            <CircleAlert size={20} />
            <div>
              <strong>{t("unableToQuery")}</strong>
              <p>{error}</p>
              {lastQuery && (
                <button
                  className="text-action"
                  type="button"
                  disabled={loading || exporting}
                  onClick={() =>
                    void fetchScores(
                      lastQuery.name,
                      lastQuery.mode,
                      lastQuery.limit,
                    )
                  }
                >
                  {t("retry")}
                </button>
              )}
            </div>
          </div>
        )}
        {waiting && <WaitingPanel waiting={waiting} onCancel={cancelQuery} />}
        {loading && !waiting && (
          <section className="loading-panel" role="status" aria-live="polite">
            <LoaderCircle size={24} className="spin" />
            <div>
              <strong>{t("loadingPlayer", { name: pendingName })}</strong>
              <p>{t("loadingMode", { mode: selectedModeLabel })}</p>
            </div>
            <button type="button" onClick={cancelQuery}>
              {t("cancelQuery")}
            </button>
          </section>
        )}
        {result && (
          <section
            className="results"
            aria-busy={loading}
            aria-label={t("playerScores")}
            aria-live="polite"
          >
            {previousResult && (
              <p className="previous-result" role="status">
                {t("previousResult")}
              </p>
            )}
            <div
              className="player-card"
              key={`${result.player.user_id}-${result.mode}-${resultLimit}-${result.fetched_at}`}
            >
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
                <span>
                  {modeLabels[result.mode]} · Best {resultLimit}
                </span>
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
            <ResultFreshness
              fetchedAt={result.fetched_at}
              refreshAt={refreshAt}
            />
            <div className="download-actions">
              <button
                type="button"
                className="download-button"
                disabled={loading || exporting || !result.scores.length}
                onClick={() => void downloadScores()}
              >
                {exporting ? (
                  <LoaderCircle size={16} className="spin" />
                ) : (
                  <Download size={16} />
                )}
                {exporting
                  ? t("downloadingImage")
                  : preview
                    ? t("downloadAgain")
                    : t("downloadImage", { count: resultLimit })}
              </button>
            </div>
            <div className="export-feedback">
              {(exporting || downloadReady) && (
                <div
                  key={exporting ? "exporting" : "ready"}
                  className="download-status"
                  role="status"
                  aria-live="polite"
                >
                  {exporting ? (
                    <LoaderCircle size={20} className="spin" />
                  ) : (
                    <Check size={20} />
                  )}
                  <div>
                    <strong>
                      {exporting
                        ? t("downloadTitle", { count: resultLimit })
                        : t("downloadReady")}
                    </strong>
                    <p>
                      {exporting
                        ? downloadProgress?.stage === "images"
                          ? t("downloadImages", {
                              completed: downloadProgress.completed,
                              total: downloadProgress.total,
                            })
                          : t("downloadRendering")
                        : t("downloadBrowser")}
                    </p>
                    {exporting && downloadProgress?.stage === "images" && (
                      <>
                        <progress
                          value={downloadProgress.completed}
                          max={downloadProgress.total || 1}
                          aria-label={t("downloadImageProgress")}
                        />
                        <small>{t("downloadPacing")}</small>
                      </>
                    )}
                  </div>
                </div>
              )}
              {downloadError && (
                <div
                  className="download-status download-status-error"
                  role="alert"
                >
                  <CircleAlert size={20} />
                  <p>{downloadError}</p>
                  <button
                    className="text-action"
                    type="button"
                    disabled={loading || exporting}
                    onClick={() => void downloadScores()}
                  >
                    {t("retryExport")}
                  </button>
                </div>
              )}
            </div>
            {preview && (
              <details
                className="export-preview"
                onToggle={(event) => setPreviewOpen(event.currentTarget.open)}
              >
                <summary>{t("previewImage")}</summary>
                {previewOpen && (
                  <img src={preview.url} alt={t("previewImage")} />
                )}
              </details>
            )}
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
            </div>
          </section>
        )}
      </main>
      <footer>
        <div>
          <span>made by</span>
          <a
            className="footer-brand"
            href="https://rarverse.com"
            target="_blank"
            rel="noreferrer"
          >
            Rarverse
          </a>
        </div>
        <p>
          {t("unofficial")} · v{version}
        </p>
        <span className="privacy-disclosure">
          <button
            type="button"
            aria-expanded={privacyExpanded}
            aria-controls="privacy-notice"
            onClick={() => setPrivacyExpanded(!privacyExpanded)}
            onKeyDown={(event) => {
              if (event.key === "Escape") setPrivacyExpanded(false);
            }}
          >
            {t("privacy")}
            <ChevronUp size={14} aria-hidden="true" />
          </button>
          <ul id="privacy-notice" aria-hidden={!privacyExpanded}>
            <li>{t("privacyBrowser")}</li>
            <li>{t("privacyRequests")}</li>
            <li>{t("privacyLogs")}</li>
            <li>{t("privacyRetention")}</li>
            <li>{t("privacyCredentials")}</li>
          </ul>
        </span>
        {/* Temporarily hide private repo link until public
        <a
          href="https://github.com/Rarverse/osu-score-fetch-GUI"
          target="_blank"
          rel="noreferrer"
        >
          GitHub
          <ExternalLink size={12} />
        </a>
        */}
      </footer>
      {showQuickNav && result && (
        <nav className="quick-nav" aria-label={t("quickNavigation")}>
          <span>
            {result.player.username} · {modeLabels[result.mode]}
          </span>
          <button type="button" onClick={backToSearch}>
            <Search size={16} />
            {t("searchAgain")}
          </button>
          <button
            type="button"
            aria-label={t("backToTop")}
            onClick={backToSearch}
          >
            <ArrowUp size={18} />
          </button>
        </nav>
      )}
      <PageScrollbar />
    </div>
  );
}
