/**
 * PinSelector - GPIO Pin dropdown
 * Pin availability depends on selected port:
 *   GPIOA, GPIOB → pins 0–15
 *   GPIOC         → pins 13, 14, 15 (STM32F103VB constraint)
 *   GPIOD         → pins 0, 1
 */
export default function PinSelector({ value, onChange, port, pins = {} }) {
  const getPins = () => {
    if (pins[port]) return pins[port];
    // Fallback based on STM32F103VB datasheet constraints
    if (port === 'A' || port === 'B') return Array.from({ length: 16 }, (_, i) => i);
    if (port === 'C') return [13, 14, 15];
    if (port === 'D') return [0, 1];
    return [];
  };

  const availablePins = getPins();
  const isRegisterCRH = (pin) => pin >= 8;

  return (
    <div className="animate-fadeIn">
      <label className="label-field">Pin Number</label>
      <select
        className="select-field"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={!port}
      >
        <option value="">— Select Pin —</option>
        {availablePins.map((pin) => (
          <option key={pin} value={pin}>
            P{port}{pin} [{isRegisterCRH(pin) ? 'CRH' : 'CRL'}]
          </option>
        ))}
      </select>
      {value !== '' && port && (
        <p className="mt-1 text-xs" style={{ color: '#406070', fontFamily: 'JetBrains Mono' }}>
          Reg: GPIO{port}_{isRegisterCRH(parseInt(value)) ? 'CRH' : 'CRL'} · Bit offset: {(parseInt(value) % 8) * 4}
        </p>
      )}
      {!port && (
        <p className="mt-1 text-xs" style={{ color: '#406070' }}>Select a port first</p>
      )}
    </div>
  );
}
