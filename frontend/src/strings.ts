// All interface strings live here. Interface language is Russian only (see frontend/CLAUDE.md).
import { typoDeep, typoShort } from '@/lib/typo';

/** «в 1 месте», «в 2 местах», «в 11 местах». */
function placesWord(n: number): string {
  return n % 10 === 1 && n % 100 !== 11 ? 'месте' : 'местах';
}

const RAW = {
  appName: 'Video Digest',
  newJob: 'Новая задача',
  download: 'Скачать',
  share: 'Поделиться',
  themeDark: 'Тёмная тема',
  themeLight: 'Светлая тема',
  contactMail: 'Написать на почту',
  contactTelegram: 'Написать в Telegram',

  depth: 'Глубина',
  depth1: '1 минута',
  depth5: '5 минут',
  depthAll: 'Всё',
  /* short depth labels for the mobile bar (turn 4) */
  depth1Short: '1 мин',
  depth5Short: '5 мин',
  structure: 'Структура',
  toc: 'Оглавление',
  close: 'Закрыть',
  depthHint1: 'TL;DR и заголовки глав',
  depthHint5: (n: number) => `+ ${n} ${plural(n, 'тезис', 'тезиса', 'тезисов')} под главами`,
  depthHintAll: (words: number) =>
    `+ транскрипт · ${formatNumber(words)} ${plural(words, 'слово', 'слова', 'слов')}`,
  chaptersDeeper: (n: number) =>
    `${n} ${plural(n, 'глава раскрыта', 'главы раскрыты', 'глав раскрыто')} глубже`,
  chaptersOverridden: (n: number) =>
    `${n} ${plural(n, 'глава раскрыта', 'главы раскрыты', 'глав раскрыто')} иначе`,
  reset: 'сбросить',

  tldr: 'TL;DR',
  /** UMUX-Lite survey on the result page (step E2, 2026-09-23). */
  feedback: {
    rate: 'Оценить',
    thanksShort: 'Спасибо за оценку',
    title: 'Как вам выжимка?',
    intro: 'Два вопроса и, если хотите, пара слов. Это помогает понять, что чинить первым.',
    fits: 'Возможности сервиса соответствуют моим требованиям',
    easy: 'Сервисом легко пользоваться',
    scaleLow: 'не согласен',
    scaleHigh: 'полностью согласен',
    comment: 'Комментарий',
    commentHint: 'Не указывайте здесь персональные данные: имена, телефоны, адреса, почту.',
    replyHint: 'Если нужен ответ, напишите в Telegram или на почту из шапки.',
    counter: (n: number, max: number) => `${n}/${max}`,
    send: 'Отправить',
    sending: 'Отправляем…',
    skip: 'Не сейчас',
    close: 'Закрыть',
    thanksTitle: 'Спасибо!',
    thanksText:
      'Ответ записан. Ещё раз оценить эту задачу нельзя, но комментарий можно прислать в Telegram.',
    alreadyRated: 'Эта задача уже оценена, спасибо.',
    failed: 'Не удалось отправить. Попробуйте ещё раз через минуту.',
  },
  /** result.notices (result-schema section 2): what changes what the reader reads. Text agreed 2026-09-23. */
  notices: {
    label: 'Оговорки к транскрипту',
    show: 'Показать места',
    hide: 'Скрыть места',
    capped: (shown: number, total: number) => `Показаны первые ${shown} из ${total}.`,
    transcript_shortened: {
      title: 'Транскрипт мог быть сокращён',
      body: (n: number) =>
        `При очистке речи модель местами убирает больше, чем слова-паразиты. Мы это замечаем и просим её вернуть пропущенное, но в ${n} ${placesWord(n)} текст мог остаться короче сказанного.`,
    },
    clean_fallback: {
      title: 'Часть речи очищена без модели',
      body: (n: number) =>
        `На ${n} ${n === 1 ? 'участке' : 'участках'} модель не справилась с очисткой, и текст собран по правилам: слова-паразиты убраны, но предложения могли остаться менее гладкими.`,
    },
  },
  quote: 'Цитата',
  quoteLink: 'цитата',
  objection: 'Возражение',
  objectionsBadge: (n: number) => `${n} ${plural(n, 'возражение', 'возражения', 'возражений')}`,
  showPoints: (n: number) => `Тезисы · ${n}`,
  showTranscript: (min: number) => `Транскрипт · ${min} мин`,
  collapse: 'Свернуть',
  collapseToTitle: 'Свернуть до заголовка',
  noPoints: 'Тезисов нет.',
  openOnPlatform: 'Открыть на видео',

  processedIn: (text: string) => `обработано за ${text}`,
  axisLegend: 'толщина — глубина раскрытия',
  extras: 'Дополнительно',
  extrasTitles: {
    glossary: 'Глоссарий',
    critique: 'Критика',
    self_check: 'Проверь себя',
    decisions: 'Решения',
    action_items: 'Задачи',
    questions: 'Открытые вопросы',
  } as const,
  critiqueStrong: 'Сильные стороны',
  critiqueWeak: 'Слабые места',
  critiqueMissing: 'Чего не хватает',
  owner: 'ответственный',
  due: 'срок',

  presets: {
    lecture: 'Лекция',
    meeting: 'Совещание',
    talk: 'Доклад',
    interview: 'Интервью',
    plain: 'Выжимка',
  } as const,
  platforms: { youtube: 'YouTube', vk: 'VK Видео', rutube: 'Rutube', upload: 'Файл' } as Record<
    string,
    string
  >,
  languages: {
    ru: 'Русский',
    en: 'Английский',
    de: 'Немецкий',
    fr: 'Французский',
    es: 'Испанский',
    it: 'Итальянский',
    pt: 'Португальский',
    uk: 'Украинский',
    kk: 'Казахский',
    zh: 'Китайский',
    ja: 'Японский',
  } as Record<string, string>,

  // home (3.1)
  homeHeading: 'Превратите видео в конспект, который можно прочитать',
  linkPlaceholder: 'Ссылка на видео',
  orUpload: 'или загрузите файл',
  continue: 'Продолжить',
  checking: 'Проверяем…',
  changeLink: 'Изменить ссылку',
  uploadFile: 'Загрузить файл',
  clearLink: 'Очистить',
  dropHere: 'Отпустите, чтобы загрузить',
  cancelUpload: 'Отменить',
  videoLanguage: 'язык видео',
  /** Static note under the upload zone (step F, 2026-09-30): where a file goes, always visible. */
  uploadNote:
    'Файл уйдёт на обработку облачным ИИ-сервисам — распознавание речи и языковые модели. Не загружайте записи с конфиденциальной информацией и персональными данными.',
  uploadNoteLink: 'Как мы обрабатываем данные',
  sources: ['YouTube', 'VK Видео', 'Rutube', 'прямая ссылка'],
  formats: 'mp4 mov mkv webm mp3 m4a wav ogg flac',
  /** limits from GET /api/limits; nothing is printed until they arrive */
  maxSize: (mb: number) => `до ${mb} МБ`,
  maxDuration: (min: number) => `до ${min} минут`,
  fixtureLinks:
    'В режиме мока: любая ссылка с http даёт карточку; слова private, bot, long, unsupported в ссылке — ошибки; subs — вариант с субтитрами; notices — результат с оговоркой о сокращённом транскрипте; budget, busy и checkfail — отказы на запуске; fail и extrasfail — ошибки обработки. Готовые результаты: /jobs/sample, /jobs/audio, /jobs/direct, /jobs/rutube, /jobs/expired.',
  probeErrors: {
    unsupported_url: {
      title: 'Ссылку не понимаем.',
      text: 'Поддерживаем YouTube, VK Видео, Rutube и прямые ссылки на файл.',
    },
    private_or_removed: {
      title: 'Видео недоступно.',
      text: 'Оно приватное или удалено. Проверьте, открывается ли ссылка в браузере без входа в аккаунт, или загрузите файл.',
    },
    bot_check: {
      title: 'YouTube просит подтвердить, что вы не робот.',
      text: 'Скачайте видео сами и загрузите файл — результат будет тот же.',
    },
    unsupported_file: {
      title: 'Такой файл не подходит.',
      text: 'Поддерживаем mp4, mov, mkv, webm, mp3, m4a, wav, ogg, flac.',
    },
    /** 429 from nginx (contract section 6): per-address rate limit, unlike daily_limit and busy. */
    rate_limited: {
      title: 'Слишком много запросов с вашего адреса.',
      text: 'Подождите минуту и попробуйте снова.',
    },
    generic: { title: 'Не получилось проверить ссылку.', text: 'Попробуйте ещё раз через минуту.' },
  } as Record<string, { title: string; text: string }>,
  /** too_long: the limit comes from `max_duration_sec` in the response; null when it is missing. */
  probeTooLong: (min: number | null) =>
    min === null
      ? {
          title: 'Видео слишком длинное.',
          text: 'Выберите запись покороче или загрузите обрезанный файл.',
        }
      : {
          title: `Видео длиннее ${min} минут.`,
          text: `Принимаем записи до ${min} минут. Выберите запись покороче или загрузите обрезанный файл.`,
        },
  /** file_too_large: the ceiling comes from GET /api/limits; null when it has not arrived. */
  fileTooLarge: (mb: number | null) => ({
    title: 'Файл слишком большой.',
    text: `${mb === null ? 'Он больше, чем принимает сервис.' : `Максимум ${mb} МБ.`} Сожмите видео или извлеките аудиодорожку.`,
  }),
  probeStage: 'probe',
  blockFailed: 'Не удалось собрать этот блок',

  // source card (3.2)
  change: 'изменить',
  subsFound: 'Есть субтитры, обработаем за минуту',
  subsNone: (min: number) =>
    `Субтитров нет, транскрибируем — около ${min} ${plural(min, 'минуты', 'минут', 'минут')}`,
  subsNoneShort: (min: number) => `Субтитров нет, ~${min} мин`,
  run: 'Запустить',
  otherVideo: 'Другое видео',

  // settings (3.3, accordion since step E4)
  presetTitle: 'Пресет',
  presetHint: 'Набор блоков по умолчанию, любой можно добавить или снять',
  presetDescriptions: {
    lecture: 'Структура, тезисы, глоссарий и вопросы для самопроверки',
    meeting: 'Решения, задачи с ответственными, открытые вопросы',
    talk: 'Главная мысль, аргументы, цитаты и критика',
    interview: 'Позиции собеседников, где расходятся, цитаты',
    plain: 'TL;DR, структура и тезисы',
  } as const,
  presetNames: {
    lecture: 'Лекция',
    meeting: 'Совещание',
    talk: 'Доклад',
    interview: 'Интервью',
    plain: 'Просто выжимка',
  } as const,
  outputLanguage: 'Язык результата',
  videoLanguageIs: (lang: string) => `Язык видео — ${lang.toLowerCase()}`,
  optionLabels: {
    glossary: { title: 'Глоссарий' },
    critique: { title: 'Критика' },
    self_check: { title: 'Вопросы для самопроверки' },
    decisions: { title: 'Решения' },
    action_items: { title: 'Задачи и договорённости' },
    questions: { title: 'Открытые вопросы' },
  } as const,
  /** time addition of one block, from probe.estimate.per_option */
  addTime: (sec: number) => (sec < 60 ? `+${sec} с` : `+${Math.round(sec / 60)} мин`),
  readyIn: (min: number) => `Готово через ~${min} мин`,
  inLanguage: (lang: string) => `на ${lang}`,
  languagesPrepositional: {
    ru: 'русском',
    en: 'английском',
    de: 'немецком',
    fr: 'французском',
    es: 'испанском',
    it: 'итальянском',
    pt: 'португальском',
    uk: 'украинском',
    kk: 'казахском',
    zh: 'китайском',
    ja: 'японском',
  } as Record<string, string>,
  starting: 'Запускаем…',

  // my jobs (home, localStorage only)
  myJobs: 'Мои задачи',
  myJobsHint: 'список хранится в этом браузере',
  jobStatus: {
    processing: 'в обработке',
    done: 'готово',
    failed: 'ошибка',
    expired: 'удалено',
  } as const,
  removeFromList: 'Убрать из списка',
  startFailed: 'Не удалось запустить. Попробуйте ещё раз.',
  /** 429 on POST /api/jobs (contract section 6): retry offered only where waiting can help. */
  startErrors: {
    daily_limit: {
      text: 'Сегодня сервис исчерпал дневной лимит. Попробуйте завтра.',
      retry: false,
    },
    busy: {
      text: 'Сейчас обрабатываются другие задачи, попробуйте через несколько минут.',
      retry: true,
    },
    /** 403 from the Turnstile check (contract section 6): the widget did not confirm the browser. */
    bot_check_failed: {
      text: 'Не удалось подтвердить, что запрос из браузера. Обновите страницу и попробуйте снова.',
      retry: true,
    },
    /** 429 from nginx: too many requests from this address, not a service-wide limit. */
    rate_limited: {
      text: 'Слишком много запросов с вашего адреса. Подождите минуту.',
      retry: true,
    },
  } as Record<string, { text: string; retry: boolean }>,
  retryNow: 'Повторить',

  // waiting (3.4)
  processing: 'Обрабатываем',
  remaining: (min: number) => `осталось около ${min} ${plural(min, 'минуты', 'минут', 'минут')}`,
  remainingUnderMinute: 'осталось меньше минуты',
  longerThanUsual: 'чуть дольше обычного',
  stageNames: {
    download: 'Скачиваем',
    transcribe: 'Распознаём речь',
    clean: 'Чистим транскрипт',
    digest: 'Собираем выжимку',
    extras: 'Дополнительные блоки',
  } as const,
  stageProgress: (done: number, total: number) =>
    `${done} из ${total} ${plural(total, 'части', 'частей', 'частей')}`,
  stagePreparing: 'подготовка',
  notOrdered: 'не заказано',
  hasSubtitles: 'есть субтитры',
  stageFailedSoft:
    'Не удалось собрать. Результат откроется без них — повторить можно будет в самом блоке',
  canClose: 'Можно закрыть страницу.',
  saveLink: 'Сохраните ссылку: по ней будет результат, он хранится 30 дней.',
  copyLink: 'Скопировать ссылку',
  notifyAsk: 'Сообщить, когда будет готово?',
  notifyAllow: 'Разрешить',
  notifyDecline: 'Не надо',
  notifyDone: 'Выжимка готова',
  notifyFailed: 'Не удалось обработать',
  jobErrors: {
    /** Contract section 6: our side refused by the provider (401/403); the link is fine, a retry cannot help. */
    provider_auth: {
      title: 'Сбой на нашей стороне',
      text: 'С вашей ссылкой всё в порядке. Попробуйте позже.',
      retry: false,
    },
    stt_failed: {
      title: 'Не удалось распознать речь',
      text: 'Повтор обычно помогает. Если повторится — проверьте, есть ли в записи звук, или загрузите файл в другом формате.',
    },
    llm_failed: {
      title: 'Не удалось собрать выжимку',
      text: 'Повтор обычно помогает: модель иногда отвечает не по формату.',
    },
    timeout: {
      title: 'Обработка заняла слишком долго',
      text: 'Попробуйте ещё раз. Если видео очень длинное, обрежьте его или разбейте на части.',
    },
    bot_check: {
      title: 'YouTube просит подтвердить, что вы не робот',
      text: 'Мы не можем скачать это видео с сервера. Скачайте его сами и загрузите файл — результат будет тот же.',
    },
    private_or_removed: {
      title: 'Видео недоступно',
      text: 'Оно приватное или удалено. Проверьте ссылку или загрузите файл.',
    },
    source_gone: {
      title: 'Исходный файл уже удалён',
      text: 'Загрузите файл заново — обработка займёт столько же, сколько в первый раз.',
    },
    generic: {
      title: 'Не удалось обработать видео',
      text: 'Попробуйте ещё раз. Если повторится — загрузите файл или выберите другое видео.',
    },
  } as Record<string, { title: string; text: string; retry?: boolean }>,
  stoppedAt: (stage: string) => `Остановилось на этапе «${stage}»`,
  stoppedAtPart: (done: number, total: number) => `, на части ${done} из ${total}`,
  retry: 'Попробовать снова',
  retrying: 'Запускаем…',
  retryFailed: 'Не удалось запустить повтор.',
  otherVideoBtn: 'Другое видео',

  // service pages (3.6)
  notFoundCode: '404',
  notFoundText:
    'Проверьте ссылку — возможно, она скопирована не полностью. Если задача была, её результат мог быть удалён по сроку хранения.',
  /** a job whose identifying fields were removed after the retention period (title, link, cover) */
  expiredJobTitle: 'Запись удалена по сроку хранения',
  expiredCode: '410 · хранение 30 дней',
  expiredTitle: 'Результат удалён',
  expiredText: (date: string) =>
    `Мы храним результаты 30 дней, затем удаляем вместе с транскриптом и аудио. Этот срок истёк ${date}. Видео можно обработать заново — займёт столько же, сколько в первый раз.`,
  reprocess: 'Обработать заново',
  policyTitle: 'Как сервис обрабатывает данные',
  policyMeta: 'обновлено 11 октября 2026',

  // footer: on every page but the result (the player sits there) and the policy itself
  footerRetention: 'Результат хранится 30 дней',
  footerPolicy: 'Политика данных',
  footerAuthor: (name: string, handle: string) => `${name} · @${handle}`,

  // player (3.5, directions turn 5)
  play: 'Играть',
  pause: 'Пауза',
  speed: 'Скорость',
  mute: 'Выключить звук',
  unmute: 'Включить звук',
  toChapterEnd: (t: string) => `до конца главы ${t}`,
  showPicture: 'Картинка',
  showVideo: 'Видео',
  collapsePlayer: 'Свернуть',
  openOnPlatformNamed: (platform: string) => `Открыть на ${platform}`,
  platformControls: (platform: string) =>
    `${platform} · управление — в плеере платформы, полоска глав ниже перематывает его`,
  directControls: 'Прямая ссылка · управление — в плеере, полоска глав ниже перематывает его',
  playerLegend: 'плеер',
  playerFailed: 'Плеер платформы не смог загрузить видео — откройте его на платформе',

  // download menu (c8), share and toasts (c11)
  exportTitles: {
    'digest.md': 'Выжимка',
    'transcript.md': 'Транскрипт',
    'transcript.srt': 'Субтитры',
    'digest.html': 'HTML',
    'digest.pdf': 'PDF',
    'all.zip': 'Всё архивом',
  } as Record<string, string>,
  preparing: 'Готовим…',
  retryShort: 'Повторить',
  toastCopied: 'Ссылка скопирована',
  toastCopyFailed: 'Не удалось скопировать',
  toastFileReady: (name: string) => `Файл готов — ${name}`,
  toastExportNotReady: 'Файл ещё готовится',
  toastExportGone: 'Файл не найден: результат уже удалён',
  toastExportFailed: 'Не удалось скачать',

  loading: 'Загружаем…',
  notFoundTitle: 'Такой задачи нет или результат уже удалён',
  notFoundHint: 'Результаты хранятся 30 дней.',
  toHome: 'На главную',
  waitingTitle: 'Обрабатываем',
  waitingHint: 'Страница ожидания появится на следующем шаге. Обновите страницу позже.',
  homeTitle: 'Ссылка на видео или файл → выжимка и транскрипт',
  homeHint: 'Главная появится на шаге 2. В режиме мока доступны результаты на фикстурах:',
  errorGeneric: 'Не удалось загрузить результат. Попробуйте обновить страницу.',
};

/**
 * Interface strings after typograf: hanging prepositions, quotes, dashes. Preset cards and option
 * descriptions are short texts in narrow boxes and skip the non-breaking spaces (see typoShort).
 */
export const S: typeof RAW = {
  ...typoDeep(RAW),
  presetNames: typoDeep(RAW.presetNames, typoShort),
  presetDescriptions: typoDeep(RAW.presetDescriptions, typoShort),
  optionLabels: typoDeep(RAW.optionLabels, typoShort),
};

export function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few;
  return many;
}

export function formatNumber(n: number): string {
  return new Intl.NumberFormat('ru-RU').format(n);
}
