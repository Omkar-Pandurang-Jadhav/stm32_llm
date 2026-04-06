import json
from pathlib import Path
# ══════════════════════════════════════════════════════
# FIXED detect_data_class()
# NOW takes prompt as second argument
# ══════════════════════════════════════════════════════

def detect_data_class(output_blocks, clean_prompt=""):
    """
    Rules (strict priority order):
    1. ERROR/AMBIGUOUS/INVALID intent  → INVALID
    2. Any assumed flag anywhere        → VALID_PARTIAL
    3. TIMER_DELAY timer not in prompt  → VALID_PARTIAL
    4. UART TX/RX pin present           → VALID_PARTIAL
       (pins are always hardware-fixed)
    5. Otherwise                        → VALID_COMPLETE
    """
    prompt_lower = clean_prompt.lower()

    for block in output_blocks:
        intent = block.get("intent", "")

        # Rule 1
        if intent in ["ERROR","AMBIGUOUS","INVALID"]:
            return "INVALID"

        cfg    = block.get("config", {})
        action = block.get("action", {})
        timing = block.get("timing", {})

        # Rule 2a: top-level config keys
        for key, val in cfg.items():
            if "assumed" in str(key).lower():
                return "VALID_PARTIAL"
            # Rule 2b: nested dict (tx_pin, rx_pin, pwm_pin)
            if isinstance(val, dict):
                if val.get("assumed") is True:
                    return "VALID_PARTIAL"
                for nk in val.keys():
                    if "assumed" in str(nk).lower():
                        return "VALID_PARTIAL"

        # Rule 2c: action block
        if isinstance(action, dict):
            if action.get("assumed") is True:
                return "VALID_PARTIAL"

        # Rule 2d: timing block
        if isinstance(timing, dict):
            if timing.get("assumed") is True:
                return "VALID_PARTIAL"

        # Rule 3: timer not stated in prompt
        if intent == "TIMER_DELAY":
            timer = block.get("peripheral", "")
            if timer and timer.lower() not in prompt_lower:
                return "VALID_PARTIAL"

        # Rule 4: UART pins always hardware-fixed
        if intent in ["UART_INIT","UART_TRANSMIT",
                      "UART_RECEIVE"]:
            if cfg.get("tx_pin") or cfg.get("rx_pin"):
                return "VALID_PARTIAL"

    return "VALID_COMPLETE"
# ── paste detect_data_class above this line ──────────

def standardize_block_flags(block):
    """
    Fix flag format in an existing block in-place.
    """
    intent = block.get("intent","")
    cfg    = block.get("config", {})

    # Move flat flags into nested format
    for flat_key, nested_key in [
        ("tx_pin_assumed", "tx_pin"),
        ("rx_pin_assumed", "rx_pin"),
        ("pwm_pin_assumed","pwm_pin"),
    ]:
        if flat_key in cfg:
            nested = cfg.get(nested_key, {})
            if isinstance(nested, dict):
                nested["assumed"] = True
                cfg[nested_key]   = nested
            del cfg[flat_key]

    # Ensure UART pins always have assumed:true
    if intent in ["UART_INIT","UART_TRANSMIT"]:
        tx = cfg.get("tx_pin",{})
        if isinstance(tx, dict) and tx:
            tx["assumed"]  = True
            cfg["tx_pin"]  = tx

    if intent in ["UART_INIT","UART_RECEIVE"]:
        rx = cfg.get("rx_pin",{})
        if isinstance(rx, dict) and rx:
            rx["assumed"]  = True
            cfg["rx_pin"]  = rx

    if intent == "TIMER_PWM":
        pwm = cfg.get("pwm_pin",{})
        if isinstance(pwm, dict) and pwm:
            pwm["assumed"]  = True
            cfg["pwm_pin"]  = pwm

    # TIMER_DELAY: add timer_assumed if missing
    if intent == "TIMER_DELAY":
        if "timer_assumed" not in cfg:
            cfg["timer_assumed"] = True

    block["config"] = cfg
    return block


def fix_file(path):
    with open(path) as f:
        data = json.load(f)

    label_fixed = 0
    flag_fixed  = 0
    breakdown   = {}

    for ex in data:
        clean_p  = ex.get("clean_prompt","")
        old_cls  = ex.get("data_class","")

        # Fix assumed flag format in all blocks
        new_output = []
        for block in ex.get("output",[]):
            intent = block.get("intent","")
            if intent not in ["ERROR","AMBIGUOUS",
                              "INVALID"]:
                old_cfg = str(block.get("config",{}))
                block   = standardize_block_flags(block)
                if str(block.get("config",{})) != old_cfg:
                    flag_fixed += 1
            new_output.append(block)
        ex["output"] = new_output

        # Fix data_class label
        new_cls = detect_data_class(
            ex["output"], clean_p)
        if new_cls != old_cls:
            ex["data_class"] = new_cls
            label_fixed += 1
        else:
            ex["data_class"] = new_cls

        breakdown[new_cls] = \
            breakdown.get(new_cls, 0) + 1

    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\n{'='*50}")
    print(f"File : {Path(path).name}")
    print(f"Total: {len(data)}")
    print(f"Labels fixed : {label_fixed}")
    print(f"Flags fixed  : {flag_fixed}")
    print(f"Final breakdown:")
    for cls, cnt in sorted(breakdown.items()):
        pct = cnt / len(data) * 100
        print(f"  {cls:20s}: "
              f"{cnt:5d} ({pct:.1f}%)")


if __name__ == "__main__":
    base = Path.home() / "Desktop/stm32_llm/dataset"
    for fname in ["dataset_full.json",
                  "simple_dataset.json",
                  "complex_dataset.json"]:
        p = base / fname
        if p.exists():
            fix_file(str(p))
        else:
            print(f"Not found: {fname}")