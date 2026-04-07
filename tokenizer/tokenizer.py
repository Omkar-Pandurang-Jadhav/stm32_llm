import json
import os
import re
from pathlib import Path
from tokenizers import Tokenizer
from tokenizers.models import BPE
from tokenizers.trainers import BpeTrainer
from tokenizers.pre_tokenizers import Sequence,Whitespace,Split
from tokenizers.processors import TemplateProcessing
from tokenizers import AddedToken

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from preprocessor.preprocessor import preprocess

# ══════════════════════════════════════════════════════
# SPECIAL TOKENS
# ══════════════════════════════════════════════════════

SPECIAL_TOKENS = [
    "<PAD>",
    "<UNK>",
    "<BOS>",
    "<EOS>",
    "<SEP>",
]

# ══════════════════════════════════════════════════════
# DOMAIN VOCAB (UNCHANGED)
# ══════════════════════════════════════════════════════

DOMAIN_VOCAB = [

    # ── GPIO pins ──────────────────────────────────────
    "PA0","PA1","PA2","PA3","PA4","PA5","PA6","PA7",
    "PA8","PA9","PA10","PA11","PA12",
    "PB0","PB1","PB2","PB5","PB6","PB7",
    "PB8","PB9","PB10","PB11","PB12","PB13","PB14","PB15",
    "PC13","PC14","PC15",
    "PD0","PD1",

    # Short form pins (used in prompts)
    "A0","A1","A2","A3","A4","A5","A6","A7",
    "A8","A9","A10","A11","A12",
    "B0","B1","B2","B5","B6","B7",
    "B8","B9","B10","B11","B12","B13","B14","B15",

    # ── Peripherals ────────────────────────────────────
    "GPIOA","GPIOB","GPIOC","GPIOD",
    "USART1","USART2","USART3",
    "UART1","UART2","UART3",
    "TIM1","TIM2","TIM3","TIM4",
    "PWM",

    # ── RCC registers ──────────────────────────────────
    "RCC_APB2ENR","RCC_APB1ENR",
    "APB2ENR","APB1ENR","APB2","APB1",
    "IOPAEN","IOPBEN","IOPCEN","IOPDEN",
    "USART1EN","USART2EN","USART3EN",
    "TIM2EN","TIM3EN","TIM4EN",

    # ── GPIO modes ─────────────────────────────────────
    "output_push_pull","output_open_drain",
    "input_floating","input_pull_up","input_pull_down",
    "alternate_push_pull",

    # ── Speeds ─────────────────────────────────────────
    "50MHz","10MHz","2MHz",

    # ── Baudrates ──────────────────────────────────────
    "9600","19200","38400","57600","115200",

    # ── Timer channels ─────────────────────────────────
    "CH1","CH2","CH3","CH4",

    # ── Intent names ───────────────────────────────────
    "GPIO_OUTPUT","GPIO_INPUT","GPIO_TOGGLE","GPIO_READ",
    "UART_INIT","UART_TRANSMIT","UART_RECEIVE",
    "TIMER_DELAY","TIMER_PWM","RCC_ENABLE",
    "VALID_COMPLETE","VALID_PARTIAL",
    "INVALID","AMBIGUOUS","ERROR",

    # ── Base addresses ─────────────────────────────────
    "0x40010400","0x40010800","0x40010C00","0x40011000",
    "0x40013800","0x40004000","0x40004400",
    "0x40000000","0x40000400","0x40000800",
    "0x40021000",

    # ── Register offsets ───────────────────────────────
    "0x00","0x04","0x08","0x0C","0x10",
    "0x14","0x18","0x1C","0x20","0x24",
    "0x28","0x2C","0x34","0x38","0x3C",

    # ── Common action words ────────────────────────────
    "configure","setup","initialize","init",
    "enable","disable","toggle","blink","read",
    "write","send","receive","transmit","generate",
    "create","start","stop","wait","delay","set",
    "get","make","output","input","flash","flip",
    "switch","drive","assign","prepare","sample",
    "check","capture","detect","monitor","collect",
    "poll","listen","produce","block",
    "hold","pause","stall","halt","establish","open",
    "bring","allow","ungate","activate","feed",

    # ── Hardware words ─────────────────────────────────
    "baudrate","baud","prescaler","period","duty",
    "frequency","clock","channel","pin","port",
    "timer","output","input","push","pull",
    "floating","alternate","serial","data","byte",
    "string","message","bit","bits","parity","stop",
    "word","none","even","odd","high","low","state",
    "value","register","cycle","waveform","signal",
    "interval","periodic","blocking","digital",
    "logic","voltage","level","mode","speed","rate",

    # ── Time values ────────────────────────────────────
    "100ms","200ms","500ms","1000ms","2000ms",

    # ── Connectors ─────────────────────────────────────
    "and","also","then","additionally","plus",
    "as","well","via","with","at","on","of",
    "for","from","through","using","by","in",
    "into","to","per","every","each","while",
    "after","before","when","if","the","a","an",

    # ── Duty cycle values ──────────────────────────────
    "25%","50%","75%",

]



