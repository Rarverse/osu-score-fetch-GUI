const zh = {
  appName: "Rarsu查分器",
  home: "Rarsu查分器首页",
  description:
    "Rarsu查分器：输入 osu! 用户名，直接看 TA 的 Top 20/50 成绩。四个模式都能查，不用登录。",
  currentMode: "当前模式：{mode}",
  visitOsu: "访问 osu!",
  playerLabel: "玩家用户名或 ID",
  playerPlaceholder: "输入玩家用户名或 ID",
  query: "查询成绩",
  querying: "查询中",
  waiting: "等待中",
  mode: "游戏模式",
  defaultMode: "玩家默认",
  downloadB50: "下载 B50 图片",
  downloadingB50: "正在生成图片…",
  downloadFailed: "图片下载失败，请稍后重试。",
  bestPerformance: "最佳表现",
  noLogin: "无需登录",
  publicScores: "公开成绩",
  ownApi: "使用自己的 osu! API",
  ownApiDescription:
    "填写 osu! OAuth 应用的 Client ID 和 Client Secret；本工具使用 client credentials 和 public scope，无需用户授权。仅用此方式时，Callback URL 可留空。留空凭据时使用站点配置。",
  clientId: "Client ID",
  clientSecret: "Client Secret",
  credentialsInMemory:
    "凭据仅保留在此页面内存中，并通过 HTTPS 发送；关闭或刷新页面后需要重新填写。",
  createOauth: "在 osu! 创建 OAuth 应用",
  httpsRequired:
    "出于安全考虑，自定义凭据仅能通过 HTTPS 使用（localhost 除外）。",
  invalidCredentials: "请输入有效的 Client ID 和 Client Secret。",
  unableToQuery: "暂时无法查询",
  loadingScores: "正在读取玩家成绩",
  loadingMode: "正在获取 {mode} best performance…",
  playerScores: "玩家成绩",
  performance: "表现分",
  globalRank: "全球排名",
  accuracy: "准确率",
  scoreCount: "{count} 条成绩",
  cached: "已缓存",
  browserCached: "本地缓存",
  fetched: "刚刚获取",
  noScores: "还没有最佳成绩",
  noScoresMode: "这位玩家目前没有公开的 {mode} best performance。",
  srTitle: "谱面基础 SR，未应用 mods",
  srNote: "SR 为谱面基础值（未应用 mods）；pp 为 osu! 返回值。",
  updated: "更新于 {date}",
  instructions: "查询说明",
  startTitle: "输入玩家用户名或 ID",
  startDescription: "默认按玩家首选模式查询，也可手动选择模式。",
  keyStats: "关键数据",
  fourModes: "四种模式",
  unofficial: "非官方 fan-made 项目，与 peppy / osu! 无隶属关系。",
  busyTitle: "查询服务繁忙，请稍候",
  busyDescription: "当前查询较多，你的查询已保留。",
  retryCountdown: "{seconds} 秒后自动重试",
  retryNow: "正在重新查询…",
  retryAttempt: "第 {attempt} / 5 次重试",
  cancelWaiting: "取消等待",
  busyExhausted: "查询服务仍繁忙，请稍后手动重试。",
  networkError: "无法连接查询服务，请检查网络后重试。",
  queryFailed: "查询失败，请稍后重试。",
  retryAfter: "{seconds} 秒后可再次查询。",
  PLAYER_NOT_FOUND: "未找到该玩家，请检查用户名或 ID。",
  INVALID_PLAYER: "请输入 1–32 字符的用户名或 ID。",
  INVALID_REQUEST: "请检查模式、成绩类型和数量。",
  RATE_LIMITED: "查询过于频繁，请稍后重试。",
  UPSTREAM_ERROR: "osu! 服务暂时无法访问，请稍后重试。",
  NOT_CONFIGURED: "服务端尚未配置 osu! OAuth 凭据。",
  INVALID_CREDENTIALS: "请同时提供有效的 osu! Client ID 和 Client Secret。",
  SERVER_BUSY: "当前查询人数较多，请稍候。",
  UPSTREAM_BUSY: "查询服务正在等待 osu! 请求额度。",
};

type MessageKey = keyof typeof zh;

