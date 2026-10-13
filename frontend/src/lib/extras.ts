import type { VideoDigestResult } from '@/types/result';
import { S } from '@/strings';

/** Sidebar navigation for extras blocks: key, title and the count shown on the right. */
export function extrasNav(
  result: VideoDigestResult,
): { key: string; title: string; count: string }[] {
  const ex = result.extras;
  const out: { key: string; title: string; count: string }[] = [];
  if (ex.glossary)
    out.push({
      key: 'glossary',
      title: S.extrasTitles.glossary,
      count: String(ex.glossary.length),
    });
  if (ex.critique) {
    const c = ex.critique;
    out.push({
      key: 'critique',
      title: S.extrasTitles.critique,
      count: `${c.strong.length} · ${c.weak.length} · ${c.missing.length}`,
    });
  }
  if (ex.self_check)
    out.push({
      key: 'self_check',
      title: S.extrasTitles.self_check,
      count: String(ex.self_check.length),
    });
  if (ex.decisions)
    out.push({
      key: 'decisions',
      title: S.extrasTitles.decisions,
      count: String(ex.decisions.length),
    });
  if (ex.action_items)
    out.push({
      key: 'action_items',
      title: S.extrasTitles.action_items,
      count: String(ex.action_items.length),
    });
  if (ex.questions)
    out.push({
      key: 'questions',
      title: S.extrasTitles.questions,
      count: String(ex.questions.length),
    });
  return out;
}
