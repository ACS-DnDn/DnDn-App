/* ── 상태 ── */
let currentTab = 'action';
let currentPage = 1;
const PAGE_SIZE = 10;

/* ── 읽음/선택 상태 ── */
const readIds     = new Set();
let   selectedIds = new Set();

/* ── 날짜 피커 상태 ── */
let pickStart = null;
let pickEnd   = null;
let pickStep  = 0;
let hoverDate = null;
let calYear, calMonth;
let calDayEls = [];

/* ── 탭 전환 ── */
function switchTab(tab) {
  currentTab = tab;
  currentPage = 1;
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
  document.getElementById('nav-sub-action').classList.toggle('active', tab === 'action');
  document.getElementById('nav-sub-all').classList.toggle('active', tab === 'all');
  document.getElementById('typeFilter').value   = '';
  document.getElementById('statusFilter').value = '';
  document.getElementById('searchInput').value  = '';
  selectedIds.clear();
  clearDates();
  const crumb = document.getElementById('crumbTab');
  if (crumb) crumb.textContent = tab === 'action' ? '처리할 문서' : '전체 문서';
}

/* ── 필터 적용 ── */
function applyFilters() {
  currentPage = 1;
  renderTable();
}

function getFiltered() {
  const q      = document.getElementById('searchInput').value.toLowerCase().trim();
  const field  = document.getElementById('searchField').value;
  const type   = document.getElementById('typeFilter').value;
  const status = document.getElementById('statusFilter').value;

  let docs = currentTab === 'action'
    ? ALL_DOCS.filter(d => d.action !== null)
    : ALL_DOCS;

  if (q) {
    if (field === 'author') docs = docs.filter(d => d.author.toLowerCase().includes(q));
    else                    docs = docs.filter(d => d.name.toLowerCase().includes(q));
  }
  if (type)   docs = docs.filter(d => d.type === type);
  if (status) docs = docs.filter(d => d.status === status);
  if (pickStep === 2) {
    if (pickStart) docs = docs.filter(d => d.date >= pickStart);
    if (pickEnd)   docs = docs.filter(d => d.date <= pickEnd + ' 23:59');
  }

  return [...docs].sort((a, b) => b.date.localeCompare(a.date));
}

/* ── 테이블 렌더 ── */
function renderTable() {
  const docs     = getFiltered();
  const start    = (currentPage - 1) * PAGE_SIZE;
  const pageDocs = docs.slice(start, start + PAGE_SIZE);

  document.getElementById('actionCount').textContent = ALL_DOCS.filter(d => d.action !== null).length;
  document.getElementById('allCount').textContent    = ALL_DOCS.filter(d => !readIds.has(d.id)).length;

  const tbody = document.getElementById('docTbody');
  tbody.innerHTML = '';
  document.getElementById('docTable').style.display = 'table';

  if (pageDocs.length === 0) {
    document.getElementById('emptyState').style.display = 'flex';
    document.getElementById('pagination').innerHTML = '';
    return;
  }
  document.getElementById('emptyState').style.display = 'none';

  const statusLabels = { progress: '진행 중', done: '완료', rejected: '반려', failed: '실패' };
  const typeLabels   = { '계획서': '작업 계획서', '주간보고서': '주간 보고서', '이벤트보고서': '이벤트 보고서' };

  pageDocs.forEach(doc => {
    const tr = document.createElement('tr');
    if (readIds.has(doc.id)) tr.classList.add('doc-read');

    const statusLabel = statusLabels[doc.status] || doc.status;
    const typeLabel   = typeLabels[doc.type] || doc.type;
    const docNum      = `${doc.date.slice(0, 4)}-DnDn-${String(doc.id).padStart(4, '0')}`;
    const checked     = selectedIds.has(doc.id) ? 'checked' : '';

    tr.innerHTML = `
      <td class="td-check" onclick="event.stopPropagation()"><input type="checkbox" class="row-check" ${checked} onchange="toggleSelect(${doc.id},this.checked)"></td>
      <td class="td-docnum">${docNum}</td>
      <td><div class="doc-title">${doc.name}</div></td>
      <td class="td-type">${typeLabel}</td>
      <td class="td-author">${doc.author}</td>
      <td class="td-date">${formatDate(doc.date)}</td>
      <td>${statusLabel}</td>
    `;
    tbody.appendChild(tr);
  });

  const chkAll = document.getElementById('chkAll');
  const allChecked  = pageDocs.length > 0 && pageDocs.every(d => selectedIds.has(d.id));
  const someChecked = pageDocs.some(d => selectedIds.has(d.id));
  chkAll.checked       = allChecked;
  chkAll.indeterminate = !allChecked && someChecked;

  renderPagination(docs.length);
}

