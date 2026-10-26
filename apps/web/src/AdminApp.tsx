import {
  Activity,
  ArrowLeft,
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  Clock3,
  Database,
  FileClock,
  Gauge,
  LogIn,
  LogOut,
  RefreshCw,
  ScrollText,
  Search,
  Server,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import {
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  type AdminSession,
  getAdminSession,
  getMonitoring,
  getOverview,
  getRequest,
  getRequests,
  type LogEntry,
  logout,
  type MonitoringStatus,
  type Overview,
  type QueryRecord,
  searchLogs,
} from "./admin-api";

type Page = "overview" | "requests" | "logs";

const eventCopy: Record<string, { title: string; hint?: string }> = {
  request_started: { title: "收到 HTTP 请求" },
  request_completed: { title: "HTTP 请求处理完成" },
  scores_query_started: { title: "开始查询玩家成绩" },
  scores_cache_lookup: { title: "检查成绩缓存" },
  scores_cache_written: { title: "成绩已写入缓存" },
  scores_ready: { title: "成绩结果已准备完成" },
  scores_query_completed: { title: "成绩查询处理完成" },
  osu_query_started: { title: "开始访问 osu! API" },
  osu_http_completed: { title: "osu! HTTP 请求完成" },
  osu_http_failed: {
    title: "osu! HTTP 请求失败",
    hint: "检查阶段、耗时和同一请求中的其他事件。",
  },
  audit_write_failed: {
    title: "请求审计记录写入失败",
    hint: "检查 PostgreSQL 连通性、磁盘空间与迁移状态。",
  },
};

function formatTime(value: string, withDate = false) {
  return new Intl.DateTimeFormat("zh-CN", {
    ...(withDate ? { month: "2-digit", day: "2-digit" } : {}),
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    fractionalSecondDigits: 3,
    hour12: false,
  }).format(new Date(value));
}

function StatusBadge({ status }: { status: number }) {
  const kind = status >= 500 ? "error" : status >= 400 ? "warning" : "ok";
  return <span className={`admin-status admin-status-${kind}`}>{status}</span>;
}

function LoginScreen({ session }: { session: AdminSession }) {
  return (
    <main className="admin-login">
      <div className="admin-login-card">
        <div className="admin-login-icon">
          <ShieldCheck size={34} />
        </div>
        <p className="admin-eyebrow">RARU CONTROL</p>
        <h1>管理员后台</h1>
        <p>
          {session.enabled
            ? "登录需要管理员账号、密码及邮箱一次性验证码。"
            : "管理员后台尚未在服务器上完成配置。"}
        </p>
        {session.enabled ? (
          <a className="admin-primary-button" href="/api/admin/auth/login">
            <LogIn size={17} /> 安全登录
          </a>
        ) : (
          <span className="admin-disabled-note">
            请先完成数据库与 OIDC 配置
          </span>
        )}
        <a className="admin-back-link" href="/">
          <ArrowLeft size={15} /> 返回查分器
        </a>
      </div>
    </main>
  );
}

function OverviewPage() {
  const [data, setData] = useState<Overview | null>(null);
  const [monitoring, setMonitoring] = useState<MonitoringStatus | null>(null);
  const [monitoringError, setMonitoringError] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    getOverview()
      .then(setData)
      .catch((failure: Error) => setError(failure.message));
    getMonitoring()
      .then(setMonitoring)
      .catch((failure: Error) => setMonitoringError(failure.message));
  }, []);

  if (error) return <ErrorPanel message={error} />;
  if (!data) return <LoadingPanel />;
  const successRate = data.requests
    ? ((data.successful / data.requests) * 100).toFixed(1)
    : "100.0";
  return (
    <div className="admin-page-content">
      <header className="admin-page-heading">
        <div>
          <p className="admin-eyebrow">过去 {data.period_hours} 小时</p>
          <h1>运行总览</h1>
        </div>
        <span className="admin-health-pill">
          <CheckCircle2 size={15} /> 管理 API 正常
        </span>
      </header>
      <section className="admin-stat-grid">
        <StatCard
          icon={<Activity />}
          label="成绩请求"
          value={String(data.requests)}
        />
        <StatCard icon={<Gauge />} label="成功率" value={`${successRate}%`} />
        <StatCard
          icon={<Clock3 />}
          label="平均耗时"
          value={`${data.average_duration_ms} ms`}
        />
        <StatCard
          icon={<CircleAlert />}
          label="服务端错误"
          value={String(data.server_errors)}
        />
      </section>
      <section className="admin-panel admin-monitoring">
        <header>
          <div>
            <p className="admin-eyebrow">LIVE AVAILABILITY</p>
            <h2>API 与服务可用性</h2>
          </div>
          <Server size={19} />
        </header>
        {monitoringError ? (
          <p className="admin-monitoring-note error">{monitoringError}</p>
        ) : !monitoring ? (
          <p className="admin-monitoring-note">正在读取监控状态…</p>
        ) : !monitoring.configured ? (
          <p className="admin-monitoring-note">
            Prometheus 尚未配置。启用 admin Compose profile 后即可查看。
          </p>
        ) : monitoring.targets.length ? (
          <div className="admin-target-grid">
            {monitoring.targets.map((target) => (
              <article
                key={`${target.kind}-${target.name}-${target.instance}`}
                className={target.available ? "available" : "unavailable"}
              >
                {target.available ? (
                  <CheckCircle2 size={17} />
                ) : (
                  <XCircle size={17} />
                )}
                <div>
                  <strong>{monitorName(target.name)}</strong>
                  <small>{target.instance}</small>
                </div>
                <span>{target.available ? "正常" : "不可用"}</span>
              </article>
            ))}
          </div>
        ) : (
          <p className="admin-monitoring-note">暂未发现监控目标。</p>
        )}
      </section>
    </div>
  );
}

