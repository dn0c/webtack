#!/usr/bin/env python3
"""
Webtack — Build Sample Demo Vault
Constructs a pristine, self-contained fixtures/demo_vault directory with
sample atoms representing the canonical kinds (article, bookmark, video, quote, note, image).
"""

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import blurhash

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_VAULT = REPO_ROOT / "fixtures" / "demo_vault"
ATOMS_DIR = DEMO_VAULT / "atoms" / "2026" / "11"


def create_gradient_image(path: Path, title: str, subtitle: str, bg_color1: tuple, bg_color2: tuple, text_color: tuple = (255, 255, 255)) -> dict:
    """Create an aesthetic 800x450 card image with Pillow, compute blurhash and palette."""
    w, h = 800, 450
    img = Image.new("RGB", (w, h), bg_color1)
    draw = ImageDraw.Draw(img)

    # Vertical gradient
    for y in range(h):
        r = int(bg_color1[0] + (bg_color2[0] - bg_color1[0]) * (y / h))
        g = int(bg_color1[1] + (bg_color2[1] - bg_color1[1]) * (y / h))
        b = int(bg_color1[2] + (bg_color2[2] - bg_color1[2]) * (y / h))
        draw.line([(0, y), (w, y)], fill=(r, g, b))

    # Decorative border & inner box
    draw.rectangle([20, 20, w - 20, h - 20], outline=(text_color[0], text_color[1], text_color[2], 60), width=2)
    draw.rectangle([40, 40, w - 40, h - 40], outline=(text_color[0], text_color[1], text_color[2], 40), width=1)

    # Simple clean text placement
    draw.text((60, 160), title, fill=text_color)
    draw.text((60, 240), subtitle, fill=(text_color[0], text_color[1], text_color[2]))

    # Watermark
    draw.text((60, h - 70), "WEBTACK // SPECIMEN", fill=(text_color[0], text_color[1], text_color[2]))

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="JPEG", quality=85)

    # Compute blurhash
    small = img.resize((32, 18))
    bh = blurhash.encode(small, x_components=4, y_components=3)

    hex_c1 = f"#{bg_color1[0]:02x}{bg_color1[1]:02x}{bg_color1[2]:02x}"
    hex_c2 = f"#{bg_color2[0]:02x}{bg_color2[1]:02x}{bg_color2[2]:02x}"

    return {
        "file": path.name,
        "relative_path": path.name,
        "mime_type": "image/jpeg",
        "dimensions": {"width": w, "height": h},
        "aspect_ratio": round(w / h, 4),
        "blurhash": bh,
        "color_palette": [hex_c1, hex_c2],
        "alt_text": f"Preview card for {title}"
    }