# ══════════════════════════════════════════════════════
# FIXED NORMALIZATION
# ══════════════════════════════════════════════════════
def normalize_text(text):
    text = text.lower()

    # ===== FIX MODES =====
    # Replace FULL pattern (avoid "output output_push_pull")
    text = re.sub(r'output\s+push\s+pull', 'output_push_pull', text)
    text = re.sub(r'push\s+pull', 'output_push_pull', text)

    text = re.sub(r'output\s+open\s+drain', 'output_open_drain', text)
    text = re.sub(r'open\s+drain', 'output_open_drain', text)

    text = re.sub(r'pull\s+up', 'input_pull_up', text)
    text = re.sub(r'pull\s+down', 'input_pull_down', text)

    # ===== REMOVE DUPLICATE WORD =====
    text = re.sub(r'\boutput\s+output_push_pull\b', 'output_push_pull', text)

    # ===== FIX % (CRITICAL) =====
    text = re.sub(r'(\d+)\s+%', r'\1%', text)

    # ===== FIX ms =====
    text = re.sub(r'(\d+)\s+ms', r'\1ms', text)

    # ===== FIX MHz =====
    text = re.sub(r'(\d+)\s*mhz', r'\1MHz', text)

    # ===== FIX PERIPHERAL CASE =====
    # VERY IMPORTANT for domain vocab matching
    
    text = re.sub(r'\bch(\d)\b', r'CH\1', text)
    text = re.sub(r'\bpa(\d+)\b', r'PA\1', text)
    text = re.sub(r'\bpb(\d+)\b', r'PB\1', text)
    text = re.sub(r'\bpc(\d+)\b', r'PC\1', text)

    text = re.sub(r'\btim(\d+)\b', r'TIM\1', text)
    text = re.sub(r'\busart(\d+)\b', r'USART\1', text)

    text = re.sub(r'\bpwm\b', 'PWM', text)
    # Fix duty cycle — must be atomic BEFORE whitespace split
    # "50 %" → "50%" and "25 %" → "25%"
    text = re.sub(r'\b(25|50|75|100)\s*%', r'\1%', text)

    # Fix time — "500 ms" → "500ms"
    text = re.sub(r'\b(\d+)\s*ms\b', r'\1ms', text)

    #Fix speed — "50 MHz" → "50MHz"  
    text = re.sub(r'\b(\d+)\s*[Mm][Hh][Zz]\b', r'\1MHz', text)

    # CH must be uppercase before tokenization
    text = re.sub(r'\bch\s*([1-4])\b', r'CH\1', text, flags=re.IGNORECASE)
    
    text = re.sub(r'\bpa(\d+)\b',r'PA\1',text)
    text = re.sub(r'\bpb(\d+)\b',r'PB\1',text)
    text = re.sub(r'\bpc(\d+)\b',r'PC\1',text)
    text = re.sub(r'\bpd(\d+)\b',r'PD\1',text)
    
    text = re.sub(r'\b(P[A-D])(\d{1,2})\b',r'\1 \2',text)

    # ===== CLEAN =====
    text = re.sub(r'\s+', ' ', text)
    
    text = re.sub(r'\bCH([1-4])\b',r'CH\1', text)
    text = re.sub(r'\bPWM\b', 'PWM', text)
    text = re.sub(r'(\d+)%',r'\1%',text)
    
    text = re.sub(r'push\s+pull',
                  'output_push_pull', text,
                  flags=re.IGNORECASE)
    text = re.sub(r'open\s+drain',
                  'output_open_drain', text,
                  flags=re.IGNORECASE)
    text = re.sub(r'pull\s+up',
                  'input_pull_up', text,
                  flags=re.IGNORECASE)
    text = re.sub(r'pull\s+down',
                  'input_pull_down', text,
                  flags=re.IGNORECASE)
   
    
   

    return text.strip()