function monitorName(value: string) {
  return (
    {
      api: "后端 API",
      loki: "日志存储",
      prometheus: "指标存储",
      web: "公开网页",
      "api-health": "API 健康检查",
      "osu-api": "osu! API",
    }[value] || value
  );
}

function StatCard({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <article className="admin-stat-card">
      <span>{icon}</span>
      <p>{label}</p>
      <strong>{value}</strong>
    </article>
  );
}

function RequestsPage({ openLogs }: { openLogs: (requestId: string) => void }) {
  const [items, setItems] = useState<QueryRecord[]>([]);
  const [detail, setDetail] = useState<QueryRecord | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    getRequests()
      .then((response) => setItems(response.items))
      .catch((failure: Error) => setError(failure.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  async function inspect(id: string) {
    try {
      setDetail(await getRequest(id));
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "无法读取请求详情");
    }
  }

  return (
    <div className="admin-page-content">
      <header className="admin-page-heading">
        <div>
          <p className="admin-eyebrow">ENCRYPTED AUDIT</p>
          <h1>查分请求</h1>
        </div>
        <button
          type="button"
          className="admin-icon-button"
          onClick={load}
          aria-label="刷新请求记录"
        >
          <RefreshCw size={17} />
        </button>
      </header>
      {error && <ErrorPanel message={error} />}
      {loading ? (
        <LoadingPanel />
      ) : (
        <div className="admin-panel admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>时间</th>
                <th>查询玩家</th>
                <th>模式</th>
                <th>状态</th>
                <th>缓存</th>
                <th>耗时</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>{formatTime(item.completed_at, true)}</td>
                  <td>
                    <strong>{item.username || item.query || "—"}</strong>
                    {item.query && item.query !== item.username && (
                      <small>输入：{item.query}</small>
                    )}
                  </td>
                  <td>{item.mode || "auto"}</td>
                  <td>
                    <StatusBadge status={item.status} />
                  </td>
                  <td>{item.cache || "—"}</td>
                  <td>{item.duration_ms.toFixed(1)} ms</td>
                  <td>
                    <button
                      type="button"
                      className="admin-text-button"
                      onClick={() => void inspect(item.id)}
                    >
                      查看
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!items.length && <p className="admin-table-empty">暂无请求记录</p>}
        </div>
      )}
      {detail && (
        <div className="admin-detail-backdrop" role="presentation">
          <section className="admin-detail" role="dialog" aria-modal="true">
            <header>
              <div>
                <p className="admin-eyebrow">REQUEST DETAIL</p>
                <h2>{detail.username || detail.query}</h2>
              </div>
              <button
                type="button"
                className="admin-text-button"
                onClick={() => setDetail(null)}
              >
                关闭
              </button>
            </header>
            <dl className="admin-detail-grid">
              <div>
                <dt>Request ID</dt>
                <dd>{detail.request_id}</dd>
              </div>
              <div>
                <dt>状态</dt>
                <dd>
                  <StatusBadge status={detail.status} />
                </dd>
              </div>
              <div>
                <dt>模式</dt>
                <dd>{detail.mode || "auto"}</dd>
              </div>
              <div>
                <dt>成绩数量</dt>
                <dd>{detail.score_count ?? "—"}</dd>
              </div>
              <div>
                <dt>上游请求</dt>
                <dd>{detail.upstream_requests}</dd>
              </div>
              <div>
                <dt>API 配置组</dt>
                <dd>{detail.api_slot ?? "—"}</dd>
              </div>
            </dl>
            <button
              type="button"
              className="admin-secondary-button"
              onClick={() => openLogs(detail.request_id)}
            >
              <ScrollText size={16} /> 查看关联日志
            </button>
            <details className="admin-json">
              <summary>
                <ChevronDown size={15} /> 当次返回结果
              </summary>
              <pre>
                {detail.result
                  ? JSON.stringify(detail.result, null, 2)
                  : "结果快照已过期或不可用"}
              </pre>
            </details>
          </section>
        </div>
      )}
    </div>
  );
}