def build_demo_vault():
    print(f"🧹 Clearing existing demo vault at {DEMO_VAULT}...")
    if DEMO_VAULT.exists():
        shutil.rmtree(DEMO_VAULT)
    ATOMS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Article: "As We May Think"
    art_id = "atm_20261108200100_demoart"
    art_dir = ATOMS_DIR / art_id
    art_dir.mkdir(parents=True, exist_ok=True)
    art_cover = create_gradient_image(
        art_dir / "cover.jpg",
        "As We May Think",
        "Vannevar Bush (The Atlantic, 1945)",
        (30, 41, 59), (15, 23, 42)
    )
    art_md_content = """# As We May Think

*By Vannevar Bush — The Atlantic Monthly, July 1945*

This has not been a scientist's war; it has been a war in which all have had a part. The scientists, burying their old professional competition in the demand of a common cause, have shared greatly and learned much.

Now, as peace approaches, one asks where they will find objectives worthy of their best.

## The Memex

Consider a future device for individual use, which is a sort of mechanized private file and library. It needs a name, and, to coin one at random, "memex" will do. A memex is a device in which an individual stores all his books, records, and communications, and which is mechanized so that it may be consulted with exceeding speed and flexibility. It is an enlarged intimate supplement to his memory.

It consists of a desk, and while it can presumably be operated from a distance, it is primarily the piece of furniture at which he works. On the top are slanting translucent screens, on which material can be projected for convenient reading. There is a keyboard, and sets of buttons and levers. Otherwise it looks like an ordinary desk.

### Associative Trails

The human mind does not work that way. It operates by association. With one item in its grasp, it snaps instantly to the next that is suggested by the association of thoughts, in accordance with some intricate web of trails carried by the cells of the brain. It has other characteristics, of course; trails that are not frequently followed are prone to fade, items are not fully recoverable, yet the speed of action, the intricacy of trails, the detail of mental pictures, is an awe-inspiring thing.

Man cannot hope fully to duplicate this mental process artificially, but he certainly ought to be able to learn from it.
"""
    (art_dir / "article.md").write_text(art_md_content, encoding="utf-8")

    art_atom = {
        "id": art_id,
        "kind": "article",
        "version": 3,
        "created_at": "2026-11-08T20:01:00Z",
        "updated_at": "2026-11-08T20:01:00Z",
        "source": {
            "source_url": "https://www.theatlantic.com/magazine/archive/1945/07/as-we-may-think/303881/",
            "source_title": "As We May Think",
            "site_name": "The Atlantic",
            "author": "Vannevar Bush",
            "published_at": "1945-07-01T00:00:00Z",
            "favicon": "https://www.theatlantic.com/favicon.ico",
            "capture_method": "cli"
        },
        "curation": {
            "atom_title": "As We May Think",
            "description": "Vannevar Bush's seminal 1945 essay introducing the Memex—an individualized desk anticipating hypertext, personal computing, and the web.",
            "tags": ["hypertext", "memex", "computing-history", "philosophy"],
            "collections": ["Foundational Texts", "Web History"],
            "visibility": "public",
            "favorite": True
        },
        "content": {
            "cover_image": art_cover,
            "article": {
                "file": "article.md",
                "relative_path": "article.md",
                "word_count": len(art_md_content.split()),
                "byline": "Vannevar Bush"
            }
        }
    }
    (art_dir / "atom.json").write_text(json.dumps(art_atom, indent=2), encoding="utf-8")

    # 2. Bookmark: "The Internet Archive — Wayback Machine"
    bmk_id = "atm_20261108200200_demobmk"
    bmk_dir = ATOMS_DIR / bmk_id
    bmk_dir.mkdir(parents=True, exist_ok=True)
    bmk_cover = create_gradient_image(
        bmk_dir / "cover.jpg",
        "Wayback Machine",
        "Internet Archive: Universal Access to Knowledge",
        (13, 71, 161), (1, 36, 86)
    )
    bmk_atom = {
        "id": bmk_id,
        "kind": "bookmark",
        "version": 3,
        "created_at": "2026-11-08T20:02:00Z",
        "updated_at": "2026-11-08T20:02:00Z",
        "source": {
            "source_url": "https://archive.org/web/",
            "source_title": "Wayback Machine",
            "site_name": "Internet Archive",
            "author": "Brewster Kahle",
            "published_at": "1996-05-10T00:00:00Z",
            "favicon": "https://archive.org/favicon.ico",
            "capture_method": "bookmarklet"
        },
        "curation": {
            "atom_title": "Internet Archive: Wayback Machine",
            "description": "A digital library of Internet sites and cultural artifacts, providing permanent universal access to historical web pages.",
            "tags": ["web-archiving", "preservation", "digital-commons"],
            "collections": ["Preservation Tools"],
            "visibility": "public",
            "favorite": True
        },
        "content": {
            "cover_image": bmk_cover
        }
    }
    (bmk_dir / "atom.json").write_text(json.dumps(bmk_atom, indent=2), encoding="utf-8")

    # 3. Video: "The Mother of All Demos (1968)"
    vid_id = "atm_20261108200300_demovid"
    vid_dir = ATOMS_DIR / vid_id
    vid_dir.mkdir(parents=True, exist_ok=True)
    vid_cover = create_gradient_image(
        vid_dir / "cover.jpg",
        "The Mother of All Demos",
        "Douglas Engelbart (ACM / IEEE, 1968)",
        (180, 83, 9), (120, 53, 15)
    )
    transcript_text = """[00:00:05] If in your office, you as an intellectual worker, were supplied with a computer display.
[00:00:15] Backed up by a computer that was alive for you all day, and was instantly responsive to every action you had.
[00:00:25] How much value could you derive from that?
[00:00:40] Today, we will demonstrate the NLS system developed at the Augmentation Research Center.
[00:01:02] We have here what we call the mouse, and a chord keyset for rapid textual manipulation.
"""
    (vid_dir / "transcript.txt").write_text(transcript_text, encoding="utf-8")

    vid_atom = {
        "id": vid_id,
        "kind": "video",
        "version": 3,
        "created_at": "2026-11-08T20:03:00Z",
        "updated_at": "2026-11-08T20:03:00Z",
        "source": {
            "source_url": "https://www.youtube.com/watch?v=yJDv-zdhzMY",
            "source_title": "Douglas Engelbart: The Mother of All Demos (1968)",
            "site_name": "YouTube",
            "author": "Douglas Engelbart",
            "published_at": "1968-12-09T00:00:00Z",
            "favicon": "https://www.youtube.com/s/desktop/favicon.ico",
            "capture_method": "cli"
        },
        "curation": {
            "atom_title": "The Mother of All Demos (1968)",
            "description": "Douglas Engelbart and the SRI team unveil the mouse, windowing, hypermedia, text editing, video conferencing, and collaborative computing.",
            "tags": ["computing-history", "interfaces", "doug-engelbart", "demo"],
            "collections": ["Foundational Texts", "Talks"],
            "visibility": "public",
            "favorite": True
        },
        "content": {
            "cover_image": vid_cover,
            "video": {
                "provider": "youtube",
                "embed_url": "https://www.youtube.com/embed/yJDv-zdhzMY",
                "duration_seconds": 6000,
                "transcript_file": "transcript.txt",
                "transcript_language": "en",
                "transcript_is_generated": False,
                "has_transcript": True
            }
        }
    }
    (vid_dir / "atom.json").write_text(json.dumps(vid_atom, indent=2), encoding="utf-8")

    # 4. Quote: Ted Nelson on Files
    qte_id = "atm_20261108200400_demoqte"
    qte_dir = ATOMS_DIR / qte_id
    qte_dir.mkdir(parents=True, exist_ok=True)
    quote_md = """> "A file is only a clumsy container for thoughts. The true structure of ideas is non-linear, interconnected, and deeply associative."
> 
> — **Ted Nelson**, *Literary Machines* (1981)
"""
    (qte_dir / "quote.md").write_text(quote_md, encoding="utf-8")

    qte_atom = {
        "id": qte_id,
        "kind": "quote",
        "version": 3,
        "created_at": "2026-11-08T20:04:00Z",
        "updated_at": "2026-11-08T20:04:00Z",
        "source": {
            "source_url": "https://archive.org/details/literarymachines0000nels",
            "source_title": "Literary Machines",
            "site_name": "Project Xanadu",
            "author": "Ted Nelson",
            "published_at": "1981-01-01T00:00:00Z",
            "capture_method": "cli"
        },
        "curation": {
            "atom_title": "Ted Nelson on Files as Clumsy Containers",
            "description": "From Literary Machines (1981). Nelson critiques rigid hierarchical filesystem folders as insufficient for associative thought.",
            "tags": ["ted-nelson", "hypertext", "information-architecture", "quotes"],
            "collections": ["Notable Quotes"],
            "visibility": "public",
            "favorite": False
        },
        "content": {
            "text": {
                "file": "quote.md",
                "relative_path": "quote.md",
                "excerpt": "A file is only a clumsy container for thoughts. The true structure of ideas is non-linear, interconnected, and deeply associative.",
                "word_count": 21
            }
        }
    }
    (qte_dir / "atom.json").write_text(json.dumps(qte_atom, indent=2), encoding="utf-8")

    # 5. Note: Local-First Software
    not_id = "atm_20261108200500_demonot"
    not_dir = ATOMS_DIR / not_id
    not_dir.mkdir(parents=True, exist_ok=True)
    note_md = """# Seven Ideals of Local-First Software

*Notes on Kleppmann, Wiggins, Hardenberg, van Hardenberg (Ink & Switch, 2019)*

1. **No spinners: your work at your fingertips** — Local reads and local writes happen immediately without waiting for server network hops.
2. **Your work is not trapped on one device** — Cross-device synchronization via transparent data layers.
3. **The network is optional** — Every feature works completely offline on an airplane or cabin.
4. **Seamless collaboration with other people** — Conflict-free synchronization (CRDTs or immutable event logs).
5. **The long now** — Software and data that work 30 years from today without depending on proprietary SaaS servers remaining solvent.
6. **Security and privacy by default** — Local storage encrypted on your own filesystem.
7. **You retain ultimate ownership and control** — Plain, inspectable files on disk.

*Application in Webtack*: The Content Sidecar pattern guarantees Ideal #5 and #7: every atom is a self-contained folder of open formats (`atom.json`, `cover.jpg`, `article.md`).
"""
    (not_dir / "note.md").write_text(note_md, encoding="utf-8")

    not_atom = {
        "id": not_id,
        "kind": "note",
        "version": 3,
        "created_at": "2026-11-08T20:05:00Z",
        "updated_at": "2026-11-08T20:05:00Z",
        "source": {
            "source_url": None,
            "capture_method": "cli"
        },
        "curation": {
            "atom_title": "Seven Ideals of Local-First Software",
            "description": "Reflections on Ink & Switch's foundational 2019 paper and how the Content Sidecar pattern achieves longevity and ownership.",
            "tags": ["local-first", "architecture", "data-ownership", "manifesto"],
            "collections": ["Architecture Notes"],
            "visibility": "public",
            "favorite": True
        },
        "content": {
            "text": {
                "file": "note.md",
                "relative_path": "note.md",
                "excerpt": "Seven ideals of local-first software: no spinners, multi-device, offline-capable, collaboration, longevity, privacy, user ownership.",
                "word_count": len(note_md.split())
            }
        }
    }
    (not_dir / "atom.json").write_text(json.dumps(not_atom, indent=2), encoding="utf-8")

    # 6. Image: Memex Desk Illustration
    img_id = "atm_20261108200600_demoimg"
    img_dir = ATOMS_DIR / img_id
    img_dir.mkdir(parents=True, exist_ok=True)
    img_cover = create_gradient_image(
        img_dir / "cover.jpg",
        "The Memex Desk (1945)",
        "Life Magazine Illustration / Alfred D. Crimi",
        (74, 4, 78), (30, 27, 75)
    )
    img_atom = {
        "id": img_id,
        "kind": "image",
        "version": 3,
        "created_at": "2026-11-08T20:06:00Z",
        "updated_at": "2026-11-08T20:06:00Z",
        "source": {
            "source_url": "https://en.wikipedia.org/wiki/Memex",
            "source_title": "Memex Desk Diagram",
            "site_name": "Wikipedia",
            "author": "Alfred D. Crimi",
            "published_at": "1945-11-19T00:00:00Z",
            "capture_method": "cli"
        },
        "curation": {
            "atom_title": "The Memex Desk Diagram (1945)",
            "description": "Life Magazine illustration depicting the Memex desk conceived by Vannevar Bush in 'As We May Think'.",
            "tags": ["memex", "diagram", "vannevar-bush", "life-magazine"],
            "collections": ["Historical Artifacts"],
            "visibility": "public",
            "favorite": False
        },
        "content": {
            "cover_image": img_cover
        }
    }
    (img_dir / "atom.json").write_text(json.dumps(img_atom, indent=2), encoding="utf-8")

    print(f"✨ Created 6 demo atoms in {ATOMS_DIR}")

    # Reindex demo vault
    print("🔨 Running reindex on fixtures/demo_vault ...")
    subprocess.run(["python3", str(REPO_ROOT / "curate.py"), "--vault", str(DEMO_VAULT), "reindex"], check=True)
    print("✅ Demo vault successfully built and indexed!")


if __name__ == "__main__":
    build_demo_vault()
