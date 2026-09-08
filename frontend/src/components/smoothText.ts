import { useEffect, useRef, useState } from "react";

/**
 * Paced release of streamed text.
 *
 * A model does not arrive at a readable rate: it sends whatever a provider
 * flushes, so a reply lands in lumps — nothing, then a paragraph. Rendering
 * each lump as it comes is what makes generation look like a stutter rather
 * than like writing.
 *
 * So the arriving text is a target and the screen follows it, closing the gap
 * by a fraction of itself each tick: a few characters when nearly caught up, a
 * rush when far behind. The lag decays geometrically, so it never accumulates
 * and the last character is never late.
 */
const TICK_MS = 33;
/** Larger is calmer; smaller keeps up harder. */
const CATCH_UP = 6;
const MIN_STEP = 2;

/** How much of `target` to show next, given how much is showing now. */
export function nextLength(shown: number, total: number): number {
  if (shown >= total) return total;
  const backlog = total - shown;
  return Math.min(total, shown + Math.max(MIN_STEP, Math.ceil(backlog / CATCH_UP)));
}

/**
 * `target` is everything received so far; the return value is what to draw.
 * When `live` goes false the run is over, so the rest appears at once — a
 * finished answer must never sit half-written.
 */
export function useSmoothText(target: string, live: boolean): string {
  const [length, setLength] = useState(target.length);
  const shown = useRef(target.length);
  /* A new message starts over; anything else only ever grows. */
  const previous = useRef(target);
  if (!target.startsWith(previous.current)) {
    shown.current = 0;
    previous.current = target;
  } else {
    previous.current = target;
  }
  if (shown.current > target.length) shown.current = target.length;

  useEffect(() => {
    if (!live) {
      shown.current = target.length;
      setLength(target.length);
      return;
    }
    if (shown.current >= target.length) return;
    let frame = 0;
    let last = 0;
    const step = (now: number) => {
      if (now - last >= TICK_MS) {
        last = now;
        shown.current = nextLength(shown.current, target.length);
        setLength(shown.current);
      }
      if (shown.current < target.length) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [target, live]);

  return target.slice(0, Math.min(length, target.length));
}