function LogsPage({ initialRequestId }: { initialRequestId: string }) {
  const [items, setItems] = useState<LogEntry[]>([]);
  const [levels, setLevels] = useState<string[]>(["INFO", "WARNING", "ERROR"]);
  const [rangeMinutes, setRangeMinutes] = useState(15);
  const [text, setText] = useState("");
  const [requestId, setRequestId] = useState(initialRequestId);
  const [live, setLive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const end = new Date();
      const start = new Date(end.getTime() - rangeMinutes * 60 * 1000);
      const response = await searchLogs({
        start: start.toISOString(),
        end: end.toISOString(),
        services: [],
        levels,
        ...(requestId ? { request_id: requestId } : {}),
        ...(text ? { text } : {}),
        limit: 300,
      });
      setItems(response.items);
      setError("");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "无法查询日志");
    } finally {
      setLoading(false);
    }
  }, [levels, rangeMinutes, requestId, text]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!live) return;
    const timer = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(timer);
  }, [live, load]);

  function toggleLevel(level: string) {
    setLevels((current) =>
      current.includes(level)
        ? current.filter((item) => item !== level)
        : [...current, level],
    );
  }

  return (
    <div className="admin-page-content admin-logs-page">
      <header className="admin-page-heading">
        <div>
          <p className="admin-eyebrow">LOKI LOG STREAM</p>
          <h1>日志中心</h1>
        </div>
        <label className="admin-live-switch">
          <input
            type="checkbox"
            checked={live}
            onChange={(event) => setLive(event.target.checked)}
          />
          <span /> 实时刷新
        </label>
      </header>
      <section className="admin-panel admin-log-filters">
        <label>
          <Clock3 size={15} />
          <select
            value={rangeMinutes}
            onChange={(event) => setRangeMinutes(Number(event.target.value))}
            aria-label="日志时间范围"
          >
            <option value={15}>最近 15 分钟</option>
            <option value={60}>最近 1 小时</option>
            <option value={1440}>最近 24 小时</option>
            <option value={10080}>最近 7 天</option>
          </select>
        </label>
        <label>
          <Search size={15} />
          <input
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="搜索事件或内容"
          />
        </label>
        <label>
          <FileClock size={15} />
          <input
            value={requestId}
            onChange={(event) => setRequestId(event.target.value)}
            placeholder="Request ID"
          />
        </label>
        <div className="admin-levels">
          {["DEBUG", "INFO", "WARNING", "ERROR"].map((level) => (
            <button
              type="button"
              key={level}
              className={levels.includes(level) ? "active" : ""}
              onClick={() => toggleLevel(level)}
            >
              {level}
            </button>
          ))}
        </div>
        <button
          type="button"
          className="admin-primary-button compact"
          onClick={() => void load()}
          disabled={loading}
        >
          <RefreshCw size={15} /> 查询
        </button>
      </section>
      {error && <ErrorPanel message={error} />}
      <section className="admin-log-list" aria-live="polite">
        {items.map((item) => (
          <LogRow
            key={`${item.timestamp}-${item.service}-${item.event}-${item.request_id}-${item.raw}`}
            item={item}
          />
        ))}
        {!loading && !error && !items.length && (
          <div className="admin-panel admin-table-empty">
            当前范围内没有匹配日志
          </div>
        )}
      </section>
    </div>
  );
}

