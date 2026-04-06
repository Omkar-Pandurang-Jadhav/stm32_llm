import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
import json
import sys
import os
import time
import math
from pathlib import Path
from tokenizers import Tokenizer

# ── Import your model ─────────────────────────────────
sys.path.append(str(Path(__file__).parent.parent))
from model.model import STM32LLM, STM32Config, STM32Loss

# ══════════════════════════════════════════════════════
# TRAINING CONFIG
# Change these based on CPU vs GPU
# ══════════════════════════════════════════════════════

class TrainConfig:
    def __init__(self, device_type="auto"):

        # ── Device ────────────────────────────────────
        if device_type == "auto":
            self.device = (
                "cuda" if torch.cuda.is_available()
                else "cpu"
            )
        else:
            self.device = device_type

        is_gpu = self.device == "cuda"

        # ── Batch size ────────────────────────────────
        # GPU can handle larger batches
        self.batch_size     = 32 if is_gpu else 8

        # ── Learning rate ─────────────────────────────
        self.lr             = 3e-4

        # ── Epochs per stage ──────────────────────────
        # CPU: fewer epochs for testing
        # GPU: full training
        if is_gpu:
            self.stage1_epochs = 15
            self.stage2_epochs = 20
            self.stage3_epochs = 20
            self.stage4_epochs = 10
        else:
            # CPU mode — just verify it works
            self.stage1_epochs = 2
            self.stage2_epochs = 2
            self.stage3_epochs = 2
            self.stage4_epochs = 1

        # ── Other settings ────────────────────────────
        self.warmup_steps   = 100
        self.weight_decay   = 0.01
        self.grad_clip      = 1.0
        self.save_every     = 5    # save every N epochs
        self.log_every      = 10   # log every N batches

        # ── Paths ─────────────────────────────────────
        base                = Path(__file__).parent.parent
        self.dataset_dir    = base / "dataset"
        self.tokenizer_path = (base / "tokenizer" /
                               "stm32_tokenizer.json")
        self.save_dir       = Path(__file__).parent / "checkpoints"
        self.save_dir.mkdir(exist_ok=True)

        print(f"\nDevice     : {self.device}")
        print(f"Batch size : {self.batch_size}")
        print(f"Stage epochs: "
              f"{self.stage1_epochs}/"
              f"{self.stage2_epochs}/"
              f"{self.stage3_epochs}/"
              f"{self.stage4_epochs}")


# ══════════════════════════════════════════════════════
# DATASET CLASS
# Converts JSON examples into tensors
# ══════════════════════════════════════════════════════

