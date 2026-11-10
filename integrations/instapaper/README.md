# Instapaper Integration for WebTack

Connect your [Instapaper](https://www.instapaper.com/) account to WebTack to automatically ingest your unread reading list as durable offline `article` or `bookmark` atoms.

---

## 1. Setup & Credentials

Add your Instapaper Full API OAuth bearer token to `.env`:

```bash
INSTAPAPER_ACCESS_TOKEN="your_instapaper_oauth_token"
```

---

## 2. Usage

Pull your unread bookmarks into WebTack:

```bash
python3 integrations/instapaper/sync.py --limit 25
```

WebTack will:
* Check for duplicates against existing atoms in SQLite.
* Fetch Instapaper's pre-parsed readability text (or fall back to Trafilatura).
* Store longform articles with `article.md` offline bodies in `vault/atoms/YYYY/MM/<id>/`.
* Update checkpoint tracking in `vault/.sync_state.json`.
