import { Link2, Mail, Moon, Send, Sun } from 'lucide-react';
import { onLinkClick } from '@/lib/router';
import { shareLink } from '@/lib/exportFile';
import { S } from '@/strings';
import { useTheme } from '@/lib/theme';
import { CONTACTS, MAIL_HREF, TELEGRAM_HREF } from '@/lib/contacts';
import { DownloadMenu } from './DownloadMenu';
import './Header.css';

interface HeaderProps {
  /** result page: «Скачать» menu (c8) and «Поделиться» for this job */
  jobId?: string;
  /** result page: the survey button (step E2); thanks in its place after an answer */
  feedback?: { rated: boolean; onOpen: () => void };
  /** home: wordmark and theme only, no border unless `bordered` (mockups 3.1, 3.3) */
  variant?: 'default' | 'home';
  bordered?: boolean;
}

/**
 * Top bar from the mockups (c12). The interface is Russian only (brief), so there is no language
 * button. On mobile (turn 4) the actions collapse to icons and «Новая задача» goes: the wordmark
 * leads home. The theme toggle has two states (brief): light or dark, remembered in localStorage.
 * Right of it, two contact icons the same size: mail and Telegram (opens in a new tab).
 */
export function Header({ jobId, feedback, variant = 'default', bordered = true }: HeaderProps) {
  const [current, toggle] = useTheme();
  const label = current === 'dark' ? S.themeLight : S.themeDark;
  const theme = (
    <button
      type="button"
      className="btn btn--icon"
      onClick={toggle}
      title={label}
      aria-label={label}
      aria-pressed={current === 'dark'}
    >
      {current === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  );
  const contacts = (
    <>
      <a
        className="btn btn--icon"
        href={MAIL_HREF}
        title={`${S.contactMail} · ${CONTACTS.email}`}
        aria-label={S.contactMail}
      >
        <Mail size={16} />
      </a>
      <a
        className="btn btn--icon"
        href={TELEGRAM_HREF}
        target="_blank"
        rel="noopener noreferrer"
        title={`${S.contactTelegram} · @${CONTACTS.telegram}`}
        aria-label={S.contactTelegram}
      >
        <Send size={16} />
      </a>
    </>
  );
  return (
    <header
      className={`hdr ${variant === 'home' ? 'hdr--home' : ''} ${bordered ? '' : 'hdr--plain'}`}
    >
      <div className="hdr__left">
        <a href="/" onClick={onLinkClick} className="hdr__logo">
          {S.appName}
        </a>
        {variant === 'default' && (
          <>
            <span className="hdr__sep hdr__new" />
            <a href="/" onClick={onLinkClick} className="btn btn--small hdr__new">
              {S.newJob}
            </a>
          </>
        )}
      </div>
      {variant === 'home' && (
        <div className="hdr__right hdr__right--icons">
          {theme}
          {contacts}
        </div>
      )}
      {jobId && (
        <div className="hdr__right">
          {feedback && (
            <button
              type="button"
              className="btn btn--collapsible hdr__rate"
              onClick={feedback.onOpen}
              disabled={feedback.rated}
              title={feedback.rated ? S.feedback.thanksShort : S.feedback.rate}
              aria-label={feedback.rated ? S.feedback.thanksShort : S.feedback.rate}
            >
              <span className="btn__text">
                {feedback.rated ? S.feedback.thanksShort : S.feedback.rate}
              </span>
            </button>
          )}
          <DownloadMenu jobId={jobId} />
          <button
            type="button"
            className="btn btn--primary btn--collapsible"
            onClick={() => void shareLink(jobId)}
            title={S.share}
            aria-label={S.share}
          >
            <Link2 size={15} />
            <span className="btn__text">{S.share}</span>
          </button>
          <span className="hdr__sep hdr__sep--gap" />
          {theme}
          {contacts}
        </div>
      )}
    </header>
  );
}