# ══════════════════════════════════════════════════════
# BUILD CORPUS
# ══════════════════════════════════════════════════════

def build_corpus(dataset_dir):
    corpus = []
    base_path = Path(dataset_dir)

    files = [
        base_path / "simple_dataset.json",
        base_path / "complex_dataset.json",
        base_path / "dataset_full.json",
    ]

    seen = set()

    for fpath in files:
        if not fpath.exists():
            continue

        with open(fpath) as f:
            data = json.load(f)

        for ex in data:
            cp = normalize_text(ex.get("clean_prompt","")).strip()
            np_ = normalize_text(ex.get("prompt","")).strip()
            
            # FINAL ENFORCEMENT (CRITICAL)
            cp = cp.replace("pwm", "PWM")
            cp = re.sub(r'\bch([1-4])\b', r'CH\1', cp)

            np_ = np_.replace("pwm", "PWM")
            np_ = re.sub(r'\bch([1-4])\b', r'CH\1', np_)

            if cp and cp not in seen:
                corpus.append(cp)
                seen.add(cp)

            if np_ and np_ not in seen:
                corpus.append(np_)
                seen.add(np_)

    corpus.extend(DOMAIN_VOCAB)
    corpus.extend(["PWM PWM PWM PWM PWM","TIM3 CH1 PWM","TIM2 CH2 PWM","TIM4 CH3 PWM"])
    corpus.extend(["CH1 CH2 CH3 CH4 CH1 CH2 CH3 CH4",
                   "TIM3 CH1","TIM3 CH2","50% 50% 50% 25% 75% 50% 25%" ])

    print(f"  Corpus size: {len(corpus)} sentences")
    return corpus


def save_corpus(corpus, path):
    with open(path, "w") as f:
        for line in corpus:
            line = normalize_text(line)
            f.write(line.strip() + "\n")

    print(f"  Saved corpus: {path}")

# ══════════════════════════════════════════════════════
# TRAIN TOKENIZER
# ══════════════════════════════════════════════════════

def train_tokenizer(corpus_file, output_dir):

    tokenizer = Tokenizer(BPE(unk_token="<UNK>"))
    tokenizer.pre_tokenizer = Sequence([
        Whitespace(),
        Split(pattern=r"([A-Z]{2})(\d{1,2})",behavior="isolated")
    ])

    # ── Step 1: Train BPE normally ────────────────────
    trainer = BpeTrainer(
        vocab_size     = 4000,
        min_frequency  = 1,
        special_tokens = SPECIAL_TOKENS,
        initial_alphabet = list(set(
            list("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_%")
        )),
    )
    tokenizer.train([str(corpus_file)], trainer)

    # ── Step 2: FORCE atomic tokens after training ────
    # This is the critical fix.
    # add_special_tokens() guarantees these are NEVER
    # split regardless of what BPE learned.
    ATOMIC_TOKENS = [
        # Channels — BPE splits CH1 → ch + 1
        AddedToken("CH1", single_word=True),
        AddedToken("CH2", single_word=True),
        AddedToken("CH3", single_word=True),
        AddedToken("CH4", single_word=True),

        # PWM — BPE splits → pw + m
        AddedToken("PWM", single_word=True),

        # Duty cycles — BPE splits 50% → 50 + %
        AddedToken("25%",  single_word=False),
        AddedToken("50%",  single_word=False),
        AddedToken("75%",  single_word=False),
        AddedToken("100%", single_word=False),

        # Speeds — BPE sometimes splits
        AddedToken("50MHz", single_word=False),
        AddedToken("10MHz", single_word=False),
        AddedToken("2MHz",  single_word=False),

        # Time values
        AddedToken("100ms",  single_word=False),
        AddedToken("200ms",  single_word=False),
        AddedToken("500ms",  single_word=False),
        AddedToken("1000ms", single_word=False),
        AddedToken("2000ms", single_word=False),

        # Pins — sometimes split PA + 10
        AddedToken("PA",single_word=True),
        AddedToken("PB",single_word=True),
        AddedToken("PC",single_word=True),
        AddedToken("PD",single_word=True),

        # GPIO modes — underscores cause splits
        AddedToken("output_push_pull",  single_word=False),
        AddedToken("output_open_drain", single_word=False),
        AddedToken("input_floating",    single_word=False),
        AddedToken("input_pull_up",     single_word=False),
        AddedToken("input_pull_down",   single_word=False),

        # Intent names
        AddedToken("GPIO_OUTPUT",   single_word=False),
        AddedToken("GPIO_INPUT",    single_word=False),
        AddedToken("GPIO_TOGGLE",   single_word=False),
        AddedToken("GPIO_READ",     single_word=False),
        AddedToken("UART_INIT",     single_word=False),
        AddedToken("UART_TRANSMIT", single_word=False),
        AddedToken("UART_RECEIVE",  single_word=False),
        AddedToken("TIMER_DELAY",   single_word=False),
        AddedToken("TIMER_PWM",     single_word=False),
        AddedToken("RCC_ENABLE",    single_word=False),

        # RCC registers
        AddedToken("RCC_APB2ENR", single_word=False),
        AddedToken("RCC_APB1ENR", single_word=False),
    ]

    tokenizer.add_tokens(ATOMIC_TOKENS)

    # ── Step 3: Post processor ─────────────────────────
    tokenizer.post_processor = TemplateProcessing(
        single = "<BOS> $A <EOS>",
        special_tokens = [
            ("<BOS>", tokenizer.token_to_id("<BOS>")),
            ("<EOS>", tokenizer.token_to_id("<EOS>")),
        ],
    )

    out_path = Path(output_dir) / "stm32_tokenizer.json"
    tokenizer.save(str(out_path))
    print(f"  Saved: {out_path}")
    return tokenizer