class STM32Dataset(Dataset):
    def __init__(self, examples, tokenizer,
                 model_config, use_noisy=False):
        """
        examples     : list of dataset examples
        tokenizer    : your trained BPE tokenizer
        model_config : STM32Config instance
        use_noisy    : use noisy or clean prompt
        """
        self.tokenizer    = tokenizer
        self.cfg          = model_config
        self.use_noisy    = use_noisy
        self.examples     = []

        # Build entity tag vocabulary
        # For converting JSON config to NER labels
        self.entity_map = self._build_entity_map()

        # Process all examples
        skip = 0
        for ex in examples:
            try:
                processed = self._process(ex)
                if processed:
                    self.examples.append(processed)
            except Exception:
                skip += 1
        if skip > 0:
            print(f"  Skipped {skip} examples "
                  f"(processing error)")

    def _build_entity_map(self):
        """
        Maps known token strings to entity tags.
        Used to auto-label tokens during training.
        """
        entity_map = {}

        # Ports
        for p in ["A","B","C","D"]:
            entity_map[p]        = "B-PORT"
            entity_map[f"P{p}"]  = "B-PORT"
            
        for port in ["A","B","C","D"]:
            for pin in range(16):
                entity_map[f"P{port}{pin}"]="B-PIN"

        # Pins 0-15
        for n in range(16):
            entity_map[str(n)]   = "B-PIN"

        # Speeds
        for s in ["50MHz","10MHz","2MHz"]:
            entity_map[s]        = "B-SPEED"

        # Modes
        for m in ["output_push_pull",
                  "output_open_drain",
                  "input_floating",
                  "input_pull_up",
                  "input_pull_down"]:
            entity_map[m]        = "B-MODE"

        # UART
        for u in ["USART1","USART2","USART3",
                  "UART1","UART2","UART3"]:
            entity_map[u]        = "B-UART"

        # Baudrates
        for b in ["9600","19200","38400",
                  "57600","115200"]:
            entity_map[b]        = "B-BAUDRATE"

        # Timers
        for t in ["TIM2","TIM3","TIM4"]:
            entity_map[t]        = "B-TIMER"

        # Delays
        for d in ["100ms","200ms","500ms",
                  "1000ms","2000ms"]:
            entity_map[d]        = "B-DELAY"

        # Duty cycles
        for dc in ["25%","50%","75%"]:
            entity_map[dc]       = "B-DUTY"

        # Channels
        for ch in ["CH1","CH2","CH3","CH4"]:
            entity_map[ch]       = "B-CHANNEL"

        return entity_map

    def _get_intent_label(self, output):
        """
        Extract intent class from JSON output block.
        For multi-intent, use first intent.
        """
        if not output:
            return self.cfg.intent2id.get(
                "AMBIGUOUS", 10)

        first  = output[0]
        intent = first.get("intent", "AMBIGUOUS")

        # Map ERROR/INVALID to INVALID class
        if intent in ["ERROR", "INVALID"]:
            intent = "INVALID"

        return self.cfg.intent2id.get(
            intent,
            self.cfg.intent2id["AMBIGUOUS"]
        )

    def _get_entity_labels(self, token_strings,
                           seq_len):
        """
        Label each token with its entity tag.
        Uses entity_map for known tokens.
        Returns tensor of tag IDs.
        -100 for padding (ignored in loss).
        """
        labels = []
        O_id   = self.cfg.tag2id["O"]

        for tok in token_strings:
            # Remove BOS/EOS/PAD special tokens
            if tok in ["<BOS>","<EOS>",
                       "<PAD>","<UNK>","<SEP>"]:
                labels.append(-100)
            else:
                tag    = self.entity_map.get(tok, "O")
                tag_id = self.cfg.tag2id.get(
                    tag, O_id)
                labels.append(tag_id)

        # Pad to max_seq_len
        pad_len = seq_len - len(labels)
        labels  = labels + [-100] * pad_len
        return labels[:seq_len]

    def _process(self, ex):
        """
        Convert one dataset example to tensors.
        """
        # Choose clean or noisy prompt
        if self.use_noisy:
            prompt = ex.get("prompt",
                            ex.get("clean_prompt",""))
        else:
            prompt = ex.get("clean_prompt",
                            ex.get("prompt",""))

        if not prompt or not prompt.strip():
            return None
        
     

        # ✅ ADD THIS BLOCK HERE
        try:
            from preprocessor.preprocessor import preprocess
            processed=preprocess(prompt)
            prompt = processed["cleaned"]
        except:
            prompt = prompt.lower().strip()

        output = ex.get("output", [])
        T      = self.cfg.max_seq_len

        # Tokenize
        enc    = self.tokenizer.encode(prompt)
        ids    = enc.ids[:T]
        tokens = enc.tokens[:T]

        # Build attention mask
        pad_id  = self.cfg.pad_token_id
        pad_len = T - len(ids)
        mask    = [1]*len(ids) + [0]*pad_len
        ids     = ids + [pad_id]*pad_len

        # Get labels
        intent_label = self._get_intent_label(output)
        entity_labels = self._get_entity_labels(
            tokens, T)

        return {
            "input_ids":      torch.tensor(
                ids, dtype=torch.long),
            "attention_mask": torch.tensor(
                mask, dtype=torch.long),
            "intent_label":   torch.tensor(
                intent_label, dtype=torch.long),
            "entity_labels":  torch.tensor(
                entity_labels, dtype=torch.long),
            "prompt":         prompt,
        }

    def __len__(self):
        return len(self.examples)

    def __getitem__(self, idx):
        return self.examples[idx]


