/**
 * STM32F103VB Peripheral Configurator
 * Main application shell
 */
import { useState, useEffect, useCallback } from 'react';
import IntentSelector from './components/IntentSelector.jsx';
import DynamicForm from './components/DynamicForm.jsx';
import JsonOutput from './components/JsonOutput.jsx';
import LearningPanel from './components/LearningPanel.jsx';
import { fetchHardware, generateJson, checkHealth } from './services/api.js';

// ── Validation rules per intent ──────────────────────────────────────────────
function isFormComplete(intent, entities) {
  if (!intent) return false;
  switch (intent) {
    case 'GPIO_OUTPUT':
      return !!(entities.port && entities.pin !== '' && entities.pin !== undefined && entities.mode && entities.speed);
    case 'GPIO_INPUT':
      return !!(entities.port && entities.pin !== '' && entities.pin !== undefined && entities.mode);
    case 'GPIO_TOGGLE':
    case 'GPIO_READ':
      return !!(entities.port && entities.pin !== '' && entities.pin !== undefined);
    case 'UART_INIT':
      return !!(entities.usart && entities.baudrate);
    case 'UART_RECEIVE':
      return !!(entities.usart);
    case 'TIMER_DELAY':
      return !!(entities.timer && entities.delay && parseInt(entities.delay) > 0);
    case 'RCC_ENABLE':
      return !!(entities.peripheral);
    default:
      return false;
  }
}

// ── Status Indicator ─────────────────────────────────────────────────────────
function ApiStatus({ status }) {
  const configs = {
    online:      { color: '#00ff9d', label: 'BACKEND ONLINE',  pulse: true },
    offline:     { color: '#ff003c', label: 'BACKEND OFFLINE', pulse: false },
    checking:    { color: '#ffcc00', label: 'CHECKING...',      pulse: true },
  };
  const cfg = configs[status] || configs.checking;
  return (
    <div className="flex items-center gap-1.5">
      <span
        className="w-1.5 h-1.5 rounded-full"
        style={{
          background: cfg.color,
          boxShadow: `0 0 6px ${cfg.color}`,
          animation: cfg.pulse ? 'pulse 2s infinite' : 'none',
        }}
      />
      <span style={{ fontFamily: 'Orbitron', fontSize: '0.55rem', letterSpacing: '0.1em', color: cfg.color }}>
        {cfg.label}
      </span>
    </div>
  );
}

// ── Spinner ──────────────────────────────────────────────────────────────────
function Spinner() {
  return (
    <div className="inline-block w-3.5 h-3.5 border-2 rounded-full"
      style={{
        borderColor: '#00ff9d44',
        borderTopColor: '#00ff9d',
        animation: 'spin 0.7s linear infinite',
      }}
    />
  );
}

// ── Toast ────────────────────────────────────────────────────────────────────
function Toast({ message, type, onClose }) {
  useEffect(() => {
    const t = setTimeout(onClose, 4000);
    return () => clearTimeout(t);
  }, [onClose]);

  const colors = {
    error:   { bg: '#ff003c18', border: '#ff003c44', text: '#ff003c' },
    success: { bg: '#00ff9d18', border: '#00ff9d44', text: '#00ff9d' },
  };
  const c = colors[type] || colors.error;

  return (
    <div
      className="fixed bottom-6 right-6 px-4 py-3 rounded-lg text-sm animate-fadeIn z-50 flex items-center gap-3"
      style={{ background: c.bg, border: `1px solid ${c.border}`, color: c.text, fontFamily: 'JetBrains Mono', fontSize: '0.75rem', maxWidth: 360 }}
    >
      <span>{type === 'error' ? '✕' : '✓'}</span>
      <span>{message}</span>
      <button onClick={onClose} style={{ marginLeft: 'auto', opacity: 0.6 }}>×</button>
    </div>
  );
}

