import torch
import torch.nn as nn
import torch.nn.functional as F
import math
import json
from pathlib import Path
from tokenizers import Tokenizer

# ══════════════════════════════════════════════════════
# MODEL CONFIG
# All hyperparameters in one place
# Easy to change for experiments
# ══════════════════════════════════════════════════════

class STM32Config:
    def __init__(self):

        # ── Tokenizer ─────────────────────────────────
        self.vocab_size     = 4000
        self.pad_token_id   = 0
        self.unk_token_id   = 1
        self.bos_token_id   = 2
        self.eos_token_id   = 3
        self.sep_token_id   = 4

        # ── Model dimensions ──────────────────────────
        self.embed_dim      = 256
        self.num_heads      = 4
        self.num_layers     = 4
        self.ffn_dim        = 512
        self.max_seq_len    = 64
        self.dropout        = 0.1

        # ── Intent classes ────────────────────────────
        self.intent_classes = [
            "GPIO_OUTPUT",
            "GPIO_INPUT",
            "GPIO_TOGGLE",
            "GPIO_READ",
            "UART_INIT",
            "UART_TRANSMIT",
            "UART_RECEIVE",
            "TIMER_DELAY",
            "TIMER_PWM",
            "RCC_ENABLE",
            "AMBIGUOUS",
            "INVALID",
        ]
        self.num_intents    = len(self.intent_classes)
        self.intent2id      = {
            c: i for i, c in
            enumerate(self.intent_classes)
        }
        self.id2intent      = {
            i: c for c, i in
            self.intent2id.items()
        }

        # ── Entity tags (NER) ─────────────────────────
        # BIO tagging scheme:
        # B = beginning of entity
        # I = inside entity
        # O = outside (not an entity)
        self.entity_tags = [
            "O",           # not an entity
            "B-PORT",      # beginning of port (A,B,C)
            "B-PIN",       # beginning of pin number
            "B-SPEED",     # 50MHz, 10MHz, 2MHz
            "B-MODE",      # output_push_pull etc
            "B-UART",      # USART1, USART2, USART3
            "B-BAUDRATE",  # 9600, 115200 etc
            "B-TIMER",     # TIM2, TIM3, TIM4
            "B-DELAY",     # 500ms, 100ms etc
            "B-DUTY",      # 25%, 50%, 75%
            "B-CHANNEL",   # CH1, CH2, CH3, CH4
            "I-PORT",
            "I-PIN",
            "I-SPEED",
            "I-MODE",
            "I-UART",
            "I-BAUDRATE",
            "I-TIMER",
            "I-DELAY",
            "I-DUTY",
            "I-CHANNEL",
        ]
        self.num_entity_tags = len(self.entity_tags)
        self.tag2id = {
            t: i for i, t in
            enumerate(self.entity_tags)
        }
        self.id2tag = {
            i: t for t, i in
            self.tag2id.items()
        }
        

# ══════════════════════════════════════════════════════
# POSITIONAL ENCODING
# Tells model WHERE each token is in sequence
# Without this model treats all positions same
# ══════════════════════════════════════════════════════

class PositionalEncoding(nn.Module):
    def __init__(self, embed_dim, max_seq_len,
                 dropout=0.1):
        super().__init__()
        self.dropout = nn.Dropout(dropout)

        # Create positional encoding matrix
        pe  = torch.zeros(max_seq_len, embed_dim)
        pos = torch.arange(
            0, max_seq_len).unsqueeze(1).float()
        div = torch.exp(
            torch.arange(0, embed_dim, 2).float() *
            -(math.log(10000.0) / embed_dim)
        )

        # Even positions: sin, Odd positions: cos
        pe[:, 0::2] = torch.sin(pos * div)
        pe[:, 1::2] = torch.cos(pos * div)

        # Shape: (1, max_seq_len, embed_dim)
        pe = pe.unsqueeze(0)
        # Register as buffer (not a parameter)
        self.register_buffer('pe', pe)

    def forward(self, x):
        # x shape: (batch, seq_len, embed_dim)
        x = x + self.pe[:, :x.size(1), :]
        return self.dropout(x)
    

# ══════════════════════════════════════════════════════
# MULTI HEAD SELF ATTENTION
# Core of transformer
# Each head learns different relationships
# ══════════════════════════════════════════════════════

