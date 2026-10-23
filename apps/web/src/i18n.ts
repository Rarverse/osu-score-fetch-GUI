const zh = {
  appName: "Raru 查分器",
  clearInput: "清空用户名",
  recentSearches: "最近查询 · 仅保存在此浏览器",
  clearRecent: "清空记录",
  removeRecent: "移除 {name} 的记录",
  retry: "重新查询",
  loadingPlayer: "正在查询 {name}…",
  previousResult: "上次查询结果",
  downloadAgain: "再次下载",
  retryExport: "重试导出",
  previewImage: "预览生成的图片",
  quickNavigation: "快捷导航",
  searchAgain: "重新查询",
  backToTop: "返回顶部",

  home: "Raru 查分器首页",
  pageScroll: "页面滚动条",
  description:
    "Raru 查分器：输入 osu! 用户名，直接看 TA 的 Best 20/50 成绩。四个模式都能查，不用登录。",
  visitOsu: "访问 osu!",
  playerLabel: "玩家用户名或 ID",
  playerPlaceholder: "输入玩家用户名或 ID",
  query: "查询成绩",
  querying: "查询中",
  waiting: "等待中",
  mode: "游戏模式",
  defaultMode: "玩家默认",
  scoreLimit: "成绩数量",
  silverGrade: "银色 {grade}",
  downloadImage: "导出 Best {count} 图片",
  downloadingImage: "正在生成图片…",
  downloadTitle: "正在准备 B{count} 图片",
  downloadImages: "正在加载头像与曲绘：{completed} / {total}",
  downloadImageProgress: "图片素材加载进度",
  downloadRendering: "正在生成 PNG 图片…",
  downloadPacing: "首次加载需要按限速排队，请耐心等待，无需重复点击。",
  downloadReady: "图片已生成",
  downloadBrowser: "已交给浏览器下载，请查看下载列表。",
  downloadFailed: "图片下载失败，请稍后重试。",
  bestPerformance: "最佳表现",
  ownApi: "使用自己的 osu! API",
  ownApiRecommendation:
    "推荐使用自己的 osu! API 凭据，可在下方「使用自己的 osu! API」中配置。",
  ownApiDescription:
    "默认使用站点 API。启用下方选项后，请填写 osu! OAuth 应用的 Client ID 和 Client Secret（不是旧版 API Key）；可点击「显示」核对密钥。Callback URL 可留空。",
  clientId: "Client ID",
  clientSecret: "Client Secret",
  showSecret: "显示 API 密钥",
  hideSecret: "隐藏 API 密钥",
  show: "显示",
  hide: "隐藏",
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
  playTime: "游玩时长",
  globalRank: "全球排名",
  accuracy: "准确率",
  scoreCount: "{count} 条成绩",
  cached: "已缓存",
  browserCached: "本地缓存",
  fetched: "刚刚获取",
  dataUpdated: "数据更新时间",
  dataRefreshIn: "{seconds} 秒后可重新查询获取新数据",
  dataRefreshReady: "可重新查询获取新数据",
  dataRefreshUnknown: "暂无法确定可获取新数据的时间",
  noScores: "还没有最佳成绩",
  noScoresMode: "这位玩家目前没有公开的 {mode} best performance。",
  srTitle: "谱面基础 SR，未应用 mods",
  srNote: "SR 为谱面基础值（未应用 mods）；pp 为 osu! 返回值。",
  updated: "更新于 {date}",
  instructions: "查询说明",
  startTitle: "输入 osu! 玩家用户名或数字 ID，无需登录。",
  startDescription:
    "选择游戏模式和 Best 20 / Best 50；「玩家默认」会使用该玩家的首选模式。",
  downloadInstructions:
    "点击「查询成绩」查看最佳表现；查询完成后，可下载对应的 B20 / B50 PNG 图片。",
  keyStats: "关键数据",
  fourModes: "四种模式",
  unofficial: "非官方，与 osu! 无关联",
  busyTitle: "查询服务繁忙，请稍候",
  busyDescription: "查询通道正忙，将自动重试，也可以取消等待。",
  upstreamBusyDescription:
    "正在等待 osu! API 请求额度恢复。使用自己的 API 也需遵守站点与上游限流；恢复后自动重试。",
  retryCountdown: "{seconds} 秒后自动重试",
  retryNow: "正在重新查询…",
  retryAttempt: "第 {attempt} / 5 次重试",
  cancelWaiting: "取消等待",
  cancelQuery: "取消查询",
  requestTimeout: "查询超时，请稍后重试。",
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
  INVALID_CREDENTIALS:
    "API 凭据无效，请核对 osu! Client ID 和 Client Secret；可点击「显示」检查密钥。",
  SERVER_BUSY: "当前查询人数较多，请稍候。",
  UPSTREAM_BUSY: "查询服务正在等待 osu! 请求额度。",
};