# ══════════════════════════════════════════════════════
# DATA LOADER BUILDERS
# ══════════════════════════════════════════════════════

def load_json(path):
    with open(path) as f:
        return json.load(f)


def filter_by_class(data, classes):
    """Filter examples by data_class field."""
    return [x for x in data
            if x.get("data_class","") in classes]


def filter_by_noise(data, levels):
    """Filter examples by noise_level field."""
    return [x for x in data
            if x.get("noise_level","") in levels]


def filter_by_complexity(data, complexities):
    """Filter examples by complexity field."""
    return [x for x in data
            if x.get("complexity","") in complexities]


def make_loader(examples, tokenizer,
                model_cfg, train_cfg,
                use_noisy=False, shuffle=True):
    dataset = STM32Dataset(
        examples, tokenizer,
        model_cfg, use_noisy)
    print(f"  Dataset size: {len(dataset)} examples")
    return DataLoader(
        dataset,
        batch_size  = train_cfg.batch_size,
        shuffle     = shuffle,
        num_workers = 0,
        pin_memory  = (train_cfg.device == "cuda"),
    )


# ══════════════════════════════════════════════════════
# TRAINING UTILITIES
# ══════════════════════════════════════════════════════

def get_lr(step, embed_dim, warmup_steps):
    """
    Transformer learning rate schedule.
    Warmup then decay.
    Standard formula from Attention paper.
    """
    if step == 0:
        step = 1
    return (embed_dim ** -0.5) * min(
        step ** -0.5,
        step * (warmup_steps ** -1.5)
    )


