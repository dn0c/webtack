# Seven Ideals of Local-First Software

*Notes on Kleppmann, Wiggins, Hardenberg, van Hardenberg (Ink & Switch, 2019)*

1. **No spinners: your work at your fingertips** — Local reads and local writes happen immediately without waiting for server network hops.
2. **Your work is not trapped on one device** — Cross-device synchronization via transparent data layers.
3. **The network is optional** — Every feature works completely offline on an airplane or cabin.
4. **Seamless collaboration with other people** — Conflict-free synchronization (CRDTs or immutable event logs).
5. **The long now** — Software and data that work 30 years from today without depending on proprietary SaaS servers remaining solvent.
6. **Security and privacy by default** — Local storage encrypted on your own filesystem.
7. **You retain ultimate ownership and control** — Plain, inspectable files on disk.

*Application in WideWeb*: The Content Sidecar pattern guarantees Ideal #5 and #7: every atom is a self-contained folder of open formats (`atom.json`, `cover.jpg`, `article.md`).