class MultiHeadAttention(nn.Module):
    def __init__(self, embed_dim, num_heads,
                 dropout=0.1):
        super().__init__()
        assert embed_dim % num_heads == 0, \
            "embed_dim must be divisible by num_heads"

        self.embed_dim  = embed_dim
        self.num_heads  = num_heads
        self.head_dim   = embed_dim // num_heads
        self.scale      = math.sqrt(self.head_dim)

        # Single matrix for Q, K, V projections
        self.qkv        = nn.Linear(
            embed_dim, 3 * embed_dim)
        self.out_proj   = nn.Linear(
            embed_dim, embed_dim)
        self.dropout    = nn.Dropout(dropout)

    def forward(self, x, mask=None):
        B, T, C = x.shape  # batch, seq, embed

        # Project to Q, K, V
        qkv = self.qkv(x)
        qkv = qkv.reshape(B, T, 3,
                          self.num_heads,
                          self.head_dim)
        qkv = qkv.permute(2, 0, 3, 1, 4)
        q, k, v = qkv[0], qkv[1], qkv[2]

        # Scaled dot product attention
        scores = torch.matmul(
            q, k.transpose(-2, -1)) / self.scale

        # Apply padding mask if provided
        if mask is not None:
            # mask: (B, T) → (B, 1, 1, T)
            mask = mask.unsqueeze(1).unsqueeze(2)
            scores = scores.masked_fill(
                mask == 0, float('-inf'))

        attn   = F.softmax(scores, dim=-1)
        attn   = self.dropout(attn)

        # Weighted sum of values
        out    = torch.matmul(attn, v)
        out    = out.transpose(1, 2).contiguous()
        out    = out.reshape(B, T, C)
        return self.out_proj(out)


# ══════════════════════════════════════════════════════
# FEED FORWARD NETWORK
# Applied after attention
# Two linear layers with GELU activation
# ══════════════════════════════════════════════════════

class FeedForward(nn.Module):
    def __init__(self, embed_dim, ffn_dim,
                 dropout=0.1):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(embed_dim, ffn_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(ffn_dim, embed_dim),
            nn.Dropout(dropout),
        )

    def forward(self, x):
        return self.net(x)


# ══════════════════════════════════════════════════════
# TRANSFORMER BLOCK
# One complete transformer layer:
#   Attention → Add+Norm → FFN → Add+Norm
# ══════════════════════════════════════════════════════

class TransformerBlock(nn.Module):
    def __init__(self, embed_dim, num_heads,
                 ffn_dim, dropout=0.1):
        super().__init__()
        self.attention  = MultiHeadAttention(
            embed_dim, num_heads, dropout)
        self.ffn        = FeedForward(
            embed_dim, ffn_dim, dropout)
        self.norm1      = nn.LayerNorm(embed_dim)
        self.norm2      = nn.LayerNorm(embed_dim)
        self.dropout    = nn.Dropout(dropout)

    def forward(self, x, mask=None):
        # Pre-norm architecture (more stable training)
        # Attention with residual connection
        attn_out = self.attention(
            self.norm1(x), mask)
        x = x + self.dropout(attn_out)

        # FFN with residual connection
        ffn_out  = self.ffn(self.norm2(x))
        x = x + self.dropout(ffn_out)
        return x
    
# ══════════════════════════════════════════════════════
# STM32 LLM — MAIN MODEL
# Encoder-only transformer with dual output heads:
#   1. Intent Head  → what peripheral/action
#   2. Entity Head  → what parameters
# ══════════════════════════════════════════════════════

