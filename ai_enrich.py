#!/usr/bin/env python3
"""
WideWeb — AI Enrichment Compatibility Shim
Directs callers to enrich.py (universal AI alt text) and integrations.arena.sync_alt_text.
"""

from enrich import (
    load_env,
    get_gemini_api_key,
    is_placeholder_alt,
    generate_image_alt_text,
    batch_enrich_vault
)

from integrations.arena.sync import get_arena_token
from integrations.arena.sync_alt_text import extract_arena_block_id, push_arena_alt_text