function formatDate(d) {
  const [date, time] = d.split(' ');
  const [y, m, day] = date.split('-');
  return `${y}.${m}.${day} ${time || ''}`;
}

/* ── 페이지네이션 ── */
function renderPagination(total) {
  let pages = Math.ceil(total / PAGE_SIZE);
  if (pages < 1) pages = 1;

  const pag = document.getElementById('pagination');
  let html = '';
  html += `<button class="page-btn page-nav" onclick="goPage(${currentPage-5})" ${currentPage<=5?'disabled':''} title="5페이지 이전">«</button>`;
  html += `<button class="page-btn page-nav" onclick="goPage(${currentPage-1})" ${currentPage===1?'disabled':''} title="이전">‹</button>`;
  for (let i = 1; i <= pages; i++) {
    if (i === 1 || i === pages || Math.abs(i - currentPage) <= 1) {
      html += `<button class="page-btn ${i===currentPage?'active':''}" onclick="goPage(${i})">${i}</button>`;
    } else if (Math.abs(i - currentPage) === 2) {
      html += `<span style="padding:0 2px;color:var(--text-muted);font-size:12px;">…</span>`;
    }
  }
  html += `<button class="page-btn page-nav" onclick="goPage(${currentPage+1})" ${currentPage===pages?'disabled':''} title="다음">›</button>`;
  html += `<button class="page-btn page-nav" onclick="goPage(${currentPage+5})" ${currentPage+5>pages?'disabled':''} title="5페이지 이후">»</button>`;
  pag.innerHTML = html;
}

function goPage(p) {
  const total = getFiltered().length;
  const pages = Math.ceil(total / PAGE_SIZE);
  if (p < 1 || p > pages) return;
  currentPage = p;
  renderTable();
}

/* ── 체크박스 선택 ── */
function toggleSelect(id, checked) {
  if (checked) selectedIds.add(id);
  else         selectedIds.delete(id);
  const pageDocs = getFiltered().slice((currentPage-1)*PAGE_SIZE, currentPage*PAGE_SIZE);
  const chkAll = document.getElementById('chkAll');
  const allChecked  = pageDocs.every(d => selectedIds.has(d.id));
  const someChecked = pageDocs.some(d => selectedIds.has(d.id));
  chkAll.checked       = allChecked;
  chkAll.indeterminate = !allChecked && someChecked;
}

function toggleSelectAll(checked) {
  const pageDocs = getFiltered().slice((currentPage-1)*PAGE_SIZE, currentPage*PAGE_SIZE);
  pageDocs.forEach(d => checked ? selectedIds.add(d.id) : selectedIds.delete(d.id));
  renderTable();
}

/* ── 읽음 처리 ── */
function markRead() {
  selectedIds.forEach(id => readIds.add(id));
  selectedIds.clear();
  renderTable();
}

function markAllRead() {
  getFiltered().forEach(d => readIds.add(d.id));
  selectedIds.clear();
  renderTable();
}

/* ── 날짜 초기화 ── */
function clearDates() {
  pickStart = pickEnd = null;
  pickStep  = 0;
  hoverDate = null;
  updateDateDisplay();
  applyFilters();
}

/* ── 달력 피커 ── */
function initCalPicker() {
  const t  = new Date();
  calYear  = t.getFullYear();
  calMonth = t.getMonth();
}

function toggleCalPicker(e) {
  e && e.stopPropagation();
  const popup = document.getElementById('calPopup');
  if (popup.style.display === 'none') {
    if (!calYear) initCalPicker();
    renderCalPickerGrid();
    popup.style.display = 'block';
  } else {
    popup.style.display = 'none';
    hoverDate = null;
  }
}

function calPrevMonth() {
  calMonth--;
  if (calMonth < 0) { calMonth = 11; calYear--; }
  renderCalPickerGrid();
}

function calNextMonth() {
  calMonth++;
  if (calMonth > 11) { calMonth = 0; calYear++; }
  renderCalPickerGrid();
}

