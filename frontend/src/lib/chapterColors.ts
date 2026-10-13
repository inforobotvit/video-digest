/** Nine chapter colours from the mockup, as CSS variables so the theme can swap them (c13). */
export const CHAPTER_COUNT = 9;

export function chapterColor(index: number): string {
  return `var(--ch-${index % CHAPTER_COUNT})`;
}

/** Quote highlight: the chapter colour mixed into the page background, lighter or darker by theme. */
export function chapterTint(color: string): string {
  return `color-mix(in srgb, ${color} var(--tint-mix), var(--bg))`;
}
