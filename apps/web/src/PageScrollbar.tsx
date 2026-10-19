import {
  type KeyboardEvent,
  type PointerEvent,
  useEffect,
  useRef,
  useState,
} from "react";
import { t } from "./i18n";

export default function PageScrollbar() {
  const [page, setPage] = useState({ top: 0, height: 1, viewport: 1 });
  const dragOffset = useRef<number | null>(null);

  useEffect(() => {
    let frame = 0;
    const measure = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        setPage({
          top: window.scrollY,
          height: document.documentElement.scrollHeight,
          viewport: window.innerHeight,
        });
      });
    };
    const observer = new ResizeObserver(measure);
    observer.observe(document.body);
    window.addEventListener("scroll", measure, { passive: true });
    window.addEventListener("resize", measure);
    measure();
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", measure);
      window.removeEventListener("resize", measure);
    };
  }, []);

  const maximum = Math.max(0, page.height - page.viewport);
  const thumbHeight = Math.min(
    page.viewport,
    Math.max(36, page.viewport ** 2 / page.height),
  );
  const travel = page.viewport - thumbHeight;
  const thumbTop = maximum
    ? (Math.min(maximum, Math.max(0, page.top)) / maximum) * travel
    : 0;

  function move(event: PointerEvent<HTMLDivElement>, offset: number) {
    const track = event.currentTarget.getBoundingClientRect();
    const fraction = travel ? (event.clientY - track.top - offset) / travel : 0;
    window.scrollTo({
      top: Math.max(0, Math.min(1, fraction)) * maximum,
      behavior: "instant",
    });
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const steps: Record<string, number> = {
      ArrowDown: 40,
      ArrowUp: -40,
      PageDown: page.viewport * 0.9,
      PageUp: -page.viewport * 0.9,
      Home: -maximum,
      End: maximum,
    };
    if (!(event.key in steps)) return;
    event.preventDefault();
    window.scrollBy({ top: steps[event.key], behavior: "instant" });
  }

  return (
    <div
      className="page-scrollbar"
      role="scrollbar"
      aria-label={t("pageScroll")}
      aria-controls="root"
      aria-orientation="vertical"
      aria-valuemin={0}
      aria-valuemax={maximum}
      aria-valuenow={Math.round(Math.min(maximum, Math.max(0, page.top)))}
      tabIndex={0}
      onKeyDown={onKeyDown}
      onPointerDown={(event) => {
        if (event.button !== 0) return;
        event.preventDefault();
        event.currentTarget.focus();
        const relative =
          event.clientY - event.currentTarget.getBoundingClientRect().top;
        dragOffset.current =
          relative >= thumbTop && relative <= thumbTop + thumbHeight
            ? relative - thumbTop
            : thumbHeight / 2;
        event.currentTarget.setPointerCapture(event.pointerId);
        move(event, dragOffset.current);
      }}
      onPointerMove={(event) => {
        if (dragOffset.current !== null) move(event, dragOffset.current);
      }}
      onPointerUp={(event) => {
        if (event.currentTarget.hasPointerCapture(event.pointerId)) {
          event.currentTarget.releasePointerCapture(event.pointerId);
        }
      }}
      onLostPointerCapture={() => {
        dragOffset.current = null;
      }}
    >
      <div
        className="page-scrollbar-thumb"
        style={{ height: thumbHeight, top: thumbTop }}
      />
    </div>
  );
}
