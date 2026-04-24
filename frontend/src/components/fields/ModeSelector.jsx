/**
 * ModeSelector - GPIO Mode/CNF configuration
 * Based on STM32F103 Reference Manual: GPIOx_CRL / GPIOx_CRH
 * MODEy[1:0] + CNFy[1:0] bits
 */

const OUTPUT_MODES = [
  {
    value: 'output_push_pull',
    label: 'Output Push-Pull',
    desc: 'CNF=00 · Active drive to VDD/GND',
  },
  {
    value: 'output_open_drain',
    label: 'Output Open-Drain',
    desc: 'CNF=01 · Requires pull-up resistor',
  },
];

const INPUT_MODES = [
  {
    value: 'input_floating',
    label: 'Input Floating',
    desc: 'CNF=01 · High-Z, no internal resistor',
  },
  {
    value: 'input_pull_up',
    label: 'Input Pull-Up',
    desc: 'CNF=10 + ODR=1 · Internal 40kΩ pull-up',
  },
  {
    value: 'input_pull_down',
    label: 'Input Pull-Down',
    desc: 'CNF=10 + ODR=0 · Internal pull-down',
  },
];

export default function ModeSelector({ value, onChange, type = 'output', modes = [] }) {
  const options = modes.length > 0
    ? modes
    : type === 'output'
    ? OUTPUT_MODES
    : INPUT_MODES;

  return (
    <div className="animate-fadeIn">
      <label className="label-field">Pin Mode (CNF bits)</label>
      <select
        className="select-field"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">— Select Mode —</option>
        {options.map((mode) => (
          <option key={mode.value || mode} value={mode.value || mode}>
            {mode.label || mode}
          </option>
        ))}
      </select>
      {value && (
        <p className="mt-1 text-xs" style={{ color: '#406070', fontFamily: 'JetBrains Mono' }}>
          {getModeDesc(value, [...OUTPUT_MODES, ...INPUT_MODES])}
        </p>
      )}
    </div>
  );
}

function getModeDesc(value, allModes) {
  const found = allModes.find((m) => m.value === value);
  return found ? found.desc : '';
}