class Trainer:
    def __init__(self, model, train_cfg,
                 model_cfg):
        self.model      = model
        self.cfg        = train_cfg
        self.model_cfg  = model_cfg
        self.device     = torch.device(
            train_cfg.device)
        self.loss_fn    = STM32Loss(model_cfg)
        self.optimizer  = torch.optim.AdamW(
            model.parameters(),
            lr           = train_cfg.lr,
            weight_decay = train_cfg.weight_decay,
            betas        = (0.9, 0.999),
        )
        self.step       = 0
        self.history    = []

    def train_epoch(self, loader, epoch):
        self.model.train()
        total_loss   = 0
        intent_loss  = 0
        entity_loss  = 0
        correct      = 0
        total        = 0
        t_start      = time.time()

        for batch_idx, batch in enumerate(loader):
            # Move to device
            ids    = batch["input_ids"].to(
                self.device)
            mask   = batch["attention_mask"].to(
                self.device)
            i_lbl  = batch["intent_label"].to(
                self.device)
            e_lbl  = batch["entity_labels"].to(
                self.device)

            # Forward pass
            i_logits, e_logits = self.model(
                ids, mask)

            # Compute loss
            loss, i_loss, e_loss = self.loss_fn(
                i_logits, i_lbl,
                e_logits, e_lbl,
            )

            # Backward pass
            self.optimizer.zero_grad()
            loss.backward()

            # Gradient clipping
            torch.nn.utils.clip_grad_norm_(
                self.model.parameters(),
                self.cfg.grad_clip,
            )

            self.optimizer.step()
            self.step += 1

            # Track metrics
            total_loss  += loss.item()
            intent_loss += i_loss.item()
            entity_loss += e_loss.item()

            # Intent accuracy
            preds    = torch.argmax(
                i_logits, dim=-1)
            correct += (preds == i_lbl).sum().item()
            total   += i_lbl.size(0)

            # Log
            if (batch_idx + 1) % \
               self.cfg.log_every == 0:
                avg_loss = total_loss / \
                           (batch_idx + 1)
                acc      = correct / total * 100
                elapsed  = time.time() - t_start
                print(f"    Batch {batch_idx+1:4d}"
                      f" | Loss {avg_loss:.4f}"
                      f" | Intent acc {acc:.1f}%"
                      f" | {elapsed:.0f}s")

        n        = len(loader)
        avg_loss = total_loss / n
        acc      = correct / total * 100
        return avg_loss, acc

    def evaluate(self, loader):
        self.model.eval()
        total_loss = 0
        correct    = 0
        total      = 0

        with torch.no_grad():
            for batch in loader:
                ids   = batch["input_ids"].to(
                    self.device)
                mask  = batch["attention_mask"].to(
                    self.device)
                i_lbl = batch["intent_label"].to(
                    self.device)
                e_lbl = batch["entity_labels"].to(
                    self.device)

                i_logits, e_logits = self.model(
                    ids, mask)
                loss, _, _ = self.loss_fn(
                    i_logits, i_lbl,
                    e_logits, e_lbl,
                )

                total_loss += loss.item()
                preds       = torch.argmax(
                    i_logits, dim=-1)
                correct    += (
                    preds == i_lbl).sum().item()
                total      += i_lbl.size(0)

        avg_loss = total_loss / len(loader)
        acc      = correct / total * 100
        return avg_loss, acc

    def run_stage(self, stage_num, stage_name,
                  train_loader, val_loader,
                  epochs):
        print(f"\n{'='*55}")
        print(f"STAGE {stage_num}: {stage_name}")
        print(f"Epochs: {epochs}")
        print(f"{'='*55}")

        best_acc  = 0
        best_path = (self.cfg.save_dir /
                     f"stage{stage_num}_best.pt")

        for epoch in range(1, epochs + 1):
            print(f"\n  Epoch {epoch}/{epochs}")

            # Train
            train_loss, train_acc = \
                self.train_epoch(train_loader, epoch)

            # Validate
            val_loss, val_acc = \
                self.evaluate(val_loader)

            print(f"  Train → "
                  f"loss={train_loss:.4f} "
                  f"acc={train_acc:.1f}%")
            print(f"  Val   → "
                  f"loss={val_loss:.4f} "
                  f"acc={val_acc:.1f}%")

            # Save best model
            if val_acc > best_acc:
                best_acc = val_acc
                self.save(best_path,
                          epoch, val_acc)
                print(f"  ✅ New best: "
                      f"{val_acc:.1f}% saved")

            # Save checkpoint every N epochs
            if epoch % self.cfg.save_every == 0:
                ckpt_path = (
                    self.cfg.save_dir /
                    f"stage{stage_num}"
                    f"_epoch{epoch}.pt"
                )
                self.save(ckpt_path,
                          epoch, val_acc)

            self.history.append({
                "stage":      stage_num,
                "epoch":      epoch,
                "train_loss": train_loss,
                "train_acc":  train_acc,
                "val_loss":   val_loss,
                "val_acc":    val_acc,
            })

        print(f"\n  Stage {stage_num} complete.")
        print(f"  Best val accuracy: {best_acc:.1f}%")
        return best_acc

    def save(self, path, epoch, acc):
        torch.save({
            "epoch":       epoch,
            "model_state": self.model.state_dict(),
            "optim_state": self.optimizer.state_dict(),
            "accuracy":    acc,
            "step":        self.step,
        }, path)

    def load(self, path):
        ckpt = torch.load(path,
                          map_location=self.device)
        self.model.load_state_dict(
            ckpt["model_state"])
        self.optimizer.load_state_dict(
            ckpt["optim_state"])
        self.step = ckpt.get("step", 0)
        print(f"Loaded: {path} "
              f"(acc={ckpt['accuracy']:.1f}%)")


# ══════════════════════════════════════════════════════
# QUICK TEST FUNCTION
# Run this on CPU to verify everything works
# before moving to Colab
# ══════════════════════════════════════════════════════

