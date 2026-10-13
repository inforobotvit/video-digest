import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { VideoDigestResult } from '@/types/result';
import { S } from '@/strings';
import type { Block } from '@/lib/settings';
import { Timecode } from './Timecode';

/** Extras blocks below the digest, anchored from the sidebar, in the page's own typography. */
export function ExtrasSections({
  result,
  onSeek,
}: {
  result: VideoDigestResult;
  onSeek: (s: number) => void;
}) {
  const ex = result.extras;
  const blocks: React.ReactNode[] = [];

  if (ex.glossary) {
    blocks.push(
      <Section key="glossary" id="glossary" title={S.extrasTitles.glossary}>
        {ex.glossary.map((g) => (
          <Item key={g.start + g.term} start={g.start} onSeek={onSeek}>
            <b>{g.term}</b> — {g.definition}
          </Item>
        ))}
      </Section>,
    );
  }
  if (ex.critique) {
    const c = ex.critique;
    blocks.push(
      <Section key="critique" id="critique" title={S.extrasTitles.critique} collapsible>
        <h3 className="xs__sub">{S.critiqueStrong}</h3>
        {c.strong.map((t, i) => (
          <Item key={i}>{t}</Item>
        ))}
        <h3 className="xs__sub">{S.critiqueWeak}</h3>
        {c.weak.map((w) => (
          <Item key={w.start + w.claim} start={w.start} onSeek={onSeek}>
            <b>{w.claim}</b> {w.issue}
          </Item>
        ))}
        <h3 className="xs__sub">{S.critiqueMissing}</h3>
        {c.missing.map((t, i) => (
          <Item key={i}>{t}</Item>
        ))}
      </Section>,
    );
  }
  if (ex.self_check) {
    blocks.push(
      <Section key="self_check" id="self_check" title={S.extrasTitles.self_check} collapsible>
        {ex.self_check.map((q, i) => (
          <Item key={i} start={q.start} onSeek={onSeek}>
            <b>{q.question}</b> {q.answer}
          </Item>
        ))}
      </Section>,
    );
  }
  if (ex.decisions) {
    blocks.push(
      <Section key="decisions" id="decisions" title={S.extrasTitles.decisions}>
        {ex.decisions.map((d, i) => (
          <Item key={i} start={d.start} onSeek={onSeek}>
            {d.text}
          </Item>
        ))}
      </Section>,
    );
  }
  if (ex.action_items) {
    blocks.push(
      <Section key="action_items" id="action_items" title={S.extrasTitles.action_items}>
        {ex.action_items.map((a, i) => (
          <Item key={i} start={a.start} onSeek={onSeek}>
            {a.text}
            {(a.owner || a.due) && (
              <span className="xs__meta">
                {a.owner && `${S.owner}: ${a.owner}`}
                {a.owner && a.due && ' · '}
                {a.due && `${S.due}: ${a.due}`}
              </span>
            )}
          </Item>
        ))}
      </Section>,
    );
  }
  if (ex.questions) {
    blocks.push(
      <Section key="questions" id="questions" title={S.extrasTitles.questions}>
        {ex.questions.map((q, i) => (
          <Item key={i} start={q.start} onSeek={onSeek}>
            {q.text}
          </Item>
        ))}
      </Section>,
    );
  }
  // Ordered blocks that never made it into the result (extras stage failed): a placeholder, no retry yet.
  // `options` is the full list of ordered blocks (since 2026-09-30 the preset adds none by itself).
  const ordered = new Set<Block>(result.options as Block[]);
  for (const key of ordered) {
    if (ex[key]) continue;
    blocks.push(
      <section key={`missing-${key}`} className="xs__section" id={`extras-${key}`}>
        <h2 className="xs__title">{S.extrasTitles[key]}</h2>
        <div className="xs__missing">
          {S.blockFailed}
          <span className="mono xs__missing-code">extras · failed</span>
        </div>
      </section>,
    );
  }
  if (blocks.length === 0) return null;
  return <div className="xs">{blocks}</div>;
}

/** Critique and self-check are collapsed by default and open on the heading; the sidebar counts stay. */
function Section({
  id,
  title,
  badge,
  collapsible,
  children,
}: {
  id: string;
  title: string;
  badge?: string;
  collapsible?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(!collapsible);
  return (
    <section className="xs__section" id={`extras-${id}`}>
      <h2 className="xs__title">
        {collapsible ? (
          <button
            type="button"
            className="xs__title-btn"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
          >
            {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            {title}
          </button>
        ) : (
          title
        )}
        {badge && <span className="xs__badge">{badge}</span>}
      </h2>
      {open && children}
    </section>
  );
}

function Item({
  start,
  onSeek,
  children,
}: {
  start?: number;
  onSeek?: (s: number) => void;
  children: React.ReactNode;
}) {
  return (
    <div className="row row--xs">
      <div className="row__gutter">
        {start !== undefined && <Timecode seconds={start} className="tc--faint" onSeek={onSeek} />}
      </div>
      <div className="row__text">
        <p className="xs__item">{children}</p>
      </div>
    </div>
  );
}
