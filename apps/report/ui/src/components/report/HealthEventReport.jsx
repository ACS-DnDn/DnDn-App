// HealthEventReport.jsx
// AWS Health 이벤트 보고서 - 이벤트보고서-클린-health.html 양식 기반

export default function HealthEventReport({ data }) {
  if (!data) return null;

  const ov = data.overview || {};
  const eg = data.이벤트_개요 || {};
  const detail = data.이벤트_상세 || {};
  const timeline = data.타임라인 || [];
  const actions = data.권장_조치 || [];

  return (
    <div className="doc">
      {/* ── 헤더 ── */}
      <div className="doc-header">
        <div className="doc-header-top">
          <div className="doc-logo-placeholder">[로고] DnDn</div>
          <div className="doc-header-meta">
            문서번호: {data.문서번호 || '—'}<br />
            작성일: {data.작성일 || '—'}
          </div>
        </div>
        <div className="doc-header-title">{data.이벤트_제목 || '—'}</div>
      </div>

      {/* ── Overview ── */}
      <div className="section">
        <div className="section-title">Overview</div>
        <table className="tbl-info">
          <tbody>
            <tr>
              <th>이벤트 내용</th>
              <td colSpan={3}>{ov.이벤트_한줄_설명 || '—'}</td>
            </tr>
            <tr>
              <th>대상 리소스</th>
              <td><code>{ov.대상_리소스 || '—'}</code> ({ov.리전 || '—'})</td>
              <th>AWS 계정</th>
              <td>{ov.AWS_계정_ID || '—'}</td>
            </tr>
            <tr>
              <th>이벤트 카테고리</th>
              <td><strong>{ov.이벤트_카테고리 || '—'}</strong></td>
              <th>감지 일시</th>
              <td>{ov.감지_일시 || '—'} (KST)</td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* ── 1. 이벤트 개요 ── */}
      <div className="section">
        <div className="section-title">1. 이벤트 개요</div>
        <table className="tbl">
          <tbody>
            <tr>
              <th className="th-label">감지 출처</th>
              <td>{eg.감지_출처 || '—'}</td>
            </tr>
            <tr>
              <th className="th-label">이벤트 ARN</th>
              <td style={{ fontFamily: 'SFMono-Regular, Consolas, monospace', fontSize: '11.5px' }}>
                {eg.이벤트_ARN || '—'}
              </td>
            </tr>
            <tr>
              <th className="th-label">이벤트 상태</th>
              <td>{eg.이벤트_상태 || '—'}</td>
            </tr>
            <tr>
              <th className="th-label">감지 일시</th>
              <td>{eg.감지_일시 || '—'} (KST)</td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* ── 2. 이벤트 타임라인 ── */}
      <div className="section">
        <div className="section-title">2. 이벤트 타임라인</div>
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: '100px' }}>시각 (KST)</th>
              <th style={{ width: '120px' }}>구분</th>
              <th>내용</th>
            </tr>
          </thead>
          <tbody>
            {timeline.length > 0 ? timeline.map((row, i) => (
              <tr key={i}>
                <td className="td-time">{row.시각 || '—'}</td>
                <td className="td-type">{row.구분 || '—'}</td>
                <td>{row.내용 || '—'}</td>
              </tr>
            )) : (
              <tr>
                <td className="td-time">—</td>
                <td className="td-type">AWS Health</td>
                <td>이벤트 발생</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* ── 3. AWS Health 이벤트 상세 ── */}
      <div className="section">
        <div className="section-title">3. AWS Health 이벤트 상세</div>
        <table className="tbl">
          <tbody>
            <tr>
              <th className="th-label">이벤트 유형 코드</th>
              <td><code>{detail.이벤트_유형_코드 || '—'}</code></td>
            </tr>
            <tr>
              <th className="th-label">이벤트 카테고리</th>
              <td>{detail.이벤트_카테고리 || '—'}</td>
            </tr>
            <tr>
              <th className="th-label">이벤트 상태</th>
              <td>{detail.이벤트_상태 || '—'}</td>
            </tr>
            <tr>
              <th className="th-label">이벤트 상세 설명</th>
              <td style={{ textAlign: 'left', whiteSpace: 'pre-wrap', lineHeight: '1.7' }}>
                {detail.이벤트_상세_설명 || '—'}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* ── 4. 권장 조치 ── */}
      <div className="section">
        <div className="section-title">4. 권장 조치</div>
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: '100px' }}>구분</th>
              <th style={{ width: '44px' }}>순서</th>
              <th>조치 내용</th>
            </tr>
          </thead>
          <tbody>
            {actions.map((a, i) => (
              <tr key={i}>
                <td className="td-step">{a.조치_구분 || '—'}</td>
                <td className="td-step">{a.순서 || `${i + 1}`}</td>
                <td>{a.조치_내용 || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ── 문서 푸터 ── */}
      <div className="doc-footer">
        <span>{data.문서번호 || '—'} &nbsp;/&nbsp; {data.작성일 || '—'}</span>
      </div>
    </div>
  );
}