# ══════════════════════════════════════════════════════
# VERIFY (UNCHANGED STYLE)
# ══════════════════════════════════════════════════════

def verify_tokenizer(tokenizer):
    print(f"\n{'='*55}")
    print("TOKENIZER VERIFICATION")
    print(f"{'='*55}")

    # Critical atomic token tests
    critical_tests = [
        # (input,          must_contain_as_single_token)
        ("CH1",            "CH1"),
        ("CH2",            "CH2"),
        ("CH3",            "CH3"),
        ("CH4",            "CH4"),
        ("PWM",            "PWM"),
        ("50%",            "50%"),
        ("25%",            "25%"),
        ("75%",            "75%"),
        ("50MHz",          "50MHz"),
        ("500ms",          "500ms"),
        ("USART1",         "USART1"),
        ("TIM3",           "TIM3"),
        ("PA5",            "PA5"),
        ("output_push_pull","output_push_pull"),
        ("115200",         "115200"),
    ]

    print("\n[Critical Atomic Tokens]")
    all_pass = True
    for text, expected in critical_tests:
        norm   = normalize_text(text)
        enc    = tokenizer.encode(norm)
        tokens = enc.tokens[1:-1]  # strip BOS/EOS
        is_one = (len(tokens) == 1 and
                  tokens[0] == expected)
        icon   = "✅" if is_one else "❌"
        if not is_one:
            all_pass = False
        print(f"  {icon} '{text}' → {tokens}")

    # Full prompt tests
    print(f"\n[Full Prompts]")
    prompts = [
        "setup TIM3 CH1 PWM with 50% duty cycle",
        "generate PWM on TIM3 CH2",
        "set duty cycle to 25%",
        "configure PA5 as output_push_pull 50MHz",
        "initialize USART1 at 115200 baud",
        "generate 500ms delay using TIM3",
        "blink PA5 every 500ms and init USART1 at 115200 baud",
        "cnfig PA5 otpt 50mhz",
        "configure A5 output at 50Mhz"
    ]

    for p in prompts:
        norm = normalize_text(p)
        clean = preprocess(norm)["cleaned"]
        enc  = tokenizer.encode(clean)
        print(f"\n  Prompt : {p}")
        print(f"  Tokens : {enc.tokens[1:-1]}")
        print(f"  Count  : {len(enc.tokens)-2}")

    vocab = tokenizer.get_vocab()
    print(f"\nVocabulary size: {len(vocab)}")

    if all_pass:
        print("\n✅ All critical tokens are atomic")
    else:
        print("\n⚠ Some tokens still splitting")
        print("  → Check corpus has enough frequency")
        print("  → add_tokens() should fix remaining")

    return all_pass

# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════

if __name__ == "__main__":

    base_dir = Path(__file__).parent.parent
    dataset_dir = base_dir / "dataset"
    tokenizer_dir = Path(__file__).parent
    corpus_file = tokenizer_dir / "corpus.txt"

    print("STM32 TOKENIZER TRAINING")

    corpus = build_corpus(str(dataset_dir))
    save_corpus(corpus, str(corpus_file))

    tokenizer = train_tokenizer(corpus_file, tokenizer_dir)

    verify_tokenizer(tokenizer)