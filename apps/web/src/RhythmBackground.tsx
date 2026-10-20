import { useLayoutEffect, useRef, useState } from "react";

const random = (min: number, max: number) => min + Math.random() * (max - min);
const shapes = ["circle", "triangle", "star", "diamond"] as const;
const paths = {
  circle: "M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18",
  triangle: "M12 3 22 21H2Z",
  star: "m12 2 3.1 6.5 7.2 1-5.2 5.1 1.2 7.2-6.3-3.4-6.3 3.4 1.2-7.2L1.7 9.5l7.2-1Z",
  diamond: "m12 2 9 10-9 10L3 12Z",
};
const colors = ["#c9b2ff", "#b6cde5", "#dbb8d0"];
const sparkIds = Array.from({ length: 20 }, (_, index) => index);
const placement = (container: HTMLElement) => ({
  x: random(16, Math.max(16, container.clientWidth - 16)),
  y: random(24, Math.max(24, container.clientHeight - 24)),
  size: random(8, 22),
  shape: shapes[Math.floor(Math.random() * shapes.length)],
  flash: Math.random() < 0.16,
  color: colors[Math.floor(Math.random() * colors.length)],
  angle: random(-25, 25),
});

function Spark() {
  const [timing] = useState(() => ({
    duration: random(4.5, 8),
    delay: random(-8, 0),
  }));
  const element = useRef<HTMLSpanElement>(null);
  const [point, setPoint] = useState<ReturnType<typeof placement> | null>(null);
  useLayoutEffect(() => {
    const container = element.current?.parentElement;
    if (container) setPoint(placement(container));
  }, []);
  return (
    <span
      ref={element}
      className={`rhythm-spark${point?.flash ? " rhythm-spark-flash" : ""}`}
      style={{
        left: point?.x,
        top: point?.y,
        width: point?.size,
        height: point?.size,
        visibility: point ? undefined : "hidden",
        color: point?.flash ? "#e3d8ff" : point?.color,
        animationDuration: `${timing.duration}s`,
        animationDelay: `${timing.delay}s`,
      }}
      // Relocate only at the invisible end of each pulse.
      onAnimationIteration={(event) => {
        const container = event.currentTarget.parentElement;
        if (container) setPoint(placement(container));
      }}
    >
      <svg
        className="rhythm-spark-shape"
        viewBox="0 0 24 24"
        aria-hidden="true"
        style={{ rotate: `${point?.angle ?? 0}deg` }}
      >
        <path d={paths[point?.shape ?? "circle"]} />
      </svg>
    </span>
  );
}

export default function RhythmBackground() {
  return (
    <div className="beat-background" aria-hidden="true">
      {sparkIds.map((id) => (
        <Spark key={id} />
      ))}
    </div>
  );
}
