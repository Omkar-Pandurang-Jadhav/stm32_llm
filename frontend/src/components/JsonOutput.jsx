/**
 * JsonOutput - Syntax-highlighted JSON display with copy button
 */
import { useState } from 'react';

function syntaxHighlight(json) {
  if (!json) return '';
  const str = typeof json === 'string' ? json : JSON.stringify(json, null, 2);
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(
      /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
      (match) => {
        let cls = 'json-number';
        if (/^"/.test(match)) {
          cls = /:$/.test(match) ? 'json-key' : 'json-string';
        } else if (/true|false/.test(match)) {
          cls = 'json-boolean';
        } else if (/null/.test(match)) {
          cls = 'json-null';
        }
        return `<span class="${cls}">${match}</span>`;
      }
    );
}

export default function JsonOutput({ data, isLoading }) {
  const [copied, setCopied] = useState(false);
  const [activeTab, setActiveTab] = useState('config');

  const handleCopy = () => {
    const text = JSON.stringify(data, null, 2);
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  if (isLoading) {
    return (
      <div className="card-glow rounded-lg p-5">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-2 h-2 rounded-full animate-pulse" style={{ background: '#00ff9d' }} />
          <span className="section-header" style={{ color: '#00ff9d', fontSize: '0.65rem' }}>
            GENERATING CONFIG
          </span>
        </div>
        <div className="space-y-2">
          {[100, 85, 70, 90, 60].map((w, i) => (
            <div
              key={i}
              className="h-3 rounded loading-shimmer"
              style={{ width: `${w}%`, animationDelay: `${i * 0.15}s` }}
            />
          ))}
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="card-glow rounded-lg p-8 flex flex-col items-center justify-center gap-3" style={{ minHeight: 200 }}>
        <div style={{ fontSize: '2.5rem', opacity: 0.15 }}>{ '{' }</div>
        <p className="text-center text-sm" style={{ color: '#2a4050', fontFamily: 'JetBrains Mono' }}>
          Configure and generate to see output
        </p>
      </div>
    );
  }

  const tabs = Object.keys(data);

  return (
    <div className="card-glow rounded-lg overflow-hidden animate-fadeIn">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: '1px solid #00ff9d18' }}>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full" style={{ background: '#00ff9d', boxShadow: '0 0 6px #00ff9d' }} />
          <span className="section-header" style={{ color: '#00ff9d', fontSize: '0.65rem' }}>
            GENERATED CONFIG
          </span>
        </div>
        <button
          className="btn-secondary flex items-center gap-1.5"
          style={{ fontSize: '0.6rem', padding: '0.3rem 0.8rem' }}
          onClick={handleCopy}
        >
          {copied ? (
            <>
              <span style={{ color: '#00ff9d' }}>✓</span> COPIED
            </>
          ) : (
            <>
              <span>⎘</span> COPY
            </>
          )}
        </button>
      </div>

      {/* Tabs */}
      {tabs.length > 1 && (
        <div className="flex" style={{ borderBottom: '1px solid #00ff9d12' }}>
          {tabs.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className="px-4 py-2 text-xs transition-all"
              style={{
                fontFamily: 'Orbitron',
                fontSize: '0.6rem',
                letterSpacing: '0.1em',
                textTransform: 'uppercase',
                color: activeTab === tab ? '#00ff9d' : '#406070',
                borderBottom: activeTab === tab ? '2px solid #00ff9d' : '2px solid transparent',
                background: 'transparent',
                cursor: 'pointer',
              }}
            >
              {tab}
            </button>
          ))}
        </div>
      )}

      {/* JSON Content */}
      <div className="overflow-auto" style={{ maxHeight: 400 }}>
        <pre
          className="p-4 text-xs leading-relaxed"
          style={{
            fontFamily: 'JetBrains Mono',
            fontSize: '0.75rem',
            color: '#c0dde8',
            margin: 0,
          }}
          dangerouslySetInnerHTML={{
            __html: syntaxHighlight(
              tabs.length > 1 ? data[activeTab] : data
            ),
          }}
        />
      </div>
    </div>
  );
}
