import { useEffect, useState } from "react";
import { locale, t } from "./i18n";

export default function ResultFreshness({
  fetchedAt,
  refreshAt,
}: {
  fetchedAt: string;
  refreshAt: number | null;
}) {
  const [, tick] = useState(0);
  useEffect(() => {
    if (refreshAt === null || refreshAt <= Date.now()) return;
    const timer = setInterval(() => {
      tick((value) => value + 1);
      if (Date.now() >= refreshAt) clearInterval(timer);
    }, 1000);
    return () => clearInterval(timer);
  }, [refreshAt]);
  const seconds = Math.max(
    0,
    Math.ceil(((refreshAt ?? 0) - Date.now()) / 1000),
  );

  return (
    <div className="result-freshness">
      <span>
        {t("dataUpdated")} ·{" "}
        <time dateTime={fetchedAt}>
          {new Date(fetchedAt).toLocaleString(locale)}
        </time>
      </span>
      <span>
        {refreshAt === null
          ? t("dataRefreshUnknown")
          : seconds > 0
            ? t("dataRefreshIn", { seconds })
            : t("dataRefreshReady")}
      </span>
    </div>
  );
}
