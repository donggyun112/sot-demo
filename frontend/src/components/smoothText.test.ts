import { expect, it } from "vitest";
import { nextLength } from "./smoothText";

it("closes the gap by a fraction of itself, so lag never accumulates", () => {
  // Far behind: a rush. Nearly caught up: a few characters. The point is that
  // a burst from the provider does not become a stutter on screen.
  expect(nextLength(0, 600) - 0).toBe(100);
  expect(nextLength(500, 600) - 500).toBe(17);
  expect(nextLength(596, 600) - 596).toBe(2);
});

it("never overshoots the text it has actually received", () => {
  expect(nextLength(9, 10)).toBe(10);
  expect(nextLength(10, 10)).toBe(10);
  // A shorter target than what is shown is a new message, not a rewind.
  expect(nextLength(50, 10)).toBe(10);
});

it("always advances, so the last character is never left behind", () => {
  let shown = 0;
  const total = 2000;
  for (let tick = 0; shown < total; tick++) {
    const next = nextLength(shown, total);
    expect(next).toBeGreaterThan(shown);
    shown = next;
    expect(tick).toBeLessThan(200);
  }
  expect(shown).toBe(total);
});
