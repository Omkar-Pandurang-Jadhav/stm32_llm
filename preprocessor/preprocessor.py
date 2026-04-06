import re

# All common typos user might make
# key = wrong spelling, value = correct
TYPO_MAP = {
    # Action words
    "cnfigure"   : "configure",
    "confgure"   : "configure",
    "configre"   : "configure",
    "otput"      : "output",
    "ouput"      : "output",
    "outpt"      : "output",
    "inpt"       : "input",
    "innput"     : "input",
    "togle"      : "toggle",
    "toggl"      : "toggle",
    "recieve"    : "receive",
    "recive"     : "receive",
    "reciev"     : "receive",
    "tranmit"    : "transmit",
    "transmitt"  : "transmit",
    "trasmit"    : "transmit",
    "initalize"  : "initialize",
    "intialize"  : "initialize",
    "initalise"  : "initialize",
    "enabl"      : "enable",
    "enble"      : "enable",
    "genrate"    : "generate",
    "generat"    : "generate",
    "cnfig"      : "configure",
    "config"     : "configure",
    "otpt"       : "output",
    "oupt"       : "output",
    "inpt"       : "input",
    "50mhz"      : "50MHz",
    "2mhz"       : "2MHz",
    "10mhz"      : "10MHz",

    # Hardware words
    "baudrate"   : "baudrate",
    "baud rate"  : "baudrate",
    "baudrte"    : "baudrate",
    "baud"       : "baudrate",
    "baurdrate"  : "baudrate",
    "baudrae"    : "baudrate",
    "frequecy"   : "frequency",
    "frequncy"   : "frequency",
    "periord"    : "period",
    "presclar"   : "prescaler",
    "prescaler"  : "prescaler",
    "tiimer"     : "timer",
    "tmer"       : "timer",
    "millisecond": "ms",
    "milisecond" : "ms",
    "millisec"   : "ms",
    "milisec"    : "ms",
    "milli"      : "ms",
    "microsecond": "us",
    "microsec"   : "us",
    "evry"       : "every",
    "eevry"      : "every",
    "everey"     : "every",
    "puch"       : "push",
    "pul"        : "pull",
    "puull"      : "pull",
}


# Only these baudrates exist on STM32F103VB
VALID_BAUDRATES = [9600, 19200, 38400, 57600, 115200]

def snap_baudrate(value):
    """
    Smart baudrate correction.
    Handles two cases:
      1. Digit-drop typo: 11520 → 115200 (missing zero)
      2. Close value: 9500 → 9600
    """
    try:
        num = int(value)
        
        # Already a valid baudrate
        if num in VALID_BAUDRATES:
            return str(num)

        # Case 1: Check if adding a zero makes it valid
        # 11520 + "0" = 115200 → valid!
        num_str = str(num)
        with_zero = int(num_str + "0")
        if with_zero in VALID_BAUDRATES:
            return str(with_zero)

        # Case 2: Check if removing a zero makes it valid
        # 96000 → 9600
        if num_str.endswith("0"):
            without_zero = int(num_str[:-1])
            if without_zero in VALID_BAUDRATES:
                return str(without_zero)

        # Case 3: closest by distance (only for small gaps)
        # 9500 → 9600 (gap is small, safe to snap)
        closest = min(VALID_BAUDRATES, key=lambda x: abs(x - num))
        gap_percent = abs(closest - num) / closest
        if gap_percent < 0.05:   # only within 5% gap
            return str(closest)

        # Cannot confidently correct
        return str(num)

    except:
        return value
    
