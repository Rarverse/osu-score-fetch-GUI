import { Check, ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { t } from "./i18n";

export default function ScoreLimitSelect({
  value,
  disabled,
  onChange,
}: {
  value: number;
  disabled: boolean;
  onChange: (value: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLFieldSetElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const options = useRef<(HTMLButtonElement | null)[]>([]);

  useEffect(() => {
    if (!open) return;
    options.current[value === 50 ? 1 : 0]?.focus();
    const dismiss = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", dismiss);
    return () => document.removeEventListener("pointerdown", dismiss);
  }, [open, value]);

  return (
    <fieldset
      aria-label={t("scoreLimit")}
      className="limit-select"
      ref={root}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}
    >
      <button
        ref={trigger}
        className="limit-trigger"
        type="button"
        disabled={disabled}
        aria-label={`${t("scoreLimit")}: Best ${value}`}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls="score-limit-menu"
        onClick={() => setOpen(!open)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            setOpen(true);
          }
        }}
      >
        Best {value}
        <ChevronDown size={14} aria-hidden="true" />
      </button>
      <div
        id="score-limit-menu"
        className="limit-menu"
        role="menu"
        aria-label={t("scoreLimit")}
        aria-hidden={!open}
        inert={!open}
        data-open={open}
        onKeyDown={(event) => {
          const index = options.current.indexOf(
            document.activeElement as HTMLButtonElement,
          );
          if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
            event.preventDefault();
            const next =
              event.key === "Home"
                ? 0
                : event.key === "End"
                  ? 1
                  : (index + 1) % 2;
            options.current[next]?.focus();
          } else if (event.key === "Escape") {
            event.preventDefault();
            setOpen(false);
            trigger.current?.focus();
          }
        }}
      >
        {[20, 50].map((count, index) => (
          <button
            key={count}
            type="button"
            ref={(element) => {
              options.current[index] = element;
            }}
            role="menuitemradio"
            aria-checked={value === count}
            tabIndex={-1}
            onClick={() => {
              setOpen(false);
              trigger.current?.focus();
              onChange(count);
            }}
          >
            Best {count}
            <Check
              size={14}
              aria-hidden="true"
              style={{ opacity: value === count ? 1 : 0 }}
            />
          </button>
        ))}
      </div>
    </fieldset>
  );
}
