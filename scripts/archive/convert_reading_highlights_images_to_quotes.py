#!/usr/bin/env python3
"""
Convert image atoms in the "Reading Highlights" collection to quote atoms.
- Parses the text or highlighted text from each image
- Updates atom.json: kind="quote", text payload, metadata
- Creates quote.txt sidecar
- Deletes the cover image file (throwing away the image)
- Updates vault/vault.db
"""

import os
import json
import sqlite3
import shutil
from datetime import datetime, timezone
from pathlib import Path

VAULT_DIR = Path("vault").resolve()
DB_PATH = VAULT_DIR / "vault.db"

# Data for all 18 image atoms
QUOTES_DATA = {
    "atm_20261104205524_95c3f0": {
        "title": "Like Brothers (Page 85)",
        "author": "Mark Duplass & Jay Duplass",
        "quote": """wonderful world of Mark Kozelek and the Red House Painters. I love the music. I am comfortable now in its sadness and don't feel the need to fight it anymore. More important, though, I want to say I'm sorry for not being a friend to you. For not even trying to understand you. For blasting weird, insensitive light into your dark, shy inner world. I get it now. But back then I simply did not understand it or make a legitimate attempt to understand it. I was a bit of a jam band hippie douchebag who was just trying to block out the darkness because I was, essentially, afraid of it. And for that, I am truly sorry.

Your freshman-year roommate,
Mark"""
    },
    "atm_20261104205525_89bb52": {
        "title": "11/22/63 (Page 330)",
        "author": "Stephen King",
        "quote": "I'll tell you something, my friend. Something forty years in high schools and sixty years of living has taught me and taught me well. Artistic talent is far more common than the talent to nurture artistic talent. Any parent with a hard hand can crush it, but to nurture it is much more difficult."
    },
    "atm_20261104205526_670ea9": {
        "title": "Conspiracy (Page 2)",
        "author": "Ryan Holiday",
        "quote": "The truth, he says, is that “No one can carry out complicated plans. All parties and groups are fractious and bumbling.”"
    },
    "atm_20261104205528_e45104": {
        "title": "Conspiracy: Compartmentalization of Lawyers",
        "author": "Ryan Holiday",
        "quote": "But that’s the nice thing about lawyers: as long as you’re paying them, they’re usually good with whatever terms go along with it. Compartmentalization is their job. It’s how they represent people who are guilty, how they file long motions they know are unlikely to be successful, how they can patiently keep secrets that they’d otherwise love to be able to share."
    },
    "atm_20261104205532_b62011": {
        "title": "Conspiracy: Ego is the Enemy",
        "author": "Ryan Holiday",
        "quote": "“If you want to win, ‘ego is the enemy,’” Peter would say, “and the anti-ego thing we did was downgrade Harder’s role in the trial. Harder was not happy about this. It was the case of your lifetime and you get to have a much smaller part in it than you originally thought? But if we win, you get to take credit.”"
    },
    "atm_20261104205533_ff3909": {
        "title": "Conspiracy: Sweet Smell of Success",
        "author": "Ryan Holiday",
        "quote": "The terrible thing about people like you is that decent people have to become so much like you in order to stop you—in order to survive."
    },
    "atm_20261104205535_54119f": {
        "title": "Conspiracy: The Plenipotentiary Model",
        "author": "Ryan Holiday",
        "quote": "Early in the two companies he cofounded, Paypal and Palantir, Thiel would install strong CEOs and leaders. He relies on what might be called the plenipotentiary model—empowering trusted, skilled people on his behalf to execute the bold vision he has created. In Mr. A and Harder, he needed representatives whose judgments were close enough to his own that he could be confident in his ignorance of specific issues and deploy them to the places he couldn’t go, trusting them to discern which decisions were important enough to be made by Thiel alone."
    },
    "atm_20261104205537_3f415e": {
        "title": "Reading Horace",
        "author": "Horace / Austin Kleon",
        "quote": """It’s reason, good sense,
That takes away your cares; it isn’t owning
A house at the shore that has a commanding view.
He only changes his scene, he doesn’t change
His mind, who rushes to go abroad. How many
Are busy going elsewhere getting nowhere;
But if you have a healthy attitude,
Then what you’re seeking to find can always be found
Right where you are, even in froggy Ulúbrae.

fucking Texas."""
    },
    "atm_20261104205537_e811b6": {
        "title": "Like Brothers: To Make Change but Also Just Get By",
        "author": "Mark Duplass & Jay Duplass",
        "quote": "Sorry you feel conflicted like we do. That you are uncertain as to what the right path is in life. Sorry that you want so badly to be useful but also happy. To be inspired but also at peace. To make change but also just get by."
    },
    "atm_20261104205540_5ba344": {
        "title": "Jo Johnson: The Meanest Thing You Do to Yourself",
        "author": "Jo Johnson",
        "quote": "the meanest thing you do to yourself is pretend you don’t want the things you want. shrink the desire before anyone can see it. call it unrealistic before someone else does. and then walk around with this low grade starvation you can’t name because you buried the appetite so deep even you forgot where you put it. wanting things is dangerous. I know. it opens you up to disappointment and to looking foolish and to reaching for something that might not reach back. want it anyway. the alternative is a life of pretending you’re full."
    },
    "atm_20261104205540_7ae0ee": {
        "title": "Tomorrow, and Tomorrow, and Tomorrow (Page 88)",
        "author": "Gabrielle Zevin",
        "quote": "With the child’s design squared away, Sadie was perfecting the child’s movements. She wanted the walk to feel buoyant and slightly out of control, like a baby duck trailing after its mother. In the design document that she and Sam had written: “The child’s body moves the way a body can move before it has felt or even encountered the idea of pain.” Oh, the ambitions of design documents!"
    },
    "atm_20261104205541_b7e26d": {
        "title": "Tomorrow, and Tomorrow, and Tomorrow (Page 138)",
        "author": "Gabrielle Zevin",
        "quote": "She liked to be comfortable. She liked hotel rooms, thick towels, cashmere sweaters, silk dresses, oxfords, brunch, fine stationery, overpriced conditioner, bouquets of gerbera, hats, postage stamps, art monographs, maranta plants, PBS documentaries, challah, soy candles, and yoga. She liked receiving a canvas tote bag when she gave to a charitable cause. She was an avid reader (of fiction and nonfiction), but she never read the newspaper, other than the arts sections, and she felt guilty about this. Dov often said she was bourgeois. He meant it as an insult, but she knew that she probably was. Her parents were bourgeois, and she adored them, so, of course, she had turned out bourgeois, too. She wished she could get a dog, but Dov’s building didn’t allow them."
    },
    "atm_20261104205543_32b742": {
        "title": "Tomorrow, and Tomorrow, and Tomorrow (Page 137)",
        "author": "Gabrielle Zevin",
        "quote": "By eleven-thirty, Sadie was in her pajamas, teeth brushed and flossed, ready to go to bed. She wondered if this was what other twenty-three-year-olds' Friday nights were like. When she was forty, would she lament that she hadn't had sex with more people and partied more? But then, she didn't enjoy many people, and she had never gone to a party that she wasn't eager to leave. She hated being drunk, though she did enjoy smoking a joint every now and then. She liked playing games, seeing a foreign movie, a good meal. She liked going to bed early and waking up early. She liked working. She liked that she was good at her work, and she felt proud of the fact that she was well paid for it. She felt pleasure in orderly things—a perfectly efficient section of code, a closet where every item was in its place. She liked solitude and the thoughts of her own interesting and creative mind."
    },
    "atm_20261104205544_effb06": {
        "title": "Tomorrow, and Tomorrow, and Tomorrow (Page 291)",
        "author": "Gabrielle Zevin",
        "quote": "When you were a boy, you never thought you would be a producer of video games. You must admit there were times when you wondered if it was a mortifying passivity that had led you to this employment. Had you become a video game producer because Sam and Sadie had wanted to make video games, and you had nothing else you were doing at the time? Had you become a video game producer because you loved people who wanted to make games? How much of your life had been happenstance? How much of your life had been a roll of the big polyhedral die in the sky? But then, weren’t all lives that way? Who could say, in the end, that they had chosen any of it? And even if you hadn’t exactly chosen video game producer, you were good at it."
    },
    "atm_20261104205545_e1d4df": {
        "title": "My Struggle (Book #1) (Page 238)",
        "author": "Karl Ove Knausgård",
        "quote": "The foreignness of them, which resided not in their clothes or appearance but their behavior, was compelling, and to live in Japan, surrounded by all this foreignness, all the things one saw but did not understand, whose meaning one might intuit without ever being sure, was a dream I had long held. To sit in a Japanese house, furnished in simple, Spartan fashion, with sliding doors and paper partitions, created for a neatness that was alien to me and my northern European impetuosness, would be fantastic. To sit there and write a novel and see how the surroundings slowly and imperceptibly shaped the writing, for the way we think is of course as closely associated with the specific surroundings of which we form part as the people with whom we speak and the books we read. Japan, but also Argentina, where familiar European features were lent quite a different hue, shifted to quite a different place, and the USA, one of the small towns in Maine, for example, with landscape so like Norway’s southern coast, what might have sprung off the page there?"
    },
    "atm_20261104205546_1f4c50": {
        "title": "The Dark Forest and the Cozy Web",
        "author": "Maggie Appleton",
        "quote": """Dark Forest of the Clear Web: Inhabited by data scavengers, adtech marketers, & trolls. Enter with caution.

Cozy Web: Gatekeeper-protected enclave communities comprised of like-minded folks around niche interests. Run through chat streams like WhatsApp, Slack, Discord, Snapchat, etc.

Digital Gardens: Unpolished, loosely organised notes published on personal wikis. Tended over time as an evolving knowledge base.

Dark Web: Internet undergrowth & decomposing morals.

Onion Routers: The only way into 8chan."""
    },
    "atm_20261104205546_e905c2": {
        "title": "Chaos Streams, Digital Gardens, and Cultivated Performance",
        "author": "Maggie Appleton",
        "quote": """Chaos Streams: Twitter, cozy web groups (Discord, Telegram)
Digital Gardens: Private notes, learning in public
Cultivated Performance: Classic blog posts, books & research papers"""
    },
    "atm_20261104205549_8b7586": {
        "title": "Fav: On Ants and Comprehension",
        "author": "@Favwontmiss",
        "quote": "i learned ants really have no concept of us as humans because of their limited eyesight and how big we are to them. they see us as moving shadows, or wind, or like obstacles and landscape (i imagine mountains). makes me wonder what’s in front of me right now that’s too large for me to comprehend."
    }
}

