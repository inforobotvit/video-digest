// Author contacts: the header icons on every page and the footer signature (2026-09-11).
export const CONTACTS = {
  author: 'Виталий Туров',
  email: 'tuvitaliy@gmail.com',
  telegram: 'mewithrobot',
} as const;

export const MAIL_HREF = `mailto:${CONTACTS.email}`;
export const TELEGRAM_HREF = `https://t.me/${CONTACTS.telegram}`;
