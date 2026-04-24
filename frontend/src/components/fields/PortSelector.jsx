/**
 * PortSelector - GPIO Port dropdown (A, B, C, D)
 * STM32F103VB: GPIOA-GPIOD mapped at 0x40010800 - 0x40011400
 */
export default function PortSelector({ value, onChange, ports = [] }) {
  const displayPorts = ports.length > 0 ? ports : ['A', 'B', 'C', 'D'];

  return (
    <div className="animate-fadeIn">
      <label className="label-field">GPIO Port</label>
      <select
        className="select-field"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">— Select Port —</option>
        {displayPorts.map((port) => (
          <option key={port} value={port}>
            GPIO{port}
          </option>
        ))}
      </select>
      {value && (
        <p className="mt-1 text-xs" style={{ color: '#406070', fontFamily: 'JetBrains Mono' }}>
          Base: 0x{getPortBase(value)}
        </p>
      )}
    </div>
  );
}

function getPortBase(port) {
  const bases = { A: '40010800', B: '40010C00', C: '40011000', D: '40011400' };
  return bases[port] || '????????';
}