def quick_test(train_cfg, model_cfg, tokenizer,
               full_data):
    """
    Trains on tiny subset for 2 epochs.
    Just to verify pipeline works end to end.
    Takes 5-10 minutes on CPU.
    """
    print("\n" + "="*55)
    print("QUICK TEST MODE (CPU verification)")
    print("="*55)

    # Use tiny subset
    import random
    random.seed(42)
    tiny = random.sample(full_data,
                         min(200, len(full_data)))
    split    = int(len(tiny) * 0.8)
    train_ex = tiny[:split]
    val_ex   = tiny[split:]

    print(f"Train: {len(train_ex)} examples")
    print(f"Val:   {len(val_ex)} examples")

    train_loader = make_loader(
        train_ex, tokenizer, model_cfg,
        train_cfg, use_noisy=False)
    val_loader   = make_loader(
        val_ex, tokenizer, model_cfg,
        train_cfg, use_noisy=False,
        shuffle=False)

    model   = STM32LLM(model_cfg).to(
        torch.device(train_cfg.device))
    trainer = Trainer(model, train_cfg, model_cfg)

    for epoch in range(1, 3):
        print(f"\nEpoch {epoch}/2")
        train_loss, train_acc = \
            trainer.train_epoch(train_loader, epoch)
        val_loss, val_acc = \
            trainer.evaluate(val_loader)
        print(f"  Train loss={train_loss:.4f} "
              f"acc={train_acc:.1f}%")
        print(f"  Val   loss={val_loss:.4f} "
              f"acc={val_acc:.1f}%")

    print("\n✅ Quick test complete!")
    print("Loss should be decreasing ✅")
    print("Accuracy should be above 10% ✅")
    print("Now run full training on Colab GPU")


# ══════════════════════════════════════════════════════
# FULL CURRICULUM TRAINING
# Run this on Colab GPU
# ══════════════════════════════════════════════════════

def full_training(train_cfg, model_cfg,
                  tokenizer, full_data):
    """
    Complete 4-stage curriculum training.
    Stage 1: Simple clean examples
    Stage 2: Simple clean + noisy
    Stage 3: Complex examples
    Stage 4: Full dataset fine-tune
    """
    print("\n" + "="*55)
    print("FULL CURRICULUM TRAINING")
    print("="*55)

    # ── Split data by type ────────────────────────
    simple  = [x for x in full_data
               if x.get("complexity") == "simple"]
    complex_= [x for x in full_data
               if x.get("complexity") == "complex"]
    clean_s = filter_by_noise(simple, ["clean"])
    noisy_s = filter_by_noise(
        simple, ["light","heavy"])

    print(f"\nData splits:")
    print(f"  Simple total  : {len(simple)}")
    print(f"  Simple clean  : {len(clean_s)}")
    print(f"  Simple noisy  : {len(noisy_s)}")
    print(f"  Complex total : {len(complex_)}")

    # ── Train/val split ───────────────────────────
    import random
    random.seed(42)

    def split_data(data, ratio=0.9):
        random.shuffle(data)
        n = int(len(data) * ratio)
        return data[:n], data[n:]

    # ── Build model ───────────────────────────────
    device  = torch.device(train_cfg.device)
    model   = STM32LLM(model_cfg).to(device)
    trainer = Trainer(model, train_cfg, model_cfg)

    total, _ = model.count_parameters()
    print(f"\nModel: {total:,} parameters")
    print(f"Device: {device}")

    # ══════════════════════════════════════════════
    # STAGE 1: Simple clean only
    # Model learns basic intent mapping
    # ══════════════════════════════════════════════
    train_ex, val_ex = split_data(clean_s)
    train_l = make_loader(
        train_ex, tokenizer, model_cfg,
        train_cfg, use_noisy=False)
    val_l   = make_loader(
        val_ex, tokenizer, model_cfg,
        train_cfg, use_noisy=False,
        shuffle=False)

    acc1 = trainer.run_stage(
        1, "Simple Clean Examples",
        train_l, val_l,
        train_cfg.stage1_epochs)

    # ══════════════════════════════════════════════
    # STAGE 2: Simple clean + noisy
    # Model learns robustness
    # ══════════════════════════════════════════════
    all_simple_ex      = clean_s + noisy_s
    train_ex, val_ex   = split_data(all_simple_ex)
    train_l = make_loader(
        train_ex, tokenizer, model_cfg,
        train_cfg, use_noisy=True)
    val_l   = make_loader(
        val_ex, tokenizer, model_cfg,
        train_cfg, use_noisy=False,
        shuffle=False)

    acc2 = trainer.run_stage(
        2, "Simple Clean + Noisy",
        train_l, val_l,
        train_cfg.stage2_epochs)

    # ══════════════════════════════════════════════
    # STAGE 3: Complex multi-intent
    # Model learns multi-peripheral prompts
    # ══════════════════════════════════════════════
    train_ex, val_ex = split_data(complex_)
    train_l = make_loader(
        train_ex, tokenizer, model_cfg,
        train_cfg, use_noisy=True)
    val_l   = make_loader(
        val_ex, tokenizer, model_cfg,
        train_cfg, use_noisy=False,
        shuffle=False)

    acc3 = trainer.run_stage(
        3, "Complex Multi-Intent",
        train_l, val_l,
        train_cfg.stage3_epochs)

    # ══════════════════════════════════════════════
    # STAGE 4: Full dataset fine-tune
    # Final polishing on everything
    # ══════════════════════════════════════════════
    train_ex, val_ex = split_data(full_data)
    train_l = make_loader(
        train_ex, tokenizer, model_cfg,
        train_cfg, use_noisy=True)
    val_l   = make_loader(
        val_ex, tokenizer, model_cfg,
        train_cfg, use_noisy=False,
        shuffle=False)

    acc4 = trainer.run_stage(
        4, "Full Dataset Fine-tune",
        train_l, val_l,
        train_cfg.stage4_epochs)

    # ── Final summary ─────────────────────────────
    print(f"\n{'='*55}")
    print("TRAINING COMPLETE")
    print(f"{'='*55}")
    print(f"Stage 1 best: {acc1:.1f}%")
    print(f"Stage 2 best: {acc2:.1f}%")
    print(f"Stage 3 best: {acc3:.1f}%")
    print(f"Stage 4 best: {acc4:.1f}%")

    # Save final model
    final_path = train_cfg.save_dir / "final_model.pt"
    trainer.save(final_path, 0, acc4)
    print(f"\nFinal model: {final_path}")

    # Save training history
    hist_path = (train_cfg.save_dir /
                 "training_history.json")
    with open(hist_path, "w") as f:
        json.dump(trainer.history, f, indent=2)
    print(f"History saved: {hist_path}")

    return trainer


# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════

if __name__ == "__main__":

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["test","full"],
        default="test",
        help="test=CPU quick check, full=Colab GPU")
    args = parser.parse_args()

    # Load configs
    train_cfg = TrainConfig()
    model_cfg = STM32Config()
    tok=Tokenizer.from_file(train_cfg.tokenizer_path)
    model_cfg.vocab_size()
    

    # Load tokenizer
    print("\nLoading tokenizer...")
    if not train_cfg.tokenizer_path.exists():
        print(f"ERROR: Tokenizer not found at "
              f"{train_cfg.tokenizer_path}")
        sys.exit(1)
    tokenizer = Tokenizer.from_file(
        str(train_cfg.tokenizer_path))
    print("Tokenizer loaded ✅")

    # Update vocab size from actual tokenizer
    actual_vocab = tokenizer.get_vocab_size()
    model_cfg.vocab_size = actual_vocab
    print(f"Vocab size: {actual_vocab}")

    # Load dataset
    print("\nLoading dataset...")
    data_path = train_cfg.dataset_dir / \
                "dataset_full.json"
    if not data_path.exists():
        print(f"ERROR: Dataset not found at "
              f"{data_path}")
        sys.exit(1)

    full_data = load_json(data_path)
    print(f"Loaded {len(full_data)} examples ✅")

    # Show class distribution
    from collections import Counter
    classes = Counter(
        x.get("data_class","?")
        for x in full_data)
    print("Class distribution:")
    for cls, cnt in classes.most_common():
        print(f"  {cls:20s}: {cnt}")

    # Run selected mode
    if args.mode == "test":
        quick_test(train_cfg, model_cfg,
                   tokenizer, full_data)
    else:
        full_training(train_cfg, model_cfg,
                      tokenizer, full_data)