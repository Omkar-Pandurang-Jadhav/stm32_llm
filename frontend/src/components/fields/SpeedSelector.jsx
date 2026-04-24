/**
 * SpeedSelector - GPIO Output Speed (MODE bits)
 * STM32F103 Reference Manual: MODEy[1:0] in CRL/CRH
 * 01 = 10MHz, 10 = 2MHz, 11 = 50MHz
 */

const SPEEDS = [
  { value: '2MHz',  label: '2 MHz',  bits: '10', desc: 'Low speed · Low EMI' },
  { value: '10MHz', label: '10 MHz', bits: '01', desc: 'Medium speed · General use' },
  { value: '50MHz', label: '50 MHz', bits: '11', desc: 'High speed · Fast signals' },
];

export default function SpeedSelector({ value, onChange, speeds = [] }) {
  const displaySpeeds = speeds.length > 0 ? speeds : SPEEDS;

  return (
    <div className="animate-fadeIn">
      <label className="label-field">Output Speed (MODE bits)</label>
      <select
        className="select-field"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">— Select Speed —</option>
        {displaySpeeds.map((spd) => (
          <option key={spd.value || spd} value={spd.value || spd}>
            {spd.label || spd}
          </option>
        ))}
      </select>
      {value && (
        <p className="mt-1 text-xs" style={{ color: '#406070', fontFamily: 'JetBrains Mono' }}>
          {getSpeedDesc(value)}
        </p>
      )}
    </div>
  );
}

function getSpeedDesc(value) {
  const found = SPEEDS.find((s) => s.value === value);
  return found ? `MODE=${found.bits} · ${found.desc}` : '';
}
