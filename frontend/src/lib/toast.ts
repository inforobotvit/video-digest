import { useSyncExternalStore } from 'react';

export interface ToastAction {
  label: string;
  run: () => void;
}
export interface Toast {
  id: number;
  text: string;
  tone?: 'error';
  action?: ToastAction;
}

/** Toasts (components c11): bottom centre, 3 s, longer when there is a button to press. */
const PLAIN_MS = 3000;
const ACTION_MS = 6000;

let toasts: Toast[] = [];
let seq = 0;
const listeners = new Set<() => void>();

function notify() {
  listeners.forEach((l) => l());
}

export function toast(text: string, opts: { tone?: 'error'; action?: ToastAction } = {}): void {
  const id = ++seq;
  toasts = [...toasts, { id, text, ...opts }];
  notify();
  setTimeout(() => dismiss(id), opts.action ? ACTION_MS : PLAIN_MS);
}

export function dismiss(id: number): void {
  if (!toasts.some((t) => t.id === id)) return;
  toasts = toasts.filter((t) => t.id !== id);
  notify();
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function useToasts(): Toast[] {
  return useSyncExternalStore(subscribe, () => toasts);
}