type MessageKey = keyof typeof zh;

const en: Record<MessageKey, string> = {
  appName: "Raru Score Fetcher",
  clearInput: "Clear username",
  recentSearches: "Recent searches · saved in this browser",
  clearRecent: "Clear history",
  removeRecent: "Remove {name} from history",
  retry: "Retry search",
  loadingPlayer: "Loading scores for {name}…",
  previousResult: "Previous search result",
  downloadAgain: "Download again",
  retryExport: "Retry export",
  previewImage: "Preview generated image",
  quickNavigation: "Quick navigation",
  searchAgain: "Search again",
  backToTop: "Back to top",

  home: "Raru Score Fetcher home",
  pageScroll: "Page scrollbar",
  description:
    "Raru Score Fetcher: type an osu! username and see their best 20/50 plays. Works for all four modes, no login needed.",
  visitOsu: "Visit osu!",
  playerLabel: "Player username or ID",
  playerPlaceholder: "Enter a player username or ID",
  query: "Search scores",
  querying: "Loading",
  waiting: "Waiting",
  mode: "Game mode",
  defaultMode: "Player default",
  scoreLimit: "Number of scores",
  silverGrade: "Silver {grade}",
  downloadImage: "Export Best {count} image",
  downloadingImage: "Generating image…",
  downloadTitle: "Preparing B{count} image",
  downloadImages: "Loading avatar and covers: {completed} / {total}",
  downloadImageProgress: "Artwork loading progress",
  downloadRendering: "Generating PNG image…",
  downloadPacing:
    "New artwork loads in a rate-limited queue. Please wait; no need to click again.",
  downloadReady: "Image generated",
  downloadBrowser: "The image was sent to your browser. Check your downloads.",
  downloadFailed: "Image download failed. Please try again.",
  bestPerformance: "Best performance",
  ownApi: "Use my osu! API credentials",
  ownApiRecommendation:
    "We recommend using your own osu! API credentials. Configure them below under “Use my osu! API credentials”.",
  ownApiDescription:
    "The site API is used by default. Enable the option below to enter your osu! OAuth Client ID and Client Secret (not a legacy API key). Select Show to check your secret. The Callback URL can be blank.",
  clientId: "Client ID",
  clientSecret: "Client Secret",
  showSecret: "Show API secret",
  hideSecret: "Hide API secret",
  show: "Show",
  hide: "Hide",
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
  playTime: "Play time",
  globalRank: "Global rank",
  accuracy: "Accuracy",
  scoreCount: "{count} scores",
  cached: "Cached",
  browserCached: "Browser cache",
  fetched: "Just fetched",
  dataUpdated: "Data updated",
  dataRefreshIn: "Search again in {seconds}s to fetch fresh data",
  dataRefreshReady: "Search again to fetch fresh data",
  dataRefreshUnknown: "Fresh data availability is unknown",
  noScores: "No best scores yet",
  noScoresMode: "This player has no public {mode} best performance scores.",
  srTitle: "Base star rating, without mods",
  srNote: "SR is the base difficulty without mods; pp comes from osu!.",
  updated: "Updated {date}",
  instructions: "Search instructions",
  startTitle: "Enter an osu! username or numeric ID. No sign-in required.",
  startDescription:
    "Choose a mode and Best 20 / Best 50. Player default uses the player's preferred mode.",
  downloadInstructions:
    "Select Search scores to view their best plays, then download a B20 / B50 PNG image.",
  keyStats: "Key stats",
  fourModes: "Four modes",
  unofficial: "Unofficial · Not affiliated with osu!",
  busyTitle: "The service is busy. Please wait.",
  busyDescription:
    "The query service is busy. We will retry automatically; you can cancel at any time.",
  upstreamBusyDescription:
    "Waiting for osu! API capacity. Personal credentials still follow site and upstream limits. We will retry automatically.",
  retryCountdown: "Retrying automatically in {seconds}s",
  retryNow: "Retrying your search…",
  retryAttempt: "Retry {attempt} of 5",
  cancelWaiting: "Cancel waiting",
  cancelQuery: "Cancel query",
  requestTimeout: "The query timed out. Please try again.",
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
  INVALID_CREDENTIALS:
    "Invalid API credentials. Check your osu! Client ID and Client Secret; select Show to inspect the secret.",
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
