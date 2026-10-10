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
import { getScores } from "./api";
import intro from "./content/intro.md?raw";
import {
  modeLabels,
  type Ruleset,
  type Score,
  type ScoresResponse,
} from "./types";

const number = (value: number | null, digits = 0) =>
  value === null
    ? "—"
    : value.toLocaleString("en-US", {
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
          <span className="difficulty" title="谱面基础 SR，未应用 mods">
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
  const [limit, setLimit] = useState(20);
  const [mode, setMode] = useState<Ruleset>("mania");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<ScoresResponse | null>(null);
  const [cache, setCache] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const request = useRef<AbortController | null>(null);

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

  async function fetchScores(name: string, selectedMode: Ruleset) {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const response = await getScores(
        name,
        limit,
        selectedMode,
        controller.signal,
      );
      if (!controller.signal.aborted) {
        setResult(response.data);
        setCache(response.cache);
      }
    } catch (failure) {
      if (!controller.signal.aborted)
        setError(
          failure instanceof TypeError
            ? "无法连接查询服务，请检查网络后重试。"
            : failure instanceof Error
              ? failure.message
              : "查询失败，请稍后重试。",
        );
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }

  function changeMode(next: Ruleset) {
    if (next === mode) return;
    setMode(next);
    setError("");
    if (result) void fetchScores(result.player.username, next);
  }

  return (
    <div className="app-shell">
      <header className="site-header">
        <a className="brand" href="/" aria-label="rarverse 首页">
          <span className="brand-icon">
            <i />
            <i />
            <i />
          </span>
          rarverse<span className="brand-slash">/</span>
          <span className="brand-product">scores</span>
        </a>
        <a
          className="header-link"
          href="https://osu.ppy.sh"
          target="_blank"
          rel="noreferrer"
        >
          访问 osu!
          <ArrowUpRight size={14} />
        </a>
      </header>
      <main>
        <section className="hero" aria-labelledby="page-title">
          <h1 id="page-title">osu! 成绩查询</h1>
          {intro.trim() && (
            <div className="hero-description custom-copy">
              <Markdown>{intro}</Markdown>
            </div>
          )}
          <form className="search-panel" onSubmit={search}>
            <div className="search-input-wrap">
              <Search size={21} aria-hidden="true" />
              <label className="sr-only" htmlFor="username">
                玩家用户名或 ID
              </label>
              <input
                id="username"
                ref={input}
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="输入玩家用户名或 ID"
                autoComplete="off"
                maxLength={32}
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
              {loading ? "查询中" : "查询成绩"}
              {!loading && <ChevronRight size={16} />}
            </button>
            <div className="search-options">
              <fieldset className="mode-tabs">
                <legend className="sr-only">游戏模式</legend>
                {(Object.keys(modeLabels) as Ruleset[]).map((value) => (
                  <button
                    type="button"
                    key={value}
                    aria-pressed={mode === value}
                    disabled={loading}
                    onClick={() => changeMode(value)}
                  >
                    {modeLabels[value]}
                  </button>
                ))}
              </fieldset>
              <label htmlFor="limit">Best performance</label>
              <select
                id="limit"
                value={limit}
                onChange={(event) => setLimit(Number(event.target.value))}
                disabled={loading}
              >
                <option value={20}>Top 20</option>
                <option value={50}>Top 50</option>
              </select>
            </div>
          </form>
          <div className="search-note">
            <Check size={13} />
            无需登录<span>·</span>公开成绩
          </div>
        </section>

        {error && (
          <div className="error-panel" role="alert">
            <CircleAlert size={20} />
            <div>
              <strong>暂时无法查询</strong>
              <p>{error}</p>
            </div>
          </div>
        )}
        {loading && (
          <section className="loading-panel" role="status" aria-live="polite">
            <LoaderCircle size={24} className="spin" />
            <div>
              <strong>正在读取玩家成绩</strong>
              <p>正在获取 {modeLabels[mode]} best performance…</p>
            </div>
          </section>
        )}
        {result && (
          <section className="results" aria-label="玩家成绩" aria-live="polite">
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
                  <span>Performance</span>
                  <strong>
                    {number(result.player.pp, 2)}
                    <small>pp</small>
                  </strong>
                </div>
                <div>
                  <span>Global rank</span>
                  <strong>
                    {result.player.global_rank === null
                      ? "—"
                      : `#${number(result.player.global_rank)}`}
                  </strong>
                </div>
                <div>
                  <span>Accuracy</span>
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
                <h2>最佳表现</h2>
                <span>{result.scores.length} scores</span>
              </div>
              <span className="cache-status">
                <span className="live-dot" />
                {cache === "HIT" ? "已缓存" : "刚刚获取"}
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
                <h3>还没有最佳成绩</h3>
                <p>
                  这位玩家目前没有公开的 {modeLabels[result.mode]} best
                  performance。
                </p>
              </div>
            )}
            <div className="result-footnote">
              <span>SR 为谱面基础值（未应用 mods）；pp 为 osu! 返回值。</span>
              <span>
                更新于 {new Date(result.fetched_at).toLocaleString("zh-CN")}
              </span>
            </div>
          </section>
        )}
        {!result && !loading && !error && (
          <section className="start-panel" aria-label="查询说明">
            <Search size={28} aria-hidden="true" />
            <h2>输入玩家用户名或 ID</h2>
            <p>选择游戏模式后查询 Top 20 / Top 50 成绩。</p>
          </section>
        )}
        <div className="feature-strip">
          <div>
            <Trophy size={17} />
            <span>最佳表现</span>
            <small>Best performance</small>
          </div>
          <div>
            <Star size={17} />
            <span>关键数据</span>
            <small>pp · Accuracy · SR</small>
          </div>
          <div>
            <Circle size={17} />
            <span>四种模式</span>
            <small>osu! · taiko · catch · mania</small>
          </div>
        </div>
      </main>
      <footer>
        <div>
          <span className="footer-brand">rarverse</span>
        </div>
        <p>非官方 fan-made 项目，与 peppy / osu! 无隶属关系。</p>
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
