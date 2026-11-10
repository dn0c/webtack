# Google Cloud Storage (GCS) Integration for WebTack

Sync your public curated atoms and media assets to a Google Cloud Storage bucket to host public digital gardens (such as `drewshannon.net/garden`).

---

## 1. Setup & Credentials

Authenticate with Google Cloud SDK or provide service account credentials:

```bash
# Authenticate via gcloud CLI
gcloud auth application-default login

# Or set your default bucket in .env
WEBTACK_GCS_BUCKET="your-public-bucket-name"
```

---

## 2. Usage

Sync your public atom manifest and media assets:

```bash
# Sync all public images and upload curation_public.json
python3 integrations/gcs/sync.py --bucket your-bucket-name

# Or upload only the JSON manifest without re-syncing images
python3 integrations/gcs/sync.py --manifest-only
```
