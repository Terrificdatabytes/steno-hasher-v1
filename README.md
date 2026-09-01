# LEDGER — Chain of Custody

A Flask + Tailwind prototype for tracking file custody with a from-scratch hash-linked
blockchain and invisible steganographic watermarking (PNG/JPG/BMP via LSB, TXT via
zero-width characters, PDF via hidden metadata). No external database and no blockchain
library — everything persists to JSON files under `data/` and uploaded files under `uploads/`.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
# open http://localhost:5000
```

## Deploy to Render

1. Push this repo to GitHub.
2. In Render, choose **New + → Blueprint** and point it at this repo — it will pick up
   `render.yaml` automatically and provision the web service with a persistent disk
   mounted at `data/` (so registered files/chains survive restarts).
   - Alternatively, choose **New + → Web Service**, connect the repo, and set:
     - Build Command: `pip install -r requirements.txt`
     - Start Command: `gunicorn app:app --workers 2 --threads 4 --timeout 120`
     - Add an environment variable `SECRET_KEY` with a random value.
3. Note: on Render's free tier the filesystem is ephemeral unless you attach a persistent
   disk (the `render.yaml` here does this for `data/`). `uploads/` is not persisted by
   default — add it to the disk mount too, or accept that uploaded originals/watermarked
   copies reset on redeploy (fine for a demo).

## Project layout

```
ledger/
├── app.py            Flask routes / API
├── blockchain.py      Hash-linked chain implementation
├── stego.py            Watermark embed/extract (image, text, pdf)
├── storage.py          Simple JSON read/write helpers
├── requirements.txt
├── Procfile             For Render/Heroku-style process declaration
├── render.yaml           Render Blueprint config
├── templates/index.html
├── static/style.css
├── static/app.js
├── data/                 JSON records + per-file chains (auto-created)
└── uploads/               original/watermarked/scan_tmp files (auto-created)
```

## Security note

This is a prototype/demo. `SECRET_KEY` defaults to an insecure value if not set via
environment variable — always set `SECRET_KEY` in production. There is no real
authentication (identity is self-declared), so do not use this for actual sensitive
custody tracking without adding proper auth.
