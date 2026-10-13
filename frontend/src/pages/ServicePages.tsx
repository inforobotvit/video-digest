import type { Job } from '@/api/types';
import { onLinkClick } from '@/lib/router';
import { S } from '@/strings';
import { CONTACTS, MAIL_HREF, TELEGRAM_HREF } from '@/lib/contacts';
import { Header } from '@/components/Header';
import { Footer } from '@/components/Footer';
import '@/components/job/job.css';

/** 404 (mockup 6a). */
export function NotFoundPage({ path }: { path?: string }) {
  return (
    <>
      <Header variant="home" />
      <main className="svc">
        <div className="svc__code">{S.notFoundCode}</div>
        <h1 className="svc__title">{S.notFoundTitle}</h1>
        <p className="svc__text">{S.notFoundText}</p>
        <div className="svc__actions">
          <a href="/" onClick={onLinkClick} className="btn btn--primary btn--job">
            {S.toHome}
          </a>
          {path && <span className="svc__path">{path}</span>}
        </div>
      </main>
      <Footer />
    </>
  );
}

/** Result removed after the retention period (mockup 6b): done job with result: null. */
export function ExpiredPage({
  job,
  onRetry,
  retrying,
  retryError,
}: {
  job: Job;
  onRetry: () => void;
  retrying: boolean;
  retryError: string | null;
}) {
  const date = job.finished_at
    ? new Date(Date.parse(job.finished_at) + 30 * 86400000).toLocaleDateString('ru-RU', {
        day: 'numeric',
        month: 'long',
      })
    : '';
  return (
    <>
      <Header variant="home" />
      <main className="svc">
        <div className="svc__code">{S.expiredCode}</div>
        <h1 className="svc__title">{S.expiredTitle}</h1>
        <p className="svc__text">{S.expiredText(date)}</p>
        <div className="svc__actions">
          {job.source.url && (
            <button
              type="button"
              className="btn btn--primary btn--job"
              onClick={onRetry}
              disabled={retrying}
            >
              {retrying ? S.retrying : S.reprocess}
            </button>
          )}
          <a
            href="/"
            onClick={onLinkClick}
            className={`btn btn--job ${job.source.url ? '' : 'btn--primary'}`}
          >
            {S.toHome}
          </a>
        </div>
        {retryError && <div className="settings__error">{retryError}</div>}
      </main>
      <Footer />
    </>
  );
}

const DEEPGRAM_POLICY = 'https://deepgram.com/privacy';
const OPENAI_POLICY = 'https://developers.openai.com/api/docs/guides/your-data';
const CLOUDFLARE_POLICY = 'https://www.cloudflare.com/privacypolicy/';

/**
 * Policy page: a copy of docs/privacy-policy.md, one to one (the file is the source, this page the copy). Every
 * sentence there is checked against the code; the retention numbers are the ones the configuration runs with.
 */
export function PolicyPage() {
  const ext = { target: '_blank', rel: 'noopener noreferrer' } as const;
  return (
    <>
      <Header variant="home" />
      <main className="policy">
        <h1 className="policy__title">{S.policyTitle}</h1>
        <div className="policy__meta">{S.policyMeta}</div>

        <section>
          <h2>Что мы принимаем</h2>
          <p>
            Ссылку на публичное видео или загруженный файл, выбранный пресет и опции, а также оценку
            результата (две оценки по пяти звёздам и необязательный комментарий). Аккаунтов нет,
            почту и телефон мы не спрашиваем. Комментарий к оценке не предназначен для персональных
            данных, об этом сказано у поля.
          </p>
        </section>

        <section>
          <h2>Куда уходят данные</h2>
          <p>
            Аудио отправляется в сервис распознавания речи, текст — в языковые модели; провайдеры
            обрабатывают данные по своим условиям:{' '}
            <a href={DEEPGRAM_POLICY} {...ext}>
              политика Deepgram
            </a>
            ,{' '}
            <a href={OPENAI_POLICY} {...ext}>
              политика OpenAI для API
            </a>
            . Для защиты от роботов страница обращается к Cloudflare Turnstile;{' '}
            <a href={CLOUDFLARE_POLICY} {...ext}>
              условия Cloudflare
            </a>
            . Мы не передаём провайдерам ничего, кроме самого аудио, текста, названия видео и
            служебных параметров запроса.
          </p>
          <p>
            Видео по ссылке воспроизводится на странице результата во встроенном плеере платформы
            (YouTube, VK Видео, Rutube), и платформа видит просмотр по своим правилам.
          </p>
        </section>

        <section>
          <h2>Что мы храним и сколько</h2>
          <p>
            Результат обработки (транскрипт и выжимка) хранится на сервере <b>30 дней</b> после
            завершения задачи, затем удаляется вместе с названием и ссылкой на видео. Служебные
            события задачи и внутренние журналы обработки хранятся 7 дней. После удаления остаются
            только цифры без содержания: длительность, платформа, языки, пресет, стоимость и статусы
            этапов.
          </p>
          <p>
            Загруженный файл удаляется сразу после извлечения аудио. Рабочее аудио удаляется после
            обработки, при сбое — не позже чем через 48 часов. Аудиодорожка для плеера у загруженных
            файлов хранится столько же, сколько результат.
          </p>
          <p>Оценки и комментарии хранятся вместе с идентификатором задачи, без срока.</p>
        </section>

        <section>
          <h2>Чего мы не делаем</h2>
          <p>
            Не храним IP-адреса, не ведём журналы обращений с адресами, не ставим свои cookies и не
            используем аналитику. Ссылка на результат содержит только идентификатор задачи; кто им
            владеет, тот и видит результат — не пересылайте ссылку, если результат не для чужих
            глаз.
          </p>
        </section>

        <section>
          <h2>Если у вас вопросы</h2>
          <p>
            Напишите на <a href={MAIL_HREF}>{CONTACTS.email}</a> или в Telegram{' '}
            <a href={TELEGRAM_HREF} {...ext}>
              @{CONTACTS.telegram}
            </a>{' '}
            — те же контакты, что в шапке страницы.
          </p>
        </section>
      </main>
    </>
  );
}
