const NA_REASON_LABEL = {
  SERVICE_DISABLED: '서비스 비활성화',
  ACCESS_DENIED: '권한 없음',
  SERVICE_NOT_ENABLED: '서비스 미사용',
  SERVICE_NOT_USED: '서비스 미사용',
  DATA_NOT_AVAILABLE: '데이터 없음',
  TIME_RANGE_TOO_LARGE: '조회 범위 초과',
};

export default function NASection({ reason, message }) {
  const label = NA_REASON_LABEL[reason] || reason || '수집 불가';
  return (
    <div className="na-box">
      N/A — {label}{message ? ` (${message})` : ''}
    </div>
  );
}