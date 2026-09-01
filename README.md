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
