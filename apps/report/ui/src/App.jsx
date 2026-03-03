import { useState } from 'react';
import EventReport from './components/report/EventReport';
import eventSample from './data/event.sample.json';
import './index.css';

const TABS = [
  { key: 'event', label: '이벤트 보고서' },
  { key: 'weekly', label: '주간 보고서 (준비 중)' },
];

export default function App() {
  const [tab, setTab] = useState('event');

  return (
    <>
      <div className="dev-tabs">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={`dev-tab ${tab === t.key ? 'active' : ''}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'event' && <EventReport canonical={eventSample} />}
      {tab === 'weekly' && <div style={{ padding: '40px', textAlign: 'center', color: '#888' }}>주간 보고서 컴포넌트 개발 중</div>}
    </>
  );
}