// ── Main App ─────────────────────────────────────────────────────────────────
export default function App() {
  const [intent, setIntent] = useState('');
  const [entities, setEntities] = useState({});
  const [hardware, setHardware] = useState({});
  const [output, setOutput] = useState(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [apiStatus, setApiStatus] = useState('checking');
  const [toast, setToast] = useState(null);

  // Check API health + fetch hardware constraints on mount
  useEffect(() => {
    async function init() {
      setApiStatus('checking');
      const healthy = await checkHealth();
      setApiStatus(healthy ? 'online' : 'offline');
      if (healthy) {
        try {
          const hw = await fetchHardware();
          setHardware(hw);
        } catch {
          // Use fallback — form still works with built-in defaults
        }
      }
    }
    init();
    const interval = setInterval(async () => {
      const healthy = await checkHealth();
      setApiStatus(healthy ? 'online' : 'offline');
    }, 15000);
    return () => clearInterval(interval);
  }, []);

  const handleIntentChange = (newIntent) => {
    setIntent(newIntent);
    setEntities({});
    setOutput(null);
  };

  const handleGenerate = useCallback(async () => {
    if (!isFormComplete(intent, entities)) return;
    setIsGenerating(true);
    setOutput(null);
    try {
      const result = await generateJson(intent, entities);
      setOutput(result);
    } catch (err) {
      setToast({ message: err.message || 'Failed to generate config', type: 'error' });
    } finally {
      setIsGenerating(false);
    }
  }, [intent, entities]);

  const handleReset = () => {
    setIntent('');
    setEntities({});
    setOutput(null);
    setToast(null);
  };

  const ready = isFormComplete(intent, entities);

  return (
    <div className="min-h-screen noise-bg" style={{ background: '#020408' }}>

      {/* ── Scanline decorative bar ── */}
      <div className="fixed top-0 left-0 right-0 h-px z-50" style={{ background: 'linear-gradient(90deg, transparent, #00ff9d88, transparent)' }} />

      {/* ── Header ── */}
      <header className="sticky top-0 z-40 px-6 py-3 flex items-center justify-between"
        style={{ background: '#020408e8', borderBottom: '1px solid #00ff9d18', backdropFilter: 'blur(12px)' }}>
        <div className="flex items-center gap-4">
          <div className="flex gap-1.5">
            <div className="w-2 h-2 rounded-full" style={{ background: '#ff003c' }} />
            <div className="w-2 h-2 rounded-full" style={{ background: '#ffcc00' }} />
            <div className="w-2 h-2 rounded-full" style={{ background: '#00ff9d' }} />
          </div>
          <div>
            <h1 className="cursor-blink" style={{ fontFamily: 'Orbitron', fontSize: '0.95rem', fontWeight: 700, color: '#00ff9d', letterSpacing: '0.1em' }}>
              STM32F103VB
            </h1>
            <p style={{ fontFamily: 'JetBrains Mono', fontSize: '0.6rem', color: '#406070', marginTop: '0.1rem' }}>
              Peripheral Configuration System · ARM Cortex-M3 · 72 MHz
            </p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <ApiStatus status={apiStatus} />
          <button className="btn-secondary" onClick={handleReset} style={{ fontSize: '0.55rem', padding: '0.3rem 0.8rem' }}>
            ↺ RESET
          </button>
        </div>
      </header>

      {/* ── Main Layout ── */}
      <main className="max-w-7xl mx-auto px-4 py-6 grid gap-5" style={{ gridTemplateColumns: '1fr 1fr 320px' }}>

        {/* ── Left Column: Config Panel ── */}
        <div className="space-y-4">

          {/* Intent selector */}
          <div className="card-glow rounded-lg p-5">
            <div className="flex items-center gap-2 mb-4" style={{ borderBottom: '1px solid #00ff9d12', paddingBottom: '0.75rem' }}>
              <div className="w-2 h-2 rounded-full" style={{ background: '#00ff9d', boxShadow: '0 0 6px #00ff9d' }} />
              <span className="section-header" style={{ color: '#00ff9d', fontSize: '0.65rem' }}>
                STEP 1 — SELECT INTENT
              </span>
            </div>
            <IntentSelector value={intent} onChange={handleIntentChange} intents={hardware.intents} />
          </div>

          {/* Dynamic form */}
          <div className="card-glow rounded-lg p-5">
            <div className="flex items-center gap-2 mb-4" style={{ borderBottom: '1px solid #00ff9d12', paddingBottom: '0.75rem' }}>
              <div
                className="w-2 h-2 rounded-full"
                style={{ background: intent ? '#00ff9d' : '#1a3a54', boxShadow: intent ? '0 0 6px #00ff9d' : 'none', transition: 'all 0.3s' }}
              />
              <span className="section-header" style={{ color: intent ? '#00ff9d' : '#2a4050', fontSize: '0.65rem', transition: 'color 0.3s' }}>
                STEP 2 — CONFIGURE PARAMETERS
              </span>
            </div>
            <DynamicForm
              intent={intent}
              entities={entities}
              onChange={setEntities}
              hardware={hardware}
            />
          </div>

          {/* Generate button */}
          <button
            className="btn-primary w-full flex items-center justify-center gap-2 py-3"
            onClick={handleGenerate}
            disabled={!ready || isGenerating}
            style={{ fontSize: '0.7rem', letterSpacing: '0.15em' }}
          >
            {isGenerating ? (
              <>
                <Spinner /> GENERATING...
              </>
            ) : (
              <>
                <span style={{ fontSize: '1rem' }}>⚡</span>
                GENERATE CONFIG JSON
              </>
            )}
          </button>

          {!ready && intent && (
            <p className="text-center text-xs" style={{ color: '#2a4050', fontFamily: 'JetBrains Mono' }}>
              Complete all required fields to enable generation
            </p>
          )}
        </div>

        {/* ── Center Column: Output ── */}
        <div className="space-y-4">

          {/* Current config summary */}
          {intent && (
            <div
              className="rounded-lg p-4 animate-fadeIn"
              style={{ background: '#00ff9d08', border: '1px solid #00ff9d18' }}
            >
              <p className="section-header mb-2" style={{ color: '#00ff9d66', fontSize: '0.6rem' }}>
                CURRENT CONFIGURATION
              </p>
              <div className="flex flex-wrap gap-2">
                {intent && (
                  <Tag label="INTENT" value={intent} color="#00ff9d" />
                )}
                {Object.entries(entities).filter(([, v]) => v !== '' && v !== undefined && v !== null).map(([k, v]) => (
                  <Tag key={k} label={k.toUpperCase()} value={String(v)} color="#00e5ff" />
                ))}
              </div>
            </div>
          )}

          {/* JSON output */}
          <div>
            <div className="mb-2 flex items-center gap-2">
              <div
                className="w-2 h-2 rounded-full"
                style={{ background: output ? '#00ff9d' : '#1a3a54', boxShadow: output ? '0 0 6px #00ff9d' : 'none', transition: 'all 0.3s' }}
              />
              <span className="section-header" style={{ color: output ? '#00ff9d' : '#2a4050', fontSize: '0.65rem', transition: 'color 0.3s' }}>
                STEP 3 — INSPECT OUTPUT
              </span>
            </div>
            <JsonOutput data={output} isLoading={isGenerating} />
          </div>

          {/* Register quick-reference */}
          {intent && (
            <RegisterQuickRef intent={intent} entities={entities} />
          )}
        </div>

        {/* ── Right Column: Learning Panel ── */}
        <div>
          <LearningPanel intent={intent} entities={entities} />
        </div>
      </main>

      {/* ── Footer ── */}
      <footer className="text-center py-6" style={{ borderTop: '1px solid #00ff9d08' }}>
        <p style={{ fontFamily: 'JetBrains Mono', fontSize: '0.6rem', color: '#1a3a54' }}>
          STM32F103VB · ARM Cortex-M3 · RM0008 Reference Manual · Datasheet Rev. Sep 2023
        </p>
      </footer>

      {/* ── Toast ── */}
      {toast && (
        <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />
      )}

      {/* ── Inline spinner keyframe ── */}
      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}

// ── Tag chip ─────────────────────────────────────────────────────────────────
function Tag({ label, value, color }) {
  return (
    <div
      className="flex items-center gap-1 px-2 py-0.5 rounded"
      style={{ background: `${color}12`, border: `1px solid ${color}33` }}
    >
      <span style={{ fontFamily: 'Orbitron', fontSize: '0.5rem', color: `${color}88`, letterSpacing: '0.08em' }}>
        {label}:
      </span>
      <span style={{ fontFamily: 'JetBrains Mono', fontSize: '0.65rem', color }}>
        {value}
      </span>
    </div>
  );
}

// ── Register Quick Reference ──────────────────────────────────────────────────
function RegisterQuickRef({ intent, entities }) {
  const rows = getRegisterRows(intent, entities);
  if (!rows.length) return null;

  return (
    <div className="card-glow rounded-lg p-4 animate-fadeIn">
      <p className="section-header mb-3" style={{ color: '#00ff9d66', fontSize: '0.6rem' }}>
        ◈ REGISTER QUICK REFERENCE
      </p>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            {['Register', 'Offset', 'Purpose'].map((h) => (
              <th key={h} style={{ fontFamily: 'Orbitron', fontSize: '0.55rem', color: '#2a4050', letterSpacing: '0.08em', textAlign: 'left', paddingBottom: '0.5rem', borderBottom: '1px solid #00ff9d11' }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {[row.reg, row.offset, row.purpose].map((cell, j) => (
                <td key={j} style={{ fontFamily: 'JetBrains Mono', fontSize: '0.65rem', color: j === 0 ? '#00e5ff' : '#406070', padding: '0.3rem 0', borderBottom: '1px solid #00ff9d08' }}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function getRegisterRows(intent, entities) {
  if (intent.startsWith('GPIO')) {
    const port = entities.port || 'x';
    return [
      { reg: `GPIO${port}_CRL`,  offset: '+0x00', purpose: 'Pin config 0–7' },
      { reg: `GPIO${port}_CRH`,  offset: '+0x04', purpose: 'Pin config 8–15' },
      { reg: `GPIO${port}_IDR`,  offset: '+0x08', purpose: 'Input data (RO)' },
      { reg: `GPIO${port}_ODR`,  offset: '+0x0C', purpose: 'Output data' },
      { reg: `GPIO${port}_BSRR`, offset: '+0x10', purpose: 'Atomic set/reset' },
    ];
  }
  if (intent.startsWith('UART')) {
    const u = entities.usart || 'USARTx';
    return [
      { reg: `${u}_SR`,  offset: '+0x00', purpose: 'Status (TXE, RXNE)' },
      { reg: `${u}_DR`,  offset: '+0x04', purpose: 'Data register RW' },
      { reg: `${u}_BRR`, offset: '+0x08', purpose: 'Baud rate register' },
      { reg: `${u}_CR1`, offset: '+0x0C', purpose: 'Control (UE,TE,RE)' },
    ];
  }
  if (intent === 'TIMER_DELAY') {
    const t = entities.timer || 'TIMx';
    return [
      { reg: `${t}_CR1`, offset: '+0x00', purpose: 'Control (CEN)' },
      { reg: `${t}_SR`,  offset: '+0x10', purpose: 'Status (UIF)' },
      { reg: `${t}_CNT`, offset: '+0x24', purpose: 'Counter value' },
      { reg: `${t}_PSC`, offset: '+0x28', purpose: 'Prescaler' },
      { reg: `${t}_ARR`, offset: '+0x2C', purpose: 'Auto-reload' },
    ];
  }
  if (intent === 'RCC_ENABLE') {
    return [
      { reg: 'RCC_APB2ENR', offset: '+0x18', purpose: 'GPIO/USART1/TIM1' },
      { reg: 'RCC_APB1ENR', offset: '+0x1C', purpose: 'TIM2-4/USART2-3' },
      { reg: 'RCC_AHBENR',  offset: '+0x14', purpose: 'DMA, FLITF, SRAM' },
    ];
  }
  return [];
}
