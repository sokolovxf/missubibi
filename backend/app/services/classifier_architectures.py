"""Keras architectures extracted from the supplied September NN rev9/TR rev8 sources."""

import numpy as np

import tensorflow as tf

from tensorflow.keras import layers, regularizers, Input, Model

from app.services.classifier_features import CATEGORICAL_FEATURES

EMBED_DIM = 32

NUM_HEADS = 4

FF_DIM = 64

NUM_TRANSFORMER_BLOCKS = 2

DROPOUT_RATE = 0.2

CAT_TOKEN_DROPOUT_RATE = 0.15

EMBED_DROPOUT_RATE = 0.10

ATTENTION_KEY_DIM = 16

EMBEDDING_L2 = 1e-5

MLP_L2 = 1e-5

LABEL_SMOOTHING = 0.03

RESIDUAL_HEAD_WIDTH = 128

NUM_RESIDUAL_BLOCKS = 2

def embed_dim_for_vocab(vocab_size, min_dim=8, max_dim=48):
    '''Scale raw embedding width to vocabulary size (small vocab -> small embedding,
    large vocab -> larger embedding), capped to a sane range.'''
    heuristic = int(round(1.6 * (vocab_size ** 0.56)))
    return int(np.clip(heuristic, min_dim, max_dim))

class TransformerBlock(layers.Layer):
    '''Multi-Head Self-Attention block with residual connections & Feed-Forward network,
    following the standard Transformer encoder design.'''

    def __init__(self, embed_dim, num_heads, ff_dim, dropout_rate=0.1, key_dim=None, **kwargs):
        super().__init__(**kwargs)
        # Rev 5: key_dim is now an explicit, independently-tunable hyperparameter rather
        # than being forced to embed_dim // num_heads. That old coupling meant NUM_HEADS
        # could only be changed in ways that evenly divide EMBED_DIM, and silently shrank
        # each head's projection as NUM_HEADS went up. Decoupling lets you, e.g., raise
        # NUM_HEADS for more diverse attention patterns without starving each head's
        # representational capacity. Falls back to the old behavior if key_dim is omitted,
        # so this is a backward-compatible default.
        if key_dim is None:
            key_dim = embed_dim // num_heads
        self.att = layers.MultiHeadAttention(num_heads=num_heads, key_dim=key_dim)
        self.ffn = tf.keras.Sequential([
            layers.Dense(ff_dim, activation="gelu"),
            layers.Dense(embed_dim),
        ])
        self.layernorm1 = layers.LayerNormalization(epsilon=1e-6)
        self.layernorm2 = layers.LayerNormalization(epsilon=1e-6)
        self.dropout1 = layers.Dropout(dropout_rate)
        self.dropout2 = layers.Dropout(dropout_rate)

    def call(self, inputs, training=False):
        attn_output = self.att(inputs, inputs)
        attn_output = self.dropout1(attn_output, training=training)
        out1 = self.layernorm1(inputs + attn_output)

        ffn_output = self.ffn(out1)
        ffn_output = self.dropout2(ffn_output, training=training)
        return self.layernorm2(out1 + ffn_output)

class ResidualMLPBlock(layers.Layer):
    '''Pre-activation residual block: x + Dropout(Dense(GELU(LayerNorm(x)))).

    Rev 4 addition. Operates on a fixed-width vector (not a token sequence), used in
    the fusion head after the categorical tokens and numeric branch are concatenated.
    Because the skip connection carries the input straight through, stacking several
    of these is safe from vanishing gradients in a way a plain Dense-Dense-Dense stack
    is not.
    '''

    def __init__(self, width, dropout_rate=0.2, l2=1e-5, **kwargs):
        super().__init__(**kwargs)
        self.norm = layers.LayerNormalization(epsilon=1e-6)
        self.dense1 = layers.Dense(width, activation="gelu", kernel_regularizer=regularizers.l2(l2))
        self.dense2 = layers.Dense(width, kernel_regularizer=regularizers.l2(l2))
        self.dropout = layers.Dropout(dropout_rate)

    def call(self, inputs, training=False):
        x = self.norm(inputs)
        x = self.dense1(x)
        x = self.dense2(x)
        x = self.dropout(x, training=training)
        return inputs + x

