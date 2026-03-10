import { useEffect, useRef } from 'react';

interface AnimatedLogoProps {
  variant: 'light' | 'dark';
  className?: string;
}

const CHARS = ['D', 'n', 'D', 'n'] as const;
const CHAR_X = [0, 43.609375, 87.21875, 130.828125];
const CURSOR_X = [0, 43.609375, 87.21875, 130.828125, 194.4375];
const TYPE_GAP = 100;
const HOLD_MS = 30000;
const WAIT_MS = 1000;
const BLINK_MS = 500;

export function AnimatedLogo({ variant, className }: AnimatedLogoProps) {
  const bgRefs = useRef<(SVGTextElement | null)[]>([]);
  const fgRefs = useRef<(SVGTextElement | null)[]>([]);
  const cursorRef = useRef<SVGRectElement>(null);

  const bgColor = variant === 'dark' ? '#0d1117' : '#ffffff';
  const accentColor = variant === 'dark' ? '#4ADEAA' : '#228BE6';
  const nColor = variant === 'dark' ? '#ffffff' : '#0d1117';

  useEffect(() => {
    let cancelled = false;
    let blinkTimer: ReturnType<typeof setInterval> | null = null;

    const sleep = (ms: number) =>
      new Promise<void>((resolve) => {
        setTimeout(() => resolve(), ms);
      });

    const setCursorX = (idx: number) =>
      cursorRef.current?.setAttribute('x', String(CURSOR_X[idx]));

    const showCursor = () =>
      cursorRef.current?.setAttribute('opacity', '1');

    const showChar = (idx: number, visible: boolean) => {
      const v = visible ? '1' : '0';
      bgRefs.current[idx]?.setAttribute('opacity', v);
      fgRefs.current[idx]?.setAttribute('opacity', v);
    };

    const startBlink = () => {
      let state = true;
      showCursor();
      blinkTimer = setInterval(() => {
        state = !state;
        cursorRef.current?.setAttribute('opacity', state ? '1' : '0');
      }, BLINK_MS);
    };

    const stopBlink = () => {
      if (blinkTimer !== null) { clearInterval(blinkTimer); blinkTimer = null; }
      showCursor();
    };

    const run = async () => {
      while (!cancelled) {
        for (let i = 0; i < 4; i++) showChar(i, false);
        setCursorX(0);
        showCursor();

        await sleep(300);
        if (cancelled) break;

        stopBlink();
        for (let i = 0; i < 4; i++) {
          showChar(i, true);
          setCursorX(i + 1);
          await sleep(TYPE_GAP);
          if (cancelled) break;
        }
        if (cancelled) break;

        startBlink();
        await sleep(HOLD_MS);
        if (cancelled) break;
        stopBlink();

        for (let i = 3; i >= 0; i--) {
          showChar(i, false);
          setCursorX(i);
          await sleep(TYPE_GAP);
          if (cancelled) break;
        }
        if (cancelled) break;

        startBlink();
        await sleep(WAIT_MS);
        if (cancelled) break;
        stopBlink();
      }
    };

    run();

    return () => {
      cancelled = true;
      if (blinkTimer !== null) clearInterval(blinkTimer);
    };
  }, []);

  const fgColors = CHARS.map((c) => (c === 'D' ? accentColor : nColor));

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="-6 0 221.4375 100"
      className={className}
      style={{ backgroundColor: 'transparent' }}
    >
      {CHARS.map((char, i) => (
        <g key={i}>
          <text
            ref={(el) => { bgRefs.current[i] = el; }}
            y="88" fontFamily="'Courier New',monospace" fontSize="86" fontWeight="700"
            fill={bgColor} stroke={bgColor} strokeWidth="10" strokeLinejoin="round"
            x={CHAR_X[i]} opacity="0"
          >{char}</text>
          <text
            ref={(el) => { fgRefs.current[i] = el; }}
            y="88" fontFamily="'Courier New',monospace" fontSize="86" fontWeight="700"
            fill={fgColors[i]} stroke={fgColors[i]} strokeWidth="3"
            x={CHAR_X[i]} opacity="0"
          >{char}</text>
        </g>
      ))}
      <rect
        ref={cursorRef}
        rx="1" fill={accentColor}
        x="0" y="16.390625" width="11" height="97.4375"
      />
    </svg>
  );
}
