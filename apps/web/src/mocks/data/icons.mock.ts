import type { WsIcons, SvgIcons, WsIconKey } from '../types/ui';

export const WS_ICONS: WsIcons = {
  server:   `<svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="14" height="6" rx="1.5"/><rect x="2" y="10" width="14" height="6" rx="1.5"/><circle cx="5" cy="5" r="0.8" fill="currentColor"/><circle cx="5" cy="13" r="0.8" fill="currentColor"/></svg>`,
  cloud:    `<svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 13.5a3.5 3.5 0 01-.35-6.97 5 5 0 019.7 0A3.5 3.5 0 0113.5 13.5h-9z"/></svg>`,
  shield:   `<svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 2l6 3v4c0 3.5-2.5 6.5-6 7.5-3.5-1-6-4-6-7.5V5l6-3z"/></svg>`,
  code:     `<svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="5.5 5 2 9 5.5 13"/><polyline points="12.5 5 16 9 12.5 13"/><line x1="10" y1="3" x2="8" y2="15"/></svg>`,
  database: `<svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="9" cy="4.5" rx="6" ry="2.5"/><path d="M3 4.5v9c0 1.38 2.69 2.5 6 2.5s6-1.12 6-2.5v-9"/><path d="M3 9c0 1.38 2.69 2.5 6 2.5s6-1.12 6-2.5"/></svg>`,
  flask:    `<svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M7 2h4M8 2v5l-4.5 7a1 1 0 00.87 1.5h9.26a1 1 0 00.87-1.5L10 7V2"/></svg>`,
  rocket:   `<svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 14l-2 2-1-3-3-1 2-2"/><path d="M12.5 2.5c-3 0-6.5 3-7.5 6l5 5c3-1 6-4.5 6-7.5a2.5 2.5 0 00-3.5-3.5z"/><circle cx="12" cy="6" r="1"/></svg>`,
  lock:     `<svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="8" width="10" height="8" rx="1.5"/><path d="M6 8V5.5a3 3 0 016 0V8"/></svg>`,
};

export const ICON_KEYS: WsIconKey[] = Object.keys(WS_ICONS) as WsIconKey[];

export const SVG: SvgIcons = {
  edit:   `<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M9.5 2.5l2 2L5 11H3V9l6.5-6.5z"/></svg>`,
  del:    `<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><polyline points="2,4 12,4"/><path d="M5 4V3a1 1 0 011-1h2a1 1 0 011 1v1"/><path d="M3 4l1 8a1 1 0 001 1h4a1 1 0 001-1l1-8"/></svg>`,
  github: `<svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>`,
  aws:    `<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 13.5a3.5 3.5 0 01-.35-6.97 5 5 0 019.7 0A3.5 3.5 0 0113.5 13.5h-9z"/></svg>`,
  check:  `<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="3 7 6 10 11 4"/></svg>`,
};
