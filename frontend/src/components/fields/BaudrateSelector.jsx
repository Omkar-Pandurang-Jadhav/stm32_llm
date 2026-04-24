/**
 * BaudrateSelector - USART Baudrate selection
 * BRR register computed by backend: USARTDIV = PCLK / (16 × Baudrate)
 * BRR = mantissa << 4 | fraction
 */

const BAUDRATES = [
  { value: 9600,   label: '9,600 bps',   desc: 'Low speed · Serial terminals' },
  { value: 19200,  label: '19,200 bps',  desc: 'Standard · Modems, sensors' },
  { value: 38400,  label: '38,400 bps',  desc: 'Medium · Bluetooth classic' },
  { value: 57600,  label: '57,600 bps',  desc: 'High · GPS modules' },
  { value: 115200, label: '115,200 bps', desc: 'Fast · Debug, data streaming' },
];

export default function BaudrateSelector({ value, onChange, baudrates = [] }) {
  const displayBaudrates = baudrates.length > 0 ? baudrates : BAUDRATES;

  return (
    <div className="animate-fadeIn">
      <label className="label-field">Baudrate (BRR)</label>
      <select
        className="select-field"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">— Select Baudrate —</option>
        {displayBaudrates.map((br) => (
          <option key={br.value || br} value={br.value || br}>
            {br.label || br}
          </option>
        ))}
      </select>
      {value && (
        <div className="mt-1 p-2 rounded" style={{ background: '#0a1520', border: '1px solid #00ff9d11' }}>
          <p className="text-xs" style={{ color: '#406070', fontFamily: 'JetBrains Mono' }}>
            {getDesc(value)} · BRR computed by backend
          </p>
          <p className="text-xs mt-0.5" style={{ color: '#00ff9d44', fontFamily: 'JetBrains Mono' }}>
            USARTDIV = PCLK₁ / (16 × {Number(value).toLocaleString()})
          </p>
        </div>
      )}
    </div>
  );
}

function getDesc(value) {
  const found = BAUDRATES.find((b) => String(b.value) === String(value));
  return found ? found.desc : '';
}