def normalize_stm32_keywords(text):
    """
    Fix case and format of STM32-specific words
    """
    # Fix peripheral names to uppercase
    # Order matters — longer patterns first!
    peripherals = [
        "USART1", "USART2", "USART3",
        "GPIOA", "GPIOB", "GPIOC", "GPIOD",
        "TIM1", "TIM2", "TIM3", "TIM4",
    ]
    for p in peripherals:
        # case-insensitive replace
        text = re.sub(re.escape(p), p, text, flags=re.IGNORECASE)

    # Fix pin format: PA5, PB3 etc
    # Matches: pa5, Pa5, pA5 → PA5
    text = re.sub(
        r'\b([Pp][Aa])(\d+)\b', 
        lambda m: f"PA{m.group(2)}", 
        text
    )
    text = re.sub(
        r'\b([Pp][Bb])(\d+)\b',
        lambda m: f"PB{m.group(2)}",
        text
    )
    text = re.sub(
        r'\b([Pp][Cc])(\d+)\b',
        lambda m: f"PC{m.group(2)}",
        text
    )

    # Fix port word format
    # "porta" or "port a" or "gpio a" → "port_A"
    text = re.sub(r'\bgpio\s*a\b', 'port_A', text, flags=re.IGNORECASE)
    text = re.sub(r'\bgpio\s*b\b', 'port_B', text, flags=re.IGNORECASE)
    text = re.sub(r'\bgpio\s*c\b', 'port_C', text, flags=re.IGNORECASE)
    text = re.sub(r'\bport\s*a\b', 'port_A', text, flags=re.IGNORECASE)
    text = re.sub(r'\bport\s*b\b', 'port_B', text, flags=re.IGNORECASE)
    text = re.sub(r'\bport\s*c\b', 'port_C', text, flags=re.IGNORECASE)
    text = re.sub(r'\bporta\b',    'port_A', text, flags=re.IGNORECASE)
    text = re.sub(r'\bportb\b',    'port_B', text, flags=re.IGNORECASE)
    text = re.sub(r'\bportc\b',    'port_C', text, flags=re.IGNORECASE)
    text = re.sub(r'50\s*mhz', '50MHz', text, flags=re.IGNORECASE)
    text = re.sub(r'10\s*mhz', '10MHz', text, flags=re.IGNORECASE)
    text = re.sub(r'2\s*mhz',  '2MHz',  text, flags=re.IGNORECASE)

    return text

def fix_typos(text):
    """
    Replace known typos with correct words
    """
    words = text.split()
    fixed = []
    for word in words:
        # strip punctuation for matching
        clean = word.strip('.,!?')
        if clean.lower() in TYPO_MAP:
            fixed.append(TYPO_MAP[clean.lower()])
        else:
            fixed.append(word)
    return ' '.join(fixed)


def normalize_units(text):
    """
    Fix time unit variations
    """
    # "500 milliseconds" → "500ms"
    text = re.sub(r'(\d+)\s*milliseconds?', r'\1ms', text, flags=re.IGNORECASE)
    text = re.sub(r'(\d+)\s*microseconds?', r'\1us', text, flags=re.IGNORECASE)
    text = re.sub(r'(\d+)\s*miliseconds?',  r'\1ms', text, flags=re.IGNORECASE)
    text = re.sub(r'(\d+)\s*ms\b',          r'\1ms', text, flags=re.IGNORECASE)
    text = re.sub(r'(\d+)\s*us\b',          r'\1us', text, flags=re.IGNORECASE)

    # "half second" → "500ms"
    text = re.sub(r'half\s+second', '500ms', text, flags=re.IGNORECASE)
    # "one second" → "1000ms"
    text = re.sub(r'one\s+second',  '1000ms', text, flags=re.IGNORECASE)
    # "1 second" → "1000ms"
    text = re.sub(r'(\d+)\s*seconds?', 
                  lambda m: f"{int(m.group(1))*1000}ms", 
                  text, flags=re.IGNORECASE)

    # Fix baudrate near-matches
    # Find any number near a baudrate keyword
    def fix_baud(match):
        return snap_baudrate(match.group(0))
    text = re.sub(r'\b\d{4,7}\b', fix_baud, text)

    return text


def normalize_modes(text):
    # merge push pull → push_pull
    text = re.sub(r'push\s+pull', 'push_pull', text)

    # merge pull up/down
    text = re.sub(r'pull\s+up', 'pull_up', text)
    text = re.sub(r'pull\s+down', 'pull_down', text)

    return text