class STM32LLM(nn.Module):
    def __init__(self, config: STM32Config):
        super().__init__()
        self.config = config

        # ── Input layers ──────────────────────────────
        self.token_embedding = nn.Embedding(
            config.vocab_size,
            config.embed_dim,
            padding_idx=config.pad_token_id,
        )
        self.pos_encoding = PositionalEncoding(
            config.embed_dim,
            config.max_seq_len,
            config.dropout,
        )

        # ── Transformer blocks ────────────────────────
        self.layers = nn.ModuleList([
            TransformerBlock(
                config.embed_dim,
                config.num_heads,
                config.ffn_dim,
                config.dropout,
            )
            for _ in range(config.num_layers)
        ])

        self.norm = nn.LayerNorm(config.embed_dim)

        # ── Output Head 1: Intent Classification ──────
        # Uses [CLS] token (first token = BOS)
        # Classifies entire sequence into one intent
        self.intent_head = nn.Sequential(
            nn.Linear(config.embed_dim,
                      config.embed_dim // 2),
            nn.GELU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.embed_dim // 2,
                      config.num_intents),
        )

        # ── Output Head 2: Entity Extraction (NER) ────
        # Uses all token representations
        # Tags each token with entity label
        self.entity_head = nn.Sequential(
            nn.Linear(config.embed_dim,
                      config.embed_dim // 2),
            nn.GELU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.embed_dim // 2,
                      config.num_entity_tags),
        )

        # Initialize weights properly
        self._init_weights()

    def _init_weights(self):
        """
        Initialize weights for stable training.
        Xavier for linear layers.
        Normal for embeddings.
        """
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.xavier_uniform_(
                    module.weight)
                if module.bias is not None:
                    nn.init.zeros_(module.bias)
            elif isinstance(module, nn.Embedding):
                nn.init.normal_(
                    module.weight, mean=0,
                    std=0.02)
                if module.padding_idx is not None:
                    module.weight.data[
                        module.padding_idx
                    ].zero_()

    def forward(self, input_ids,
                attention_mask=None):
        """
        input_ids:      (batch, seq_len)
        attention_mask: (batch, seq_len)
                        1=real token, 0=padding

        Returns:
          intent_logits: (batch, num_intents)
          entity_logits: (batch, seq_len, num_tags)
        """
        B, T = input_ids.shape

        # ── Embeddings ────────────────────────────────
        x = self.token_embedding(input_ids)
        # Scale embeddings (standard practice)
        x = x * math.sqrt(self.config.embed_dim)
        x = self.pos_encoding(x)

        # ── Transformer layers ────────────────────────
        for layer in self.layers:
            x = layer(x, attention_mask)

        x = self.norm(x)

        # ── Intent head ───────────────────────────────
        # Use first token (BOS/CLS position)
        cls_repr       = x[:, 0, :]
        intent_logits  = self.intent_head(cls_repr)

        # ── Entity head ───────────────────────────────
        # Use all token representations
        entity_logits  = self.entity_head(x)

        return intent_logits, entity_logits

    def predict(self, input_ids,
                attention_mask=None):
        """
        Inference mode — returns class indices.
        No gradient computation needed.
        """
        self.eval()
        with torch.no_grad():
            intent_logits, entity_logits = \
                self.forward(
                    input_ids, attention_mask)

            intent_pred = torch.argmax(
                intent_logits, dim=-1)
            entity_pred = torch.argmax(
                entity_logits, dim=-1)

        return intent_pred, entity_pred

    def count_parameters(self):
        total     = sum(p.numel()
                       for p in self.parameters())
        trainable = sum(
            p.numel() for p in self.parameters()
            if p.requires_grad)
        return total, trainable
    

# ══════════════════════════════════════════════════════
# COMBINED LOSS FUNCTION
# Trains both heads simultaneously
# Weighted sum of intent loss + entity loss
# ══════════════════════════════════════════════════════

class STM32Loss(nn.Module):
    def __init__(self, config,
                intent_weight=1.0,
                entity_weight=0.5,
                intent_weights=None):

        super().__init__()

        self.intent_weight  = intent_weight
        self.entity_weight  = entity_weight

        if intent_weights is not None:
            self.intent_loss_fn = nn.CrossEntropyLoss(
                weight=intent_weights
            )
        else:
            self.intent_loss_fn = nn.CrossEntropyLoss()

        self.entity_loss_fn = nn.CrossEntropyLoss(
            ignore_index=-100
        )

    def forward(self,
                intent_logits, intent_labels,
                entity_logits, entity_labels):
        """
        intent_logits:  (B, num_intents)
        intent_labels:  (B,)
        entity_logits:  (B, T, num_tags)
        entity_labels:  (B, T)  -100 for padding
        """
        # Intent loss
        intent_loss = self.intent_loss_fn(
            intent_logits, intent_labels)

        # Entity loss — reshape for CrossEntropy
        B, T, num_tags = entity_logits.shape
        entity_loss = self.entity_loss_fn(
            entity_logits.reshape(B * T, num_tags),
            entity_labels.reshape(B * T),
        )

        # Combined weighted loss
        total_loss = (
            self.intent_weight  * intent_loss +
            self.entity_weight  * entity_loss
        )

        return total_loss, intent_loss, entity_loss
    
    
# ══════════════════════════════════════════════════════
# VERIFY MODEL WORKS CORRECTLY
# ══════════════════════════════════════════════════════