const en: Record<MessageKey, string> = {
  appName: "Rarsu Score Checker",
  home: "Rarsu Score Checker home",
  description:
    "Rarsu Score Checker: type an osu! username and see their top 20/50 plays. Works for all four modes, no login needed.",
  currentMode: "Current mode: {mode}",
  visitOsu: "Visit osu!",
  playerLabel: "Player username or ID",
  playerPlaceholder: "Enter a player username or ID",
  query: "Search scores",
  querying: "Loading",
  waiting: "Waiting",
  mode: "Game mode",
  defaultMode: "Player default",
  downloadB50: "Download B50 image",
  downloadingB50: "Generating image…",
  downloadFailed: "Image download failed. Please try again.",
  bestPerformance: "Best performance",
  noLogin: "No sign-in required",
  publicScores: "Public scores",
  ownApi: "Use my osu! API credentials",
  ownApiDescription:
    "Enter the Client ID and Client Secret from your osu! OAuth application. This uses client credentials with the public scope, so user authorization is not needed and the Callback URL can be blank. Leave credentials blank to use the site's configuration.",
  clientId: "Client ID",
  clientSecret: "Client Secret",
  credentialsInMemory:
    "Credentials stay in this page's memory and are sent over HTTPS. You will need to enter them again after closing or refreshing the page.",
  createOauth: "Create an osu! OAuth application",
  httpsRequired:
    "For security, custom credentials can only be used over HTTPS (except localhost).",
  invalidCredentials: "Enter a valid Client ID and Client Secret.",
  unableToQuery: "Unable to load scores",
  loadingScores: "Loading player scores",
  loadingMode: "Fetching {mode} best performance…",
  playerScores: "Player scores",
  performance: "Performance",
  globalRank: "Global rank",
  accuracy: "Accuracy",
  scoreCount: "{count} scores",
  cached: "Cached",
  browserCached: "Browser cache",
  fetched: "Just fetched",
  noScores: "No best scores yet",
  noScoresMode: "This player has no public {mode} best performance scores.",
  srTitle: "Base star rating, without mods",
  srNote: "SR is the base difficulty without mods; pp comes from osu!.",
  updated: "Updated {date}",
  instructions: "Search instructions",
  startTitle: "Enter a player username or ID",
  startDescription:
    "Search using the player's default mode, or choose a mode manually.",
  keyStats: "Key stats",
  fourModes: "Four modes",
  unofficial: "Unofficial fan-made project. Not affiliated with peppy or osu!.",
  busyTitle: "The service is busy. Please wait.",
  busyDescription:
    "Your query has been saved while other searches are being processed.",
  retryCountdown: "Retrying automatically in {seconds}s",
  retryNow: "Retrying your search…",
  retryAttempt: "Retry {attempt} of 5",
  cancelWaiting: "Cancel waiting",
  busyExhausted: "The service is still busy. Please try again later.",
  networkError: "Unable to connect. Check your network and try again.",
  queryFailed: "The search failed. Please try again later.",
  retryAfter: "You can try again in {seconds}s.",
  PLAYER_NOT_FOUND: "Player not found. Check the username or ID.",
  INVALID_PLAYER: "Enter a username or ID between 1 and 32 characters.",
  INVALID_REQUEST: "Check the game mode, score type and limit.",
  RATE_LIMITED: "Too many searches. Please try again later.",
  UPSTREAM_ERROR: "osu! is temporarily unavailable. Please try again later.",
  NOT_CONFIGURED: "The server has not configured osu! OAuth credentials yet.",
  INVALID_CREDENTIALS: "Provide both a valid osu! Client ID and Client Secret.",
  SERVER_BUSY: "Too many searches are running. Please wait.",
  UPSTREAM_BUSY: "The service is waiting for osu! request capacity.",
};

export function detectLanguage(languages: readonly string[]): "zh" | "en" {
  for (const language of languages) {
    const prefix = language.toLowerCase().split(/[-_]/)[0];
    if (prefix === "zh" || prefix === "en") return prefix;
  }
  return "en";
}

export const language = detectLanguage(
  typeof navigator === "undefined" ? ["en"] : navigator.languages,
);
export const locale = language === "zh" ? "zh-CN" : "en-US";

export function t(
  key: MessageKey,
  values: Record<string, string | number> = {},
): string {
  const message = (language === "zh" ? zh : en)[key];
  return message.replace(/\{(\w+)\}/g, (placeholder, name: string) =>
    values[name] === undefined ? placeholder : String(values[name]),
  );
}

export function errorMessage(code: string): string {
  return Object.hasOwn(zh, code) ? t(code as MessageKey) : t("queryFailed");
}
