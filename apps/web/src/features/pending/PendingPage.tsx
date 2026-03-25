import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { getDocuments } from '@/services/document.service';
import type { Document } from '@/mocks/types/document';
import './PendingPage.css';

const PAGE_SIZE = 10;

function formatDate(d: string) {
  const utc = new Date(d.includes('T') ? d : d.replace(' ', 'T'));
  if (isNaN(utc.getTime())) {
    const parts = d.split(' ');
    const dp = (parts[0] ?? '').split('-');
    return `${dp[0] ?? ''}.${dp[1] ?? ''}.${dp[2] ?? ''} ${parts[1]?.slice(0, 5) ?? ''}`.trim();
  }
  const ko = new Date(utc.toLocaleString('en-US', { timeZone: 'Asia/Seoul' }));
  const y = ko.getFullYear();
  const m = String(ko.getMonth() + 1).padStart(2, '0');
  const day = String(ko.getDate()).padStart(2, '0');
  const hh = String(ko.getHours()).padStart(2, '0');
  const mi = String(ko.getMinutes()).padStart(2, '0');
  return `${y}.${m}.${day} ${hh}:${mi}`;
}

function pad(n: number) { return String(n).padStart(2, '0'); }

function fmtShort(ds: string) {
  const parts = ds.split('-');
  return `${(parts[0] ?? '').slice(2)}.${parts[1] ?? ''}.${parts[2] ?? ''}`;
}