function LogRow({ item }: { item: LogEntry }) {
  const copy = item.event ? eventCopy[item.event] : undefined;
  const [open, setOpen] = useState(false);
  const level = item.level.toLowerCase();
  return (
    <article className={`admin-log-row level-${level}`}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        <time>{formatTime(item.timestamp)}</time>
        <span className="admin-log-level">{item.level}</span>
        <span className="admin-log-service">{item.service}</span>
        <span className="admin-log-message">
          <strong>{copy?.title || item.message}</strong>
          {item.event && <small>{item.event}</small>}
        </span>
        <ChevronDown className={open ? "open" : ""} size={16} />
      </button>
      {open && (
        <div className="admin-log-detail">
          {copy?.hint && <p className="admin-log-hint">{copy.hint}</p>}
          {item.request_id && (
            <p>
              <b>Request ID</b>
              <code>{item.request_id}</code>
            </p>
          )}
          <dl>
            {Object.entries(item.fields).map(([key, value]) => (
              <div key={key}>
                <dt>{key}</dt>
                <dd>
                  {typeof value === "string" ? value : JSON.stringify(value)}
                </dd>
              </div>
            ))}
          </dl>
          <details className="admin-json">
            <summary>原始日志</summary>
            <pre>{item.raw}</pre>
          </details>
        </div>
      )}
    </article>
  );
}

function LoadingPanel() {
  return (
    <div className="admin-panel admin-loading">
      <RefreshCw size={18} className="spin" /> 正在加载…
    </div>
  );
}

function ErrorPanel({ message }: { message: string }) {
  return (
    <div className="admin-error">
      <XCircle size={18} />
      <span>{message}</span>
    </div>
  );
}

export default function AdminApp() {
  const [session, setSession] = useState<AdminSession | null>(null);
  const [page, setPage] = useState<Page>(() => {
    const value = location.pathname.split("/")[2];
    return value === "requests" || value === "logs" ? value : "overview";
  });
  const [logRequestId, setLogRequestId] = useState("");

  useEffect(() => {
    getAdminSession()
      .then(setSession)
      .catch(() => setSession({ enabled: true, authenticated: false }));
  }, []);

  const title = useMemo(
    () => ({ overview: "总览", requests: "请求", logs: "日志" })[page],
    [page],
  );

  function navigate(next: Page) {
    history.pushState(
      {},
      "",
      next === "overview" ? "/admin" : `/admin/${next}`,
    );
    setPage(next);
  }

  if (!session)
    return (
      <main className="admin-login">
        <LoadingPanel />
      </main>
    );
  if (!session.authenticated) return <LoginScreen session={session} />;

  async function signOut() {
    if (!session?.csrf_token) return;
    await logout(session.csrf_token);
    setSession({ enabled: true, authenticated: false });
  }

  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <a className="admin-brand" href="/admin">
          <span>R</span>
          <div>
            Raru<small>Control</small>
          </div>
        </a>
        <nav aria-label="管理后台">
          <button
            type="button"
            className={page === "overview" ? "active" : ""}
            onClick={() => navigate("overview")}
          >
            <Gauge />
            总览
          </button>
          <button
            type="button"
            className={page === "requests" ? "active" : ""}
            onClick={() => navigate("requests")}
          >
            <Database />
            请求记录
          </button>
          <button
            type="button"
            className={page === "logs" ? "active" : ""}
            onClick={() => navigate("logs")}
          >
            <ScrollText />
            日志中心
          </button>
        </nav>
        <div className="admin-sidebar-user">
          <ShieldCheck size={17} />
          <div>
            <strong>{session.name || "管理员"}</strong>
            <small>{session.email}</small>
          </div>
        </div>
        <button
          type="button"
          className="admin-logout"
          onClick={() => void signOut()}
        >
          <LogOut size={16} />
          退出登录
        </button>
      </aside>
      <main className="admin-main" aria-label={title}>
        {page === "overview" && <OverviewPage />}
        {page === "requests" && (
          <RequestsPage
            openLogs={(id) => {
              setLogRequestId(id);
              navigate("logs");
            }}
          />
        )}
        {page === "logs" && <LogsPage initialRequestId={logRequestId} />}
      </main>
    </div>
  );
}
