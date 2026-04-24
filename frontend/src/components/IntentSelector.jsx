/**
 * IntentSelector - Main intent dropdown
 * Groups intents by peripheral category
 */

const INTENT_GROUPS = [
  {
    group: 'GPIO',
    intents: [
      { value: 'GPIO_OUTPUT', label: 'GPIO Output', desc: 'Configure pin as digital output' },
      { value: 'GPIO_INPUT',  label: 'GPIO Input',  desc: 'Configure pin as digital input' },
      { value: 'GPIO_TOGGLE', label: 'GPIO Toggle', desc: 'Toggle output pin state' },
      { value: 'GPIO_READ',   label: 'GPIO Read',   desc: 'Read digital input pin state' },
    ],
  },
  {
    group: 'USART',
    intents: [
      { value: 'UART_INIT',    label: 'UART Init',    desc: 'Initialize USART peripheral' },
      { value: 'UART_RECEIVE', label: 'UART Receive', desc: 'Configure UART receive mode' },
    ],
  },
  {
    group: 'TIMER',
    intents: [
      { value: 'TIMER_DELAY', label: 'Timer Delay', desc: 'Generate blocking delay using TIMx' },
    ],
  },
  {
    group: 'RCC',
    intents: [
      { value: 'RCC_ENABLE', label: 'RCC Enable', desc: 'Enable peripheral clock via RCC_APBxENR' },
    ],
  },
];

const INTENT_COLORS = {
  GPIO:  { dot: '#00ff9d', bg: '#00ff9d11', border: '#00ff9d33' },
  USART: { dot: '#00e5ff', bg: '#00e5ff11', border: '#00e5ff33' },
  TIMER: { dot: '#ffcc00', bg: '#ffcc0011', border: '#ffcc0033' },
  RCC:   { dot: '#ff6b35', bg: '#ff6b3511', border: '#ff6b3533' },
};

export default function IntentSelector({ value, onChange, intents = [] }) {
  const selectedIntent = INTENT_GROUPS.flatMap(g => g.intents).find(i => i.value === value);
  const selectedGroup = INTENT_GROUPS.find(g => g.intents.some(i => i.value === value));
  const colors = selectedGroup ? INTENT_COLORS[selectedGroup.group] : null;

  return (
    <div>
      <label className="label-field">Operation Intent</label>
      <div className="relative">
        <select
          className="select-field"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          style={{ fontSize: '0.85rem', paddingTop: '0.6rem', paddingBottom: '0.6rem' }}
        >
          <option value="">— Select Intent —</option>
          {INTENT_GROUPS.map((group) => (
            <optgroup key={group.group} label={`── ${group.group} ──`}>
              {group.intents.map((intent) => (
                <option key={intent.value} value={intent.value}>
                  {intent.label}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </div>

      {selectedIntent && colors && (
        <div
          className="mt-2 p-2.5 rounded flex items-start gap-2 animate-fadeIn"
          style={{ background: colors.bg, border: `1px solid ${colors.border}` }}
        >
          <span
            className="w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0"
            style={{ background: colors.dot, boxShadow: `0 0 6px ${colors.dot}` }}
          />
          <div>
            <p
              className="text-xs font-semibold"
              style={{ color: colors.dot, fontFamily: 'Orbitron', fontSize: '0.65rem', letterSpacing: '0.1em' }}
            >
              {selectedGroup.group} / {selectedIntent.label}
            </p>
            <p className="text-xs mt-0.5" style={{ color: '#7090a0', fontFamily: 'JetBrains Mono' }}>
              {selectedIntent.desc}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