export function PendingPage() {
  const navigate = useNavigate();
  const [allDocs, setAllDocs] = useState<Document[]>([]);

  const [searchField, setSearchField] = useState<'name' | 'author'>('name');
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [currentPage, setCurrentPage] = useState(1);

  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());

  // 날짜 피커
  const [pickStart, setPickStart] = useState<string | null>(null);
  const [pickEnd, setPickEnd] = useState<string | null>(null);
  const [pickStep, setPickStep] = useState(0);
  const [hoverDate, setHoverDate] = useState<string | null>(null);
  const [calOpen, setCalOpen] = useState(false);
  const [calYear, setCalYear] = useState(() => new Date().getFullYear());
  const [calMonth, setCalMonth] = useState(() => new Date().getMonth());
  const datePickerRef = useRef<HTMLDivElement>(null);

  useEffect(() => { getDocuments({ tab: 'action' }).then(({ items }) => setAllDocs(items)).catch(console.error); }, []);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (calOpen && datePickerRef.current && !datePickerRef.current.contains(e.target as Node)) {
        setCalOpen(false);
        setHoverDate(null);
      }
    }
    document.addEventListener('click', handleClick);
    return () => document.removeEventListener('click', handleClick);
  }, [calOpen]);

  // 처리할 문서: action !== null
  const pendingTotal = useMemo(() => allDocs.filter(d => d.action !== null).length, [allDocs]);

  const filtered = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();
    let docs = allDocs.filter(d => d.action !== null);

    if (q) {
      if (searchField === 'author') docs = docs.filter(d => d.author.toLowerCase().includes(q));
      else docs = docs.filter(d => d.name.toLowerCase().includes(q));
    }
    if (statusFilter) docs = docs.filter(d => d.status === statusFilter);
    if (pickStep === 2) {
      if (pickStart) docs = docs.filter(d => d.date >= pickStart);
      if (pickEnd) docs = docs.filter(d => d.date <= pickEnd + ' 23:59');
    }

    return [...docs].sort((a, b) => b.date.localeCompare(a.date));
  }, [allDocs, searchQuery, searchField, statusFilter, pickStep, pickStart, pickEnd]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageDocs = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  const allChecked = pageDocs.length > 0 && pageDocs.every(d => selectedIds.has(d.id));
  const someChecked = pageDocs.some(d => selectedIds.has(d.id));

  const resetPage = useCallback(() => setCurrentPage(1), []);

  const toggleSelect = (id: string, checked: boolean) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      checked ? next.add(id) : next.delete(id);
      return next;
    });
  };

  const toggleSelectAll = (checked: boolean) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      pageDocs.forEach(d => checked ? next.add(d.id) : next.delete(d.id));
      return next;
    });
  };

  const handleRowClick = (doc: Document) => {
    navigate(`/viewer/${doc.id}?from=pending`);
  };

  // 날짜 피커
  const clearDates = () => { setPickStart(null); setPickEnd(null); setPickStep(0); setHoverDate(null); resetPage(); };
  const toggleCalPicker = (e: React.MouseEvent) => { e.stopPropagation(); setCalOpen(prev => !prev); if (!calOpen) setHoverDate(null); };
  const calPrevMonth = () => { if (calMonth === 0) { setCalMonth(11); setCalYear(y => y - 1); } else setCalMonth(m => m - 1); };
  const calNextMonth = () => { if (calMonth === 11) { setCalMonth(0); setCalYear(y => y + 1); } else setCalMonth(m => m + 1); };

  const onCalDayClick = (ds: string) => {
    if (pickStep === 0 || pickStep === 2) {
      setPickStart(ds); setPickEnd(null); setPickStep(1);
    } else {
      let s = pickStart!; let e = ds;
      if (ds === s) e = ds;
      else if (ds < s) { e = s; s = ds; }
      setPickStart(s); setPickEnd(e); setPickStep(2);
      setHoverDate(null); setCalOpen(false); resetPage();
    }
  };

  const MONTHS = ['1월','2월','3월','4월','5월','6월','7월','8월','9월','10월','11월','12월'];
  const today = new Date();
  const todayStr = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`;
  const firstDay = new Date(calYear, calMonth, 1).getDay();
  const daysInMonth = new Date(calYear, calMonth + 1, 0).getDate();
  const rE = pickStep === 1 && hoverDate ? hoverDate : pickEnd;
  const rS = pickStart;

  function getDayClass(ds: string) {
    let cls = 'cal-day';
    if (rS && rE) {
      const lo = rS < rE ? rS : rE; const hi = rS < rE ? rE : rS;
      if (ds === lo && ds === hi) cls += ' cal-day-start cal-day-end';
      else if (ds === lo) cls += ' cal-day-start';
      else if (ds === hi) cls += ' cal-day-end';
      else if (ds > lo && ds < hi) cls += ' cal-day-range';
    } else if (rS && ds === rS) cls += ' cal-day-start cal-day-end';
    if (ds === todayStr && !cls.includes('cal-day-start') && !cls.includes('cal-day-end')) cls += ' cal-day-today';
    return cls;
  }

  const renderPagination = () => {
    const pages = totalPages;
    const btns: React.ReactNode[] = [];
    btns.push(
      <button key="pp" className="page-btn page-nav" onClick={() => setCurrentPage(p => Math.max(1, p - 5))} disabled={currentPage <= 5} title="5페이지 이전">&laquo;</button>,
      <button key="p" className="page-btn page-nav" onClick={() => setCurrentPage(p => p - 1)} disabled={currentPage === 1} title="이전">&lsaquo;</button>,
    );
    for (let i = 1; i <= pages; i++) {
      if (i === 1 || i === pages || Math.abs(i - currentPage) <= 1)
        btns.push(<button key={i} className={`page-btn${i === currentPage ? ' active' : ''}`} onClick={() => setCurrentPage(i)}>{i}</button>);
      else if (Math.abs(i - currentPage) === 2)
        btns.push(<span key={`e${i}`} style={{ padding: '0 2px', color: 'var(--text-muted)', fontSize: 12 }}>…</span>);
    }
    btns.push(
      <button key="n" className="page-btn page-nav" onClick={() => setCurrentPage(p => p + 1)} disabled={currentPage === pages} title="다음">&rsaquo;</button>,
      <button key="nn" className="page-btn page-nav" onClick={() => setCurrentPage(p => Math.min(pages, p + 5))} disabled={currentPage + 5 > pages} title="5페이지 이후">&raquo;</button>,
    );
    return btns;
  };

  return (
    <div className="pending-page documents-page">
      {/* 페이지 헤더 */}
      <div className="page-header">
        <span className="page-header-title">처리할 문서</span>
        <span className="page-header-count">{pendingTotal}</span>
      </div>

      {/* 컨트롤 바 */}
      <div className="control-bar">
        <div className="search-wrap">
          <div className="search-field-wrap">
            <select className="search-field-select" value={searchField} onChange={(e) => { setSearchField(e.target.value as 'name' | 'author'); resetPage(); }}>
              <option value="name">문서명</option>
              <option value="author">작성자</option>
            </select>
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 6l4 4 4-4" /></svg>
          </div>
          <svg className="search-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="6.5" cy="6.5" r="4.5" /><path d="M10.5 10.5l3 3" /></svg>
          <input className="search-input" type="text" value={searchQuery} onChange={(e) => { setSearchQuery(e.target.value); resetPage(); }} onKeyDown={(e) => { if (e.key === 'Enter') resetPage(); }} />
        </div>
        <button className="btn-search" type="button" onClick={resetPage}>검색</button>

        <div className="ctrl-sep" />

        {/* 날짜 피커 */}
        <div className="date-picker-wrap" ref={datePickerRef}>
          <span className={`date-display-field${pickStart ? ' has-value' : ''}${pickStep === 1 ? ' picking' : ''}`} onClick={toggleCalPicker}>
            <svg className="cal-field-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><rect x="1.5" y="2.5" width="13" height="12" rx="2" /><path d="M5 1.5v2M11 1.5v2M1.5 6.5h13" /></svg>
            <span>{pickStart ? fmtShort(pickStart) : ''}</span>
          </span>
          <span className="date-range-sep">~</span>
          <span className={`date-display-field${pickEnd ? ' has-value' : ''}`} onClick={toggleCalPicker}>
            <svg className="cal-field-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7"><rect x="1.5" y="2.5" width="13" height="12" rx="2" /><path d="M5 1.5v2M11 1.5v2M1.5 6.5h13" /></svg>
            <span>{pickEnd ? fmtShort(pickEnd) : ''}</span>
          </span>
          <button className="btn-clear-icon" type="button" onClick={clearDates} style={{ visibility: pickStart ? 'visible' : 'hidden' }}>
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2.2"><path d="M3 3l10 10M13 3L3 13" /></svg>
          </button>
          {calOpen && (
            <div className="cal-popup" onClick={(e) => e.stopPropagation()}>
              <div className="cal-popup-header">
                <button className="cal-nav-btn" type="button" onClick={calPrevMonth}>&lsaquo;</button>
                <span className="cal-month-label">{calYear}년 {MONTHS[calMonth]}</span>
                <button className="cal-nav-btn" type="button" onClick={calNextMonth}>&rsaquo;</button>
              </div>
              <div className="cal-dow-row"><span>일</span><span>월</span><span>화</span><span>수</span><span>목</span><span>금</span><span>토</span></div>
              <div className="cal-popup-grid">
                {Array.from({ length: firstDay }, (_, i) => <div key={`e${i}`} className="cal-day cal-day-empty" />)}
                {Array.from({ length: daysInMonth }, (_, i) => {
                  const d = i + 1;
                  const ds = `${calYear}-${pad(calMonth + 1)}-${pad(d)}`;
                  return (
                    <div key={d} className={getDayClass(ds)} onClick={(e) => { e.stopPropagation(); onCalDayClick(ds); }}
                      onMouseEnter={() => { if (pickStep === 1) setHoverDate(ds); }}
                      onMouseLeave={() => { if (pickStep === 1 && hoverDate === ds) setHoverDate(null); }}>
                      {d}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 테이블 */}
      <div className="table-wrap">
        {pageDocs.length > 0 ? (
          <table className="doc-table">
            <colgroup>
              <col style={{ width: 44 }} />
              <col style={{ width: '16%' }} />
              <col />
              <col style={{ width: '13%' }} />
              <col style={{ width: '14%' }} />
              <col style={{ width: '11%' }} />
            </colgroup>
            <thead>
              <tr>
                <th className="td-check">
                  <input type="checkbox" className="row-check" checked={allChecked}
                    ref={(el) => { if (el) el.indeterminate = !allChecked && someChecked; }}
                    onChange={(e) => toggleSelectAll(e.target.checked)} onClick={(e) => e.stopPropagation()} />
                </th>
                <th>문서번호</th>
                <th>제목</th>
                <th>작성자</th>
                <th>등록일</th>
                <th>
                  <div className="th-filter-wrap">
                    <select className="th-filter" value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); resetPage(); }}>
                      <option value="">상태</option>
                      <option value="progress">결재 대기</option>
                      <option value="rejected">반려</option>
                    </select>
                    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 6l4 4 4-4" /></svg>
                  </div>
                </th>
              </tr>
            </thead>
            <tbody>
              {pageDocs.map(doc => {
                const docNum = doc.docNum ?? `${doc.date.slice(0, 4)}-DnDn-${doc.id}`;
                const badgeCls = doc.status === 'rejected' ? 'badge badge-rejected' : 'badge badge-progress';
                const badgeLabel = doc.status === 'rejected' ? '반려' : '결재 대기';
                return (
                  <tr key={doc.id} onClick={() => handleRowClick(doc)}>
                    <td className="td-check" onClick={(e) => e.stopPropagation()}>
                      <input type="checkbox" className="row-check" checked={selectedIds.has(doc.id)} onChange={(e) => toggleSelect(doc.id, e.target.checked)} />
                    </td>
                    <td className="td-docnum">{docNum}</td>
                    <td><div className="doc-title">{doc.name}</div></td>
                    <td className="td-author">{doc.author}</td>
                    <td className="td-date">{formatDate(doc.date)}</td>
                    <td style={{ textAlign: 'center' }}><span className={badgeCls}>{badgeLabel}</span></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <div className="empty-state">
            <div className="empty-state-icon">🗂️</div>
            <div className="empty-state-title">처리할 문서가 없습니다</div>
          </div>
        )}
        {pageDocs.length > 0 && <div className="pagination">{renderPagination()}</div>}
      </div>
    </div>
  );
}
