import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSession } from '@/hooks/useSession';
import { getDashboard } from '@/services/dashboard.service';
import { getDocuments } from '@/services/document.service';
import type { DashboardData, Document } from '@/mocks';
import './DashboardPage.css';

export function DashboardPage() {
  const navigate = useNavigate();
  const session = useSession();
  const [data, setData] = useState<DashboardData | null>(null);
  const [allDocs, setAllDocs] = useState<Document[]>([]);

  useEffect(() => {
    getDashboard().then(setData).catch(console.error);
    getDocuments().then(({ items }) => setAllDocs(items)).catch(console.error);
  }, []);

  // 인사말
  const h = new Date().getHours();
  const greet = h < 12 ? '좋은 아침이에요' : h < 18 ? '안녕하세요' : '수고하셨어요';

  // 날짜
  const dateText = new Date().toLocaleDateString('ko-KR', {
    year: 'numeric', month: 'long', day: 'numeric', weekday: 'long',
  });

  // 시계
  const [time, setTime] = useState(() => new Date());
  const prevRef = useRef('');
  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const hh = String(time.getHours()).padStart(2, '0');
  const mm = String(time.getMinutes()).padStart(2, '0');
  const ss = String(time.getSeconds()).padStart(2, '0');
  const timeStr = hh + mm + ss;
  const digits = ['d-h1', 'd-h2', 'd-m1', 'd-m2', 'd-s1', 'd-s2'];
  const prev = prevRef.current;
  const changedDigits = digits.map((_, i) => prev !== '' && prev[i] !== timeStr[i]);
  prevRef.current = timeStr;

  // 상태 배지
  const statusMap: Record<string, { cls: string; label: string }> = {
    waiting: { cls: 'badge-waiting', label: '결재 대기' },
    rejected: { cls: 'badge-rejected', label: '반려' },
    done: { cls: 'badge-done', label: '완료' },
  };

  // 새로운 문서 (최신순 5개)
  const recentDocs = [...allDocs].sort((a, b) => b.date.localeCompare(a.date)).slice(0, 5);

  return (
    <div className="dashboard-page">
      {/* 히어로 */}
      <div className="hero-section">
        <div>
          <div className="hero-title">{greet}, {session.name}님</div>
          <div className="hero-actions">
            <button type="button" className="hero-btn" onClick={() => navigate('/report-settings')}>
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="8" cy="8" r="5.5" /><path d="M8 5v3l2 2" /></svg>
              보고서 생성
            </button>
            <button type="button" className="hero-btn" onClick={() => navigate('/plan')}>
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M9 2H4a1 1 0 00-1 1v10a1 1 0 001 1h8a1 1 0 001-1V6l-4-4z" /><path d="M9 2v4h4" /></svg>
              작업계획서 작성
            </button>
          </div>
        </div>
        <div className="hero-right">
          <div className="hero-date-text">{dateText}</div>
          <div className="hero-clock">
            {digits.map((id, i) => (
              <span key={id}>
                {i === 2 || i === 4 ? <span className="clock-sep">:</span> : null}
                <span className="digit-wrap">
                  <span className={`digit${changedDigits[i] ? ' changed' : ''}`} key={timeStr[i] + '-' + time.getTime()}>{timeStr[i]}</span>
                </span>
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* 문서 테이블 */}
      <div className="table-stack">
        {/* 처리할 문서 */}
        <div className="table-card">
          <div className="table-card-header">
            <div className="table-card-title">
              처리할 문서
              <span className="count-pill">{data?.pendingDocs.length ?? 0}</span>
            </div>
            <button type="button" className="table-link" onClick={() => navigate('/pending')}>전체 보기 →</button>
          </div>
          <table className="doc-table">
            <colgroup>
              <col style={{ width: '20%' }} />
              <col />
              <col style={{ width: '13%' }} />
              <col style={{ width: '15%' }} />
              <col style={{ width: '14%' }} />
            </colgroup>
            <thead>
              <tr>
                <th className="td-num">문서 번호</th>
                <th>제목</th>
                <th>유형</th>
                <th>작성자</th>
                <th>등록일</th>
              </tr>
            </thead>
            <tbody>
              {(data?.pendingDocs ?? []).length === 0 ? (
                <tr><td colSpan={5} className="empty-row">
                  <div className="empty-state">
                    <svg className="empty-ico" viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="8" y="6" width="32" height="36" rx="4"/><path d="M16 18h16M16 26h10"/><circle cx="34" cy="34" r="8" fill="var(--bg-card)" strokeWidth="2"/><path d="M31 34h6M34 31v6" strokeWidth="2"/></svg>
                    <span>처리 대기 중인 문서가 없습니다</span>
                  </div>
                </td></tr>
              ) : (data?.pendingDocs ?? []).map((d) => {
                const s = statusMap[d.status];
                return (
                  <tr key={d.docNum} onClick={() => navigate(`/viewer/${d.id}`)} onKeyDown={(e) => { if (e.key === 'Enter') navigate(`/viewer/${d.id}`); }} tabIndex={0} style={{ cursor: 'pointer' }}>
                    <td className="td-num">{d.docNum}</td>
                    <td>
                      <div className="doc-title-row">
                        <div className="doc-title">{d.title}</div>
                        {s && <span className={`badge ${s.cls}`}>{s.label}</span>}
                      </div>
                    </td>
                    <td className="td-type">{d.type}</td>
                    <td className="td-author">{d.author}</td>
                    <td className="td-date">{d.date}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* 새로운 문서 */}
        <div className="table-card">
          <div className="table-card-header">
            <div className="table-card-title">
              새로운 문서
              <span className="count-pill">{allDocs.length}</span>
            </div>
            <button type="button" className="table-link" onClick={() => navigate('/documents')}>전체 보기 →</button>
          </div>
          <table className="doc-table">
            <colgroup>
              <col style={{ width: '20%' }} />
              <col />
              <col style={{ width: '13%' }} />
              <col style={{ width: '15%' }} />
              <col style={{ width: '14%' }} />
            </colgroup>
            <thead>
              <tr>
                <th className="td-num">문서 번호</th>
                <th>제목</th>
                <th>유형</th>
                <th>작성자</th>
                <th>등록일</th>
              </tr>
            </thead>
            <tbody>
              {recentDocs.length === 0 ? (
                <tr><td colSpan={5} className="empty-row">
                  <div className="empty-state">
                    <svg className="empty-ico" viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="8" y="6" width="32" height="36" rx="4"/><path d="M16 18h16M16 26h10"/></svg>
                    <span>등록된 문서가 없습니다</span>
                  </div>
                </td></tr>
              ) : recentDocs.map((d) => (
                <tr key={d.id} onClick={() => navigate(`/viewer/${d.id}`)} onKeyDown={(e) => { if (e.key === 'Enter') navigate(`/viewer/${d.id}`); }} tabIndex={0} style={{ cursor: 'pointer' }}>
                  <td className="td-num">{d.docNum ?? String(d.id)}</td>
                  <td><div className="doc-title">{d.name}</div></td>
                  <td className="td-type">{d.type}</td>
                  <td className="td-author">{d.author}</td>
                  <td className="td-date">{d.date}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
