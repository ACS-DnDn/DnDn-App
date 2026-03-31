import { useState, useEffect, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { checkDocumentReady } from '@/services/report.service';
import './GenerateProgress.css';

export type ProgressStatus = 'collecting' | 'generating' | 'done' | 'failed' | null;

interface Job {
  runId: string;
  status: ProgressStatus;
  progress: number; // 0-100
}

const POLL_INTERVAL = 5_000;
const TIMEOUT = 180_000; // 3분

// 전역 상태 — 여러 페이지에서 접근
let _setJob: ((j: Job | null) => void) | null = null;

export function startGenerateTracking(runId: string) {
  _setJob?.({ runId, status: 'collecting', progress: 5 });
}

export function GenerateProgress() {
  const navigate = useNavigate();
  const [job, setJob] = useState<Job | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval>>(undefined);
  const startRef = useRef(0);
  const dismissRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  // 전역 setter 등록
  useEffect(() => {
    _setJob = setJob;
    return () => { _setJob = null; };
  }, []);

  const cleanup = useCallback(() => {
    clearInterval(timerRef.current);
    timerRef.current = undefined;
  }, []);

  useEffect(() => {
    if (!job || job.status === 'done' || job.status === 'failed') {
      cleanup();
      return;
    }

    startRef.current = Date.now();

    // fake progress + 폴링
    timerRef.current = setInterval(async () => {
      const elapsed = Date.now() - startRef.current;

      // 타임아웃
      if (elapsed > TIMEOUT) {
        setJob(prev => prev ? { ...prev, status: 'failed', progress: 100 } : null);
        return;
      }

      // fake progress: 0→80% over ~2min
      const fakeProgress = Math.min(80, (elapsed / TIMEOUT) * 100 * 1.3);
      const fakeStatus: ProgressStatus = fakeProgress < 35 ? 'collecting' : 'generating';

      // 실제 폴링
      const result = await checkDocumentReady(job.runId);
      if (result) {
        setJob(prev => prev ? { ...prev, status: 'done', progress: 100 } : null);
        // 5초 후 자동 닫기
        dismissRef.current = setTimeout(() => setJob(null), 5000);
        return;
      }

      setJob(prev => {
        if (!prev || prev.status === 'done' || prev.status === 'failed') return prev;
        return { ...prev, status: fakeStatus, progress: Math.max(prev.progress, fakeProgress) };
      });
    }, POLL_INTERVAL);

    return cleanup;
  }, [job?.runId, cleanup]); // eslint-disable-line react-hooks/exhaustive-deps

  // 언마운트 시 dismiss timer 정리
  useEffect(() => {
    return () => { clearTimeout(dismissRef.current); };
  }, []);

  if (!job) return null;

  const statusLabel: Record<string, string> = {
    collecting: '데이터 수집 중...',
    generating: '보고서 생성 중...',
    done: '보고서 생성 완료',
    failed: '보고서 생성 실패',
  };

  return createPortal(
    <div className={`gen-progress ${job.status}`}>
      <div className="gen-progress-icon">
        {job.status === 'done' ? (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6L9 17l-5-5" /></svg>
        ) : job.status === 'failed' ? (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
        ) : (
          <div className="gen-spinner" />
        )}
      </div>
      <div className="gen-progress-body">
        <span className="gen-progress-label">{statusLabel[job.status ?? 'collecting']}</span>
        <div className="gen-progress-bar">
          <div className="gen-progress-fill" style={{ width: `${job.progress}%` }} />
        </div>
      </div>
      {job.status === 'done' && (
        <button
          className="gen-progress-link"
          onClick={() => { navigate('/documents'); setJob(null); }}
        >
          보기
        </button>
      )}
      {(job.status === 'done' || job.status === 'failed') && (
        <button className="gen-progress-close" onClick={() => setJob(null)}>
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="4" y1="4" x2="12" y2="12" /><line x1="12" y1="4" x2="4" y2="12" /></svg>
        </button>
      )}
    </div>,
    document.body,
  );
}
