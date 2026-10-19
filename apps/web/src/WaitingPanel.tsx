import { Clock3 } from "lucide-react";
import { useEffect, useState } from "react";
import { t } from "./i18n";

export interface WaitingState {
  until: number;
  attempt: number;
  reason: string;
}

export default function WaitingPanel({
  waiting,
  onCancel,
}: {
  waiting: WaitingState;
  onCancel: () => void;
}) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(timer);
  }, []);
  const seconds = Math.max(0, Math.ceil((waiting.until - now) / 1000));

  return (
    <section className="waiting-panel" aria-labelledby="waiting-title">
      <Clock3 size={32} aria-hidden="true" />
      <h2 id="waiting-title">{t("busyTitle")}</h2>
      <p>
        {t(
          waiting.reason === "UPSTREAM_BUSY"
            ? "upstreamBusyDescription"
            : "busyDescription",
        )}
      </p>
      <p className="waiting-countdown">
        {seconds > 0 ? t("retryCountdown", { seconds }) : t("retryNow")}
        <span>{t("retryAttempt", { attempt: waiting.attempt })}</span>
      </p>
      <button type="button" onClick={onCancel}>
        {t("cancelWaiting")}
      </button>
    </section>
  );
}
