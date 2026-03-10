import type { ReactNode } from 'react';

export type WsIconKey = 'server' | 'cloud' | 'shield' | 'code' | 'database' | 'flask' | 'rocket' | 'lock';
export type SvgKey = 'edit' | 'del' | 'github' | 'aws' | 'check';

export type WsIcons = Record<WsIconKey, ReactNode>;
export type SvgIcons = Record<SvgKey, ReactNode>;