def verify_model(config):
    print("="*55)
    print("STM32 MODEL VERIFICATION")
    print("="*55)

    device = torch.device(
        "cuda" if torch.cuda.is_available()
        else "cpu")
    print(f"\nDevice: {device}")

    # Build model
    model = STM32LLM(config).to(device)
    total, trainable = model.count_parameters()
    print(f"Total params    : {total:,}")
    print(f"Trainable params: {trainable:,}")
    print(f"Model size      : "
          f"~{total*4/1024/1024:.1f} MB")

    # Test forward pass with fake data
    B   = 4     # batch size
    T   = 32    # sequence length

    # Fake token IDs (random)
    input_ids = torch.randint(
        0, config.vocab_size,
        (B, T)).to(device)

    # Fake attention mask
    # (last 8 tokens are padding)
    attention_mask = torch.ones(B, T).to(device)
    attention_mask[:, 24:] = 0

    print(f"\nTest input shape: {input_ids.shape}")

    # Forward pass
    model.eval()
    with torch.no_grad():
        intent_logits, entity_logits = \
            model(input_ids, attention_mask)

    print(f"Intent logits   : "
          f"{intent_logits.shape}")
    print(f"Entity logits   : "
          f"{entity_logits.shape}")

    # Verify output shapes
    assert intent_logits.shape == \
        (B, config.num_intents), \
        "Intent shape wrong!"
    assert entity_logits.shape == \
        (B, T, config.num_entity_tags), \
        "Entity shape wrong!"

    # Test prediction
    intent_pred, entity_pred = \
        model.predict(input_ids, attention_mask)
    print(f"\nSample intent predictions:")
    for i in range(B):
        intent_name = config.id2intent[
            intent_pred[i].item()]
        print(f"  Example {i+1}: {intent_name}")

    # Test loss function
    loss_fn = STM32Loss(config)
    intent_labels = torch.randint(
        0, config.num_intents, (B,)).to(device)
    entity_labels = torch.randint(
        0, config.num_entity_tags, (B, T)).to(device)
    # Mask padding tokens in entity labels
    entity_labels[:, 24:] = -100

    total_loss, i_loss, e_loss = loss_fn(
        intent_logits, intent_labels,
        entity_logits, entity_labels,
    )
    print(f"\nLoss verification:")
    print(f"  Total loss  : {total_loss.item():.4f}")
    print(f"  Intent loss : {i_loss.item():.4f}")
    print(f"  Entity loss : {e_loss.item():.4f}")

    # Test with real tokenizer
    tok_path = (Path(__file__).parent.parent /
                "tokenizer" / "stm32_tokenizer.json")
    if tok_path.exists():
        print(f"\nTokenizer integration test:")
        tok = Tokenizer.from_file(str(tok_path))

        test_prompts = [
            "configure PA5 as output push pull 50MHz",
            "initialize USART1 at 115200 baud",
            "generate 500ms delay using TIM3",
        ]
        for p in test_prompts:
            enc = tok.encode(p)
            ids = enc.ids[:config.max_seq_len]
            # Pad to max_seq_len
            pad = config.pad_token_id
            mask = [1]*len(ids) + \
                   [0]*(config.max_seq_len-len(ids))
            ids  = ids + \
                   [pad]*(config.max_seq_len-len(ids))

            t_ids  = torch.tensor(
                [ids]).to(device)
            t_mask = torch.tensor(
                [mask]).to(device)

            i_pred, e_pred = model.predict(
                t_ids, t_mask)
            intent_name = config.id2intent[
                i_pred[0].item()]

            print(f"\n  Prompt : {p}")
            print(f"  Tokens : {len(enc.ids)}")
            print(f"  Predicted intent: "
                  f"{intent_name} "
                  f"(random — not trained yet)")
    else:
        print(f"\n  Tokenizer not found at {tok_path}")
        print(f"  Skipping integration test")

    print(f"\n{'='*55}")
    print("✅ MODEL ARCHITECTURE VERIFIED")
    print(f"{'='*55}")
    print("\nAll shapes correct.")
    print("Ready for Step 6 Training.")
    return model


# ══════════════════════════════════════════════════════
# SAVE AND LOAD UTILITIES
# Used between Step 5 and Step 6
# ══════════════════════════════════════════════════════

def save_model(model, config, path):
    torch.save({
        "model_state": model.state_dict(),
        "config":      config.__dict__,
    }, path)
    print(f"Model saved: {path}")


def load_model(path, device="cpu"):
    checkpoint = torch.load(path,
                            map_location=device)
    config     = STM32Config()
    config.__dict__.update(checkpoint["config"])
    model      = STM32LLM(config)
    model.load_state_dict(
        checkpoint["model_state"])
    model.to(device)
    print(f"Model loaded: {path}")
    return model, config


# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════

if __name__ == "__main__":
    config = STM32Config()

    print("CONFIG SUMMARY")
    print(f"  vocab_size    : {config.vocab_size}")
    print(f"  embed_dim     : {config.embed_dim}")
    print(f"  num_heads     : {config.num_heads}")
    print(f"  num_layers    : {config.num_layers}")
    print(f"  ffn_dim       : {config.ffn_dim}")
    print(f"  max_seq_len   : {config.max_seq_len}")
    print(f"  num_intents   : {config.num_intents}")
    print(f"  num_entity_tags:{config.num_entity_tags}")
    print(f"  Intent classes: "
          f"{config.intent_classes}")

    model = verify_model(config)
    