def main():
    print(f"Connecting to DB at {DB_PATH}...")
    shutil.copy2(DB_PATH, VAULT_DIR / "vault.db.pre_quotes_conversion.bak")
    print(f"Created DB backup at {VAULT_DIR / 'vault.db.pre_quotes_conversion.bak'}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    updated_count = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    for atom_id, q_info in QUOTES_DATA.items():
        c.execute("SELECT * FROM atoms WHERE id = ?", (atom_id,))
        row = c.fetchone()
        if not row:
            print(f"⚠️ Atom {atom_id} not found in database!")
            continue

        raw_json_str = row["raw_json"]
        doc = json.loads(raw_json_str)

        # Locate atom directory
        # e.g. atoms/2026/11/<atom_id>
        cover_path_rel = row["cover_file_path"]
        if cover_path_rel:
            atom_dir = VAULT_DIR / Path(cover_path_rel).parent
        else:
            atom_dir = VAULT_DIR / "atoms" / "2026" / "11" / atom_id

        if not atom_dir.exists():
            print(f"⚠️ Atom dir {atom_dir} does not exist!")
            continue

        quote_text = q_info["quote"].strip()
        quote_title = q_info["title"]
        author = q_info["author"]
        words = quote_text.split()
        word_count = len(words)

        # 1. Write quote.txt
        quote_file = atom_dir / "quote.txt"
        with open(quote_file, "w", encoding="utf-8") as qf:
            qf.write(quote_text + "\n")

        # 2. Delete cover image file(s)
        deleted_images = []
        for img_name in ["cover.png", "cover.jpeg", "cover.jpg"]:
            img_file = atom_dir / img_name
            if img_file.exists():
                os.remove(img_file)
                deleted_images.append(img_name)

        # 3. Update atom doc
        rel_folder = atom_dir.relative_to(VAULT_DIR)
        quote_rel_path = str(rel_folder / "quote.txt")

        doc["kind"] = "quote"
        doc["updated_at"] = now_iso
        doc["curation"]["atom_title"] = quote_title
        if "author" in doc["provenance"]:
            doc["provenance"]["author"] = author
        else:
            doc["provenance"]["author"] = author

        meta_bag = {
            "word_count": word_count,
            "author": author
        }
        doc["metadata_json"] = meta_bag

        doc["payload"]["cover_image"] = None
        doc["payload"]["text"] = {
            "file": "quote.txt",
            "relative_path": quote_rel_path,
            "excerpt": quote_text,
            "word_count": word_count
        }

        # Write updated atom.json
        atom_json_file = atom_dir / "atom.json"
        with open(atom_json_file, "w", encoding="utf-8") as jf:
            json.dump(doc, jf, indent=2, ensure_ascii=False)

        # 4. Update SQLite database
        c.execute("""
            UPDATE atoms
            SET kind = 'quote',
                atom_title = ?,
                author = ?,
                cover_file_path = NULL,
                text_content = ?,
                metadata = ?,
                raw_json = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            quote_title,
            author,
            quote_text,
            json.dumps(meta_bag),
            json.dumps(doc, ensure_ascii=False),
            now_iso,
            atom_id
        ))

        updated_count += 1
        print(f"✅ Converted {atom_id} -> quote: '{quote_title}' by {author} (deleted {deleted_images})")

    conn.commit()
    conn.close()
    print(f"\n🎉 Successfully converted {updated_count} image atoms to quotes!")

if __name__ == "__main__":
    main()