def build_tab_transformer(numeric_dim):
    categorical_inputs = {}
    embedded_tokens = []

    for col in CATEGORICAL_FEATURES:
        # Rev 6: "string" (Keras 3's canonical dtype name) rather than the tf.string DType
        # object -- belt-and-suspenders against Keras 3 dtype-policy resolution quirks.
        inp = Input(shape=(1,), name=col, dtype="string")
        categorical_inputs[col] = inp

        lookup = layers.StringLookup(vocabulary=vocabularies[col], mask_token=None, oov_token="[UNK]")
        encoded = lookup(inp)
        vocab_size = lookup.vocabulary_size()
        raw_dim = embed_dim_for_vocab(vocab_size)

        embedding = layers.Embedding(
            input_dim=vocab_size, output_dim=raw_dim, name=f"{col}_embedding",
            embeddings_regularizer=regularizers.l2(EMBEDDING_L2),
        )
        token = embedding(encoded)                                      # (batch, 1, raw_dim)
        # Rev 5: per-feature embedding dropout. Independently zeroes out an entire
        # feature's embedding vector for a given training row (distinct from the existing
        # SpatialDropout1D below, which drops whole token *positions* consistently across
        # a feature map once the tokens are already concatenated). This is the classic
        # "embedding dropout" regularizer -- it forces the transformer blocks to not
        # over-rely on any single categorical column always being present/informative,
        # which is exactly the item-identity-memorization risk flagged in Section 24.
        token = layers.Dropout(EMBED_DROPOUT_RATE, name=f"{col}_embed_dropout")(token)
        token = layers.Dense(EMBED_DIM, name=f"{col}_proj")(token)       # project to shared width
        embedded_tokens.append(token)

    cat_sequence = layers.Concatenate(axis=1, name="categorical_token_sequence")(embedded_tokens)
    cat_sequence = layers.SpatialDropout1D(CAT_TOKEN_DROPOUT_RATE, name="categorical_token_dropout")(cat_sequence)

    x = cat_sequence
    for i in range(NUM_TRANSFORMER_BLOCKS):
        x = TransformerBlock(EMBED_DIM, NUM_HEADS, FF_DIM, DROPOUT_RATE,
                              key_dim=ATTENTION_KEY_DIM, name=f"transformer_block_{i}")(x)

    flat_cat = layers.Flatten(name="categorical_flatten")(x)
    cat_representation = layers.Dense(64, activation="gelu", name="categorical_projection",
                                       kernel_regularizer=regularizers.l2(MLP_L2))(flat_cat)
    cat_representation = layers.Dropout(DROPOUT_RATE)(cat_representation)

    numeric_input = Input(shape=(numeric_dim,), name="numeric_input")
    n = layers.Dense(64, activation="gelu", kernel_regularizer=regularizers.l2(MLP_L2))(numeric_input)
    n = layers.BatchNormalization()(n)
    n = layers.Dropout(DROPOUT_RATE)(n)
    numeric_representation = layers.Dense(32, activation="gelu", name="numeric_embedding",
                                           kernel_regularizer=regularizers.l2(MLP_L2))(n)

    combined = layers.Concatenate(name="fused_representation")([cat_representation, numeric_representation])

    # Rev 4: residual MLP head instead of a plain Dense-Dense stack.
    h = layers.Dense(RESIDUAL_HEAD_WIDTH, activation="gelu",
                      kernel_regularizer=regularizers.l2(MLP_L2), name="head_projection")(combined)
    for i in range(NUM_RESIDUAL_BLOCKS):
        h = ResidualMLPBlock(RESIDUAL_HEAD_WIDTH, DROPOUT_RATE, MLP_L2, name=f"residual_block_{i}")(h)
    h = layers.Dense(64, activation="gelu", kernel_regularizer=regularizers.l2(MLP_L2))(h)
    h = layers.Dropout(DROPOUT_RATE)(h)
    output = layers.Dense(1, activation="sigmoid", name="output")(h)

    all_inputs = {**categorical_inputs, "numeric_input": numeric_input}
    model = Model(inputs=all_inputs, outputs=output, name="Tabular_Transformer_Residual")
    return model

def build_binary_model(n_numeric, cat_vocabs, units1=256, units2=256, units3=128,
                       drop1=0.2, drop2=0.25, drop3=0.2):
    num_input = layers.Input(shape=(n_numeric,), name='numeric_input')
    num_x = layers.Dense(units1, activation='relu')(num_input)
    num_x = layers.BatchNormalization()(num_x)
    num_x = layers.Dropout(drop1)(num_x)

    cat_inputs, cat_embeds = [], []
    for name, vocab in cat_vocabs.items():
        # FIX 6: StringLookup with num_oov_indices=1 emits indices 0..len(vocab), i.e.
        # len(vocab)+1 distinct values in total. vocab_size already counts that OOV slot, so
        # input_dim=vocab_size is exactly right; the old vocab_size+1 reserved a second,
        # permanently unused embedding row.
        vocab_size = len(vocab) + 1
        inp = layers.Input(shape=(1,), dtype=tf.string, name=f'{name}_input')
        lookup = layers.StringLookup(vocabulary=vocab, num_oov_indices=1)(inp)
        emb = layers.Embedding(input_dim=vocab_size, output_dim=16)(lookup)
        cat_inputs.append(inp)
        cat_embeds.append(layers.Flatten()(emb))

    combined = layers.Concatenate()([num_x] + cat_embeds)
    x = layers.Dense(units2, activation='relu')(combined)
    x = layers.BatchNormalization()(x)
    x = layers.Dropout(drop2)(x)
    x = layers.Dense(units3, activation='relu')(x)
    x = layers.BatchNormalization()(x)
    x = layers.Dropout(drop3)(x)

    return [num_input] + cat_inputs, x

def build_model(kind, n_numeric, categories):
    global vocabularies
    vocabularies = categories
    if kind == 'tr':
        return build_tab_transformer(n_numeric)
    inputs, trunk = build_binary_model(n_numeric, categories)
    return Model(inputs=inputs, outputs=layers.Dense(1, activation='sigmoid', name='demand_binary')(trunk))
