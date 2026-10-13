import { S } from '@/strings';

export function TldrBlock({ text }: { text: string }) {
  return (
    <section className="row row--tldr" aria-label={S.tldr}>
      <div className="row__gutter row__gutter--tldr">
        <span className="tldr__diamond" />
      </div>
      <div className="row__text">
        <div className="eyebrow">{S.tldr}</div>
        <p className="tldr__text">{text}</p>
      </div>
    </section>
  );
}