function renderCalPickerGrid() {
  const MONTHS = ['1월','2월','3월','4월','5월','6월','7월','8월','9월','10월','11월','12월'];
  document.getElementById('calMonthLabel').textContent = `${calYear}년 ${MONTHS[calMonth]}`;

  const grid = document.getElementById('calPopupGrid');
  grid.innerHTML = '';
  calDayEls = [];

  const today    = new Date();
  const todayStr = `${today.getFullYear()}-${pad(today.getMonth()+1)}-${pad(today.getDate())}`;
  const firstDay    = new Date(calYear, calMonth, 1).getDay();
  const daysInMonth = new Date(calYear, calMonth + 1, 0).getDate();

  for (let i = 0; i < firstDay; i++) {
    const el = document.createElement('div');
    el.className = 'cal-day cal-day-empty';
    grid.appendChild(el);
  }

  for (let d = 1; d <= daysInMonth; d++) {
    const ds = `${calYear}-${pad(calMonth+1)}-${pad(d)}`;
    const el = document.createElement('div');
    el.textContent  = d;
    if (ds === todayStr) el.dataset.today = '1';
    el.onclick      = (e) => { e.stopPropagation(); onCalDayClick(ds); };
    el.onmouseenter = () => { if (pickStep === 1) { hoverDate = ds;   updateCalClasses(); } };
    el.onmouseleave = () => { if (pickStep === 1 && hoverDate === ds) { hoverDate = null; updateCalClasses(); } };
    calDayEls.push({ el, ds });
    grid.appendChild(el);
  }

  updateCalClasses();
}

function updateCalClasses() {
  const rE = pickStep === 1 && hoverDate ? hoverDate : pickEnd;
  const rS = pickStart;

  calDayEls.forEach(({ el, ds }) => {
    let cls = 'cal-day';
    if (rS && rE) {
      const lo = rS < rE ? rS : rE;
      const hi = rS < rE ? rE : rS;
      if      (ds === lo && ds === hi) cls += ' cal-day-start cal-day-end';
      else if (ds === lo)              cls += ' cal-day-start';
      else if (ds === hi)              cls += ' cal-day-end';
      else if (ds > lo && ds < hi)     cls += ' cal-day-range';
    } else if (rS && ds === rS) {
      cls += ' cal-day-start cal-day-end';
    }
    if (el.dataset.today === '1' && !cls.includes('cal-day-start') && !cls.includes('cal-day-end')) {
      cls += ' cal-day-today';
    }
    el.className = cls;
  });
}

function pad(n) { return String(n).padStart(2, '0'); }

function onCalDayClick(ds) {
  if (pickStep === 0 || pickStep === 2) {
    pickStart = ds;
    pickEnd   = null;
    pickStep  = 1;
    updateCalClasses();
  } else {
    if (ds === pickStart) {
      pickEnd = ds;
    } else if (ds < pickStart) {
      pickEnd   = pickStart;
      pickStart = ds;
    } else {
      pickEnd = ds;
    }
    pickStep  = 2;
    hoverDate = null;
    updateCalClasses();
    document.getElementById('calPopup').style.display = 'none';
    applyFilters();
  }
  updateDateDisplay();
}

function updateDateDisplay() {
  const fromEl   = document.getElementById('dateFromDisplay');
  const toEl     = document.getElementById('dateToDisplay');
  const fromText = document.getElementById('dateFromText');
  const toText   = document.getElementById('dateToText');
  const clearEl  = document.getElementById('btnDateClear');

  if (pickStart) {
    fromText.textContent = fmtShort(pickStart);
    fromEl.classList.add('has-value');
    fromEl.classList.toggle('picking', pickStep === 1);
  } else {
    fromText.textContent = '';
    fromEl.classList.remove('has-value', 'picking');
  }

  if (pickEnd) {
    toText.textContent = fmtShort(pickEnd);
    toEl.classList.add('has-value');
    toEl.classList.remove('picking');
  } else {
    toText.textContent = '';
    toEl.classList.remove('has-value', 'picking');
  }

  clearEl.style.visibility = pickStart ? 'visible' : 'hidden';
}

function fmtShort(ds) {
  const [y, m, d] = ds.split('-');
  return `${y.slice(2)}.${m}.${d}`;
}

/* ── 초기화 ── */
initCalPicker();
renderTable();

document.addEventListener('click', function(e) {
  const wrap  = document.getElementById('datePickerWrap');
  const popup = document.getElementById('calPopup');
  if (popup.style.display !== 'none' && !wrap.contains(e.target)) {
    popup.style.display = 'none';
    hoverDate = null;
  }
});