def normalize_percent(text):
    # if PWM present, assume % for numbers
    if "pwm" in text:
        text = re.sub(r'\b(\d{1,3})\b', r'\1%', text)
    return text


def infer_time_units(text):
    if "delay" in text or "blink" in text:
        text = re.sub(r'\b(\d+)\b(?!\s*(ms|us))', r'\1ms', text)
    return text


# Words that signal multiple intents
MULTI_INTENT_SIGNALS = [
    " and ", " also ", " then ", 
    " additionally ", " plus ",
    " as well as ", " while "
]

def detect_complexity(text):
    """
    Returns: 'simple' or 'complex'
    """
    text_lower = text.lower()
    for signal in MULTI_INTENT_SIGNALS:
        if signal in text_lower:
            return "complex"
    return "simple"

def clean_punctuation(text):
    """
    Remove extra punctuation and spaces
    """
    # Replace multiple spaces with one
    text = re.sub(r'\s+', ' ', text)
    # Remove punctuation except useful ones
    text = re.sub(r'[^\w\s_%]', ' ', text)
    
    text = re.sub(r'(\d)\s+%',r'\1%', text)
    # Clean up spaces again after punctuation removal
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def preprocess(raw_prompt):
    """
    MAIN FUNCTION
    Input:  raw messy user prompt
    Output: dictionary with clean text + metadata
    """
    text = raw_prompt

    # Step 1: lowercase first
    text = text.lower()

    # 🔥 FIX 1: correct regex
    text = re.sub(r'\bch\s*([1-4])\b', r'CH\1', text)

    # Step 2: typo + unit fixes
    text = fix_typos(text)
    text = normalize_units(text)
    text = normalize_modes(text)

    # ❌ REMOVE THIS (BREAKING YOUR TOKENS)
    # text = infer_time_units(text)

    # 🔥 FIX 2: protect PWM early
    text = re.sub(r'\bpwm\b', 'PWM', text)

    # Step 4: clean punctuation
    text = clean_punctuation(text)

    # 🔥 FIX 3: fix % after cleaning
    text = re.sub(r'(\d)\s+%', r'\1%', text)

    # Step 5: STM32 normalization
    text = normalize_stm32_keywords(text)

    # Step 6: detect complexity
    complexity = detect_complexity(text)

    # 🔥 FINAL PROTECTION (VERY IMPORTANT)
    text = re.sub(r'\bCH([1-4])\b', r'CH\1', text)
    text = re.sub(r'\bPWM\b', 'PWM', text)
    text = re.sub(r'(\d)\s+%', r'\1%', text)

    # Step 7: final strip
    text = text.strip()

    return {
        "original"   : raw_prompt,
        "cleaned"    : text,
        "complexity" : complexity,
        "char_count" : len(text),
        "word_count" : len(text.split())
    }
    
    
# =====================
# TEST YOUR PREPROCESSOR
# =====================
if __name__ == "__main__":

    test_prompts = [
        # Simple errors
        "cnfigure PA5 as otput push pull",
        "blink led on pa5 evry 500 milliseconds",
        "init usart1 at 11520 baud",

        # Complex prompts
        "blink PA5 every 500ms and send data via usart1",
        "configure pb3 as inpt and togle pa5",

        # Heavy errors
        "cnfig pa5 otpt 50mhz and tranmit via usart1 at 11520 baudrte",

        # Wrong UART pin (model catches this, validator fixes)
        "init USART1 tx on PB5 at 115200",
    ]

    print("=" * 60)
    print("PREPROCESSOR TEST RESULTS")
    print("=" * 60)

    for prompt in test_prompts:
        result = preprocess(prompt)
        print(f"\nORIGINAL : {result['original']}")
        print(f"CLEANED  : {result['cleaned']}")
        print(f"COMPLEXITY: {result['complexity']}")
        print("-" * 60)

