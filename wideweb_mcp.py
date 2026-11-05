#!/usr/bin/env python3
"""
WideWeb Model Context Protocol (MCP) Server.
Enables AI tools (Claude Desktop, Antigravity, Cursor, ChatGPT) to search, read,
and curate atoms directly from the WideWeb vault.
"""

import os
import sys
import json
import sqlite3
from pathlib import Path
from mcp.server.mcpserver import MCPServer

# Initialize MCP server
app = MCPServer("WideWeb Vault")


def get_vault_dir() -> Path:
    env_dir = os.environ.get("WIDEWEB_VAULT")
    if env_dir:
        return Path(env_dir).resolve()
    return Path(__file__).resolve().parent / "vault"


def get_db():
    vault_dir = get_vault_dir()
    db_path = vault_dir / "vault.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn, vault_dir


@app.tool()
def search_vault(query: str = "", kind: str = "", tag: str = "", limit: int = 15) -> list[dict]:
    """Search the WideWeb curation vault by keyword, semantic title, spoken dialogue, article text, notes, or tags."""
    conn, vault_dir = get_db()
    sql = "SELECT id, kind, created_at, atom_title, author, source_url, destination_url, tags, notes, text_content FROM atoms WHERE 1=1"
    params = []
    if query:
        sql += " AND (atom_title LIKE ? OR text_content LIKE ? OR notes LIKE ? OR tags LIKE ?)"
        q_wild = f"%{query}%"
        params.extend([q_wild, q_wild, q_wild, q_wild])
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    if tag:
        sql += " AND tags LIKE ?"
        params.append(f"%{tag}%")
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    results = []
    for r in rows:
        results.append({
            "id": r["id"],
            "kind": r["kind"],
            "title": r["atom_title"],
            "author": r["author"],
            "url": r["source_url"] or r["destination_url"],
            "date": r["created_at"][:10],
            "tags": json.loads(r["tags"]) if r["tags"] else [],
            "notes": r["notes"],
            "excerpt": r["text_content"][:300] if r["text_content"] else None
        })
    return results


@app.tool()
def get_atom(atom_id: str) -> dict:
    """Retrieve full details of an atom by ID, including its full payload body or transcript dialogue."""
    conn, vault_dir = get_db()
    row = conn.execute("SELECT * FROM atoms WHERE id = ?", (atom_id,)).fetchone()
    if not row:
        return {"error": f"Atom not found: {atom_id}"}

    doc = json.loads(row["raw_json"])
    created_at = row["created_at"]
    atom_folder = vault_dir / "atoms" / created_at[:4] / created_at[5:7] / atom_id

    content = None
    if row["kind"] == "article":
        art_path = atom_folder / "article.md"
        if art_path.exists():
            content = art_path.read_text(encoding="utf-8")
    elif row["kind"] == "video":
        trans_path = atom_folder / "transcript.txt"
        if trans_path.exists():
            content = trans_path.read_text(encoding="utf-8")
    elif row["kind"] == "note":
        note_path = atom_folder / "note.md"
        if not note_path.exists():
            note_path = atom_folder / "note.txt"
        if note_path.exists():
            content = note_path.read_text(encoding="utf-8")

    if not content and row["text_content"]:
        content = row["text_content"]

    return {
        "id": row["id"],
        "kind": row["kind"],
        "title": row["atom_title"],
        "author": row["author"],
        "url": row["destination_url"] or row["source_url"],
        "created_at": row["created_at"],
        "tags": json.loads(row["tags"]) if row["tags"] else [],
        "notes": row["notes"],
        "content_body": content,
        "folder_path": str(atom_folder),
        "raw_json": doc
    }


@app.tool()
def get_transcript(atom_id: str) -> str:
    """Get the full spoken timestamped transcript dialogue for a video atom."""
    atom = get_atom(atom_id)
    if "error" in atom:
        return atom["error"]
    return atom.get("content_body") or "No transcript available for this atom."


@app.tool()
def get_article(atom_id: str) -> str:
    """Get the full offline Markdown body for an article atom."""
    atom = get_atom(atom_id)
    if "error" in atom:
        return atom["error"]
    return atom.get("content_body") or "No article text available for this atom."


@app.tool()
def list_recent(limit: int = 15, kind: str = "") -> list[dict]:
    """List the most recently captured atoms in the WideWeb vault."""
    return search_vault(query="", kind=kind, limit=limit)


@app.tool()
def save_note(text: str, title: str = "", tags: str = "") -> dict:
    """Save a personal note or memo directly into the WideWeb vault."""
    script_dir = str(Path(__file__).resolve().parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    import curate
    import types
    vault_dir = get_vault_dir()
    args = types.SimpleNamespace(
        text=text,
        title=title or None,
        tags=tags or None,
        collection=None,
        favorite=False,
        vault=str(vault_dir),
        capture_method="mcp"
    )
    doc = curate.cmd_note(args)
    return {"success": True, "atom_id": doc["id"], "title": doc["curation"]["atom_title"]}


@app.tool()
def save_bookmark(url: str, title: str = "", tags: str = "") -> dict:
    """Save a bookmark pointer into the WideWeb vault."""
    script_dir = str(Path(__file__).resolve().parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    import curate
    import types
    vault_dir = get_vault_dir()
    args = types.SimpleNamespace(
        url=url,
        title=title or None,
        notes=None,
        tags=tags or None,
        collection=None,
        image_url=None,
        quote=None,
        favorite=False,
        vault=str(vault_dir),
        target_kind="bookmark",
        capture_method="mcp"
    )
    doc = curate.cmd_save_link(args)
    return {"success": True, "atom_id": doc["id"], "title": doc["curation"]["atom_title"]}


def main():
    """Run the WideWeb MCP server via stdio transport."""
    app.run()


if __name__ == "__main__":
    main()
