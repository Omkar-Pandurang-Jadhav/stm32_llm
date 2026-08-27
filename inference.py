import torch
from pathlib import Path
from tokenizers import Tokenizer
import sys
import json

# ===============================
# PATH SETUP
# ===============================
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

# ===============================
# IMPORTS
# ===============================
from preprocessor.preprocessor import preprocess
from json_builder.json_builder import build_json
from model.model import STM32LLM, STM32Config

# ===============================
# LOAD TOKENIZER
# ===============================
tok_path = BASE_DIR / "tokenizer" / "stm32_tokenizer.json"

if not tok_path.exists():
    raise FileNotFoundError(f"Tokenizer not found: {tok_path}")

tokenizer = Tokenizer.from_file(str(tok_path))

# ===============================
# LOAD MODEL
# ===============================
model_path = (
    BASE_DIR
    / "training"
    / "stm32_checkpoints"
    / "final_model.pt"
)

if not model_path.exists():
    raise FileNotFoundError(f"Model checkpoint not found: {model_path}")

config = STM32Config()

# 🔥 Correct tokenizer loading
tok = Tokenizer.from_file(
    str(BASE_DIR / "tokenizer" / "stm32_tokenizer.json")
)

config.vocab_size = tok.get_vocab_size()

# ===============================
# LOAD MODEL
# ===============================
model = STM32LLM(config)

checkpoint = torch.load(
    str(model_path),
    map_location="cpu"
)

model.load_state_dict(checkpoint["model_state"])

model.eval()

print("✅ Model loaded successfully")
print(f"✅ Tokenizer vocab size: {config.vocab_size}")

# ===============================
# MAIN PREDICTION FUNCTION
# ===============================
def predict_prompt(prompt: str):

    # ===============================
    # PREPROCESS
    # ===============================
    clean = preprocess(prompt)["cleaned"]

    # ===============================
    # TOKENIZE
    # ===============================
    enc = tokenizer.encode(clean)

    ids = enc.ids[:config.max_seq_len]
    tokens = enc.tokens[:config.max_seq_len]

    # ===============================
    # PADDING
    # ===============================
    pad_len = config.max_seq_len - len(ids)

    input_ids = ids + [config.pad_token_id] * pad_len

    attention_mask = [1] * len(ids) + [0] * pad_len

    input_ids = torch.tensor([input_ids])
    attention_mask = torch.tensor([attention_mask])

    # ===============================
    # MODEL PREDICTION
    # ===============================
    intent_pred, entity_pred = model.predict(
        input_ids,
        attention_mask
    )

    intent = config.id2intent[intent_pred[0].item()]

    pred_tags = [
        config.id2tag[t.item()]
        for t in entity_pred[0][:len(tokens)]
    ]

    # ===============================
    # EXTRACT ENTITIES
    # ===============================
    entity_dict = {}

    for tok, tag in zip(tokens, pred_tags):

        if (
            tag != "O"
            and tok not in ["<BOS>", "<EOS>", "<PAD>"]
        ):
            entity_dict[tok] = tag

    # ===============================
    # BUILD JSON
    # ===============================
    json_output = build_json(intent, entity_dict)

    # ===============================
    # FINAL RESULT
    # ===============================
    result = {
        "original": prompt,
        "cleaned": clean,
        "tokens": tokens,
        "intent": intent,
        "entities": entity_dict,
        "json": json_output
    }

    # ===============================
    # PRINT FOR TERMINAL TESTING
    # ===============================
    print("\n" + "=" * 60)

    print(f"Original : {prompt}")
    print(f"Cleaned  : {clean}")
    print(f"Tokens   : {tokens}")
    print(f"Intent   : {intent}")

    print("\nEntities:")

    for tok, tag in zip(tokens, pred_tags):
        print(f"  {tok:20s} -> {tag}")

    print("\nJSON Output:")
    print(json.dumps(result, indent=2))

    # ===============================
    # RETURN FOR FASTAPI
    # ===============================
    return result

# ===============================
# INTERACTIVE TERMINAL MODE
# ===============================
if __name__ == "__main__":

    print("\nEnter STM32 prompts to test the model.")
    print("Type 'exit' to quit.\n")

    while True:

        prompt = input(">> ").strip()

        if prompt.lower() in ["exit", "quit"]:
            print("Exiting.")
            break

        if not prompt:
            continue

        try:
            predict_prompt(prompt)

        except Exception as e:
            print(f"Error: {e}")