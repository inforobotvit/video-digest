import { onLinkClick } from '@/lib/router';
import { S } from '@/strings';
import { CONTACTS, TELEGRAM_HREF } from '@/lib/contacts';
import './Footer.css';

/**
 * One grey line at the bottom of the page: retention, the policy link and the author's Telegram.
 * Not on the result page (the player is pinned there) and not on the policy page itself.
 */
export function Footer() {
  return (
    <footer className="foot">
      <span>{S.footerRetention}</span>
      <span className="foot__dot">·</span>
      <a href="/policy" onClick={onLinkClick}>
        {S.footerPolicy}
      </a>
      <span className="foot__dot">·</span>
      <a href={TELEGRAM_HREF} target="_blank" rel="noopener noreferrer">
        {S.footerAuthor(CONTACTS.author, CONTACTS.telegram)}
      </a>
    </footer>
  );
}
