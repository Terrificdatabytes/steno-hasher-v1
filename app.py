import os
import secrets
import uuid
from datetime import datetime, timezone

from flask import Flask, request, session, jsonify, render_template, send_file

import blockchain
import stego
from storage import read_json, write_json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
FILES_JSON = os.path.join(DATA_DIR, 'files.json')
REQUESTS_JSON = os.path.join(DATA_DIR, 'requests.json')
CHAIN_DIR = os.path.join(DATA_DIR, 'chains')
UPLOAD_ORIG = os.path.join(BASE_DIR, 'uploads', 'originals')
UPLOAD_WM = os.path.join(BASE_DIR, 'uploads', 'watermarked')
SCAN_TMP = os.path.join(BASE_DIR, 'uploads', 'scan_tmp')

IMAGE_EXT = {'.png', '.jpg', '.jpeg', '.bmp'}
TEXT_EXT = {'.txt'}
PDF_EXT = {'.pdf'}
ALLOWED_EXT = IMAGE_EXT | TEXT_EXT | PDF_EXT

for d in (DATA_DIR, CHAIN_DIR, UPLOAD_ORIG, UPLOAD_WM, SCAN_TMP):
    os.makedirs(d, exist_ok=True)
if not os.path.exists(FILES_JSON):
    write_json(FILES_JSON, [])
if not os.path.exists(REQUESTS_JSON):
    write_json(REQUESTS_JSON, [])

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-me-please')
app.config['MAX_CONTENT_LENGTH'] = 15 * 1024 * 1024  # 15 MB


def now():
    return datetime.now(timezone.utc).isoformat()


def get_identity():
    return session.get('identity')


def json_error(message, code=400):
    return jsonify({'error': message}), code


@app.errorhandler(413)
def too_large(e):
    return jsonify({'error': 'File too large (max 15MB)'}), 413


# ---------------------------------------------------------------- pages

@app.route('/')
def index():
    return render_template('index.html')


# ---------------------------------------------------------------- identity

@app.route('/api/identity', methods=['GET'])
def api_get_identity():
    return jsonify(get_identity())


@app.route('/api/identity', methods=['POST'])
def api_set_identity():
    body = request.get_json(force=True, silent=True) or {}
    name = (body.get('name') or '').strip()
    org = (body.get('org') or '').strip()
    email = (body.get('email') or '').strip().lower()
    phone = (body.get('phone') or '').strip()
    role = (body.get('role') or '').strip().lower()

    if not name or not org or not email or role not in ('validator', 'requester'):
        return json_error('name, org, email and a valid role are required')

    identity = {'name': name, 'org': org, 'email': email, 'phone': phone, 'role': role}
    session['identity'] = identity
    session.permanent = True
    return jsonify(identity)


# ---------------------------------------------------------------- files

@app.route('/api/files', methods=['GET'])
def api_list_files():
    return jsonify(read_json(FILES_JSON, []))


@app.route('/api/files/mine', methods=['GET'])
def api_my_files():
    ident = get_identity()
    if not ident or ident['role'] != 'validator':
        return json_error('Validator identity required', 403)
    files = read_json(FILES_JSON, [])
    mine = [f for f in files if f['owner_email'] == ident['email'] and f['owner_org'] == ident['org']]
    return jsonify(mine)


@app.route('/api/files', methods=['POST'])
def api_register_file():
    ident = get_identity()
    if not ident or ident['role'] != 'validator':
        return json_error('Validator identity required', 403)

    if 'file' not in request.files or not request.files['file'].filename:
        return json_error('No file selected')
    f = request.files['file']

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return json_error(f'Unsupported file type: {ext or "(none)"}')

    file_id = uuid.uuid4().hex
    stored_name = f'{file_id}{ext}'
    stored_path = os.path.join(UPLOAD_ORIG, stored_name)
    f.save(stored_path)
    sha256_hex = stego.sha256_of_file(stored_path)

    record = {
        'file_id': file_id,
        'filename': f.filename,
        'stored_name': stored_name,
        'ext': ext,
        'mimetype': f.mimetype or 'application/octet-stream',
        'sha256': sha256_hex,
        'owner_name': ident['name'],
        'owner_org': ident['org'],
        'owner_email': ident['email'],
        'owner_phone': ident.get('phone', ''),
        'created_at': now(),
    }
    files = read_json(FILES_JSON, [])
    files.append(record)
    write_json(FILES_JSON, files)

    genesis_data = {
        'event': 'REGISTERED',
        'file_id': file_id,
        'filename': f.filename,
        'sha256': sha256_hex,
        'owner': {
            'name': ident['name'], 'org': ident['org'],
            'email': ident['email'], 'phone': ident.get('phone', ''),
        },
    }
    blockchain.create_genesis(file_id, genesis_data)
    return jsonify(record), 201


@app.route('/api/files/<file_id>/chain', methods=['GET'])
def api_file_chain(file_id):
    ident = get_identity()
    files = read_json(FILES_JSON, [])
    record = next((x for x in files if x['file_id'] == file_id), None)
    if not record:
        return json_error('File not found', 404)
    if not ident or ident['role'] != 'validator' or ident['email'] != record['owner_email'] or ident['org'] != record['owner_org']:
        return json_error('Only the owning validator may view this chain', 403)
    chain = blockchain.load_chain(file_id)
    return jsonify({'file': record, 'chain': chain, 'valid': blockchain.verify_chain(chain)})


# ---------------------------------------------------------------- requests

@app.route('/api/requests', methods=['POST'])
def api_create_request():
    ident = get_identity()
    if not ident or ident['role'] != 'requester':
        return json_error('Requester identity required', 403)

    body = request.get_json(force=True, silent=True) or {}
    file_id = body.get('file_id')
    files = read_json(FILES_JSON, [])
    record = next((x for x in files if x['file_id'] == file_id), None)
    if not record:
        return json_error('File not found', 404)

    reqs = read_json(REQUESTS_JSON, [])
    dup = next((r for r in reqs if r['file_id'] == file_id
                and r['requester']['email'] == ident['email'] and r['status'] == 'pending'), None)
    if dup:
        return json_error('You already have a pending request for this file')

    rid = uuid.uuid4().hex
    rec = {
        'request_id': rid,
        'file_id': file_id,
        'filename': record['filename'],
        'requester': {
            'name': ident['name'], 'org': ident['org'],
            'email': ident['email'], 'phone': ident.get('phone', ''),
        },
        'status': 'pending',
        'created_at': now(),
        'decided_at': None,
        'block_index': None,
        'block_hash': None,
        'watermark_id': None,
        'watermarked_stored_name': None,
        'note': None,
    }
    reqs.append(rec)
    write_json(REQUESTS_JSON, reqs)
    return jsonify(rec), 201


@app.route('/api/requests/mine', methods=['GET'])
def api_requests_mine():
    ident = get_identity()
    if not ident:
        return json_error('Identity required', 403)
    reqs = read_json(REQUESTS_JSON, [])
    mine = [r for r in reqs if r['requester']['email'] == ident['email']]
    mine.sort(key=lambda r: r['created_at'], reverse=True)
    return jsonify(mine)


@app.route('/api/requests/incoming', methods=['GET'])
def api_requests_incoming():
    ident = get_identity()
    if not ident or ident['role'] != 'validator':
        return json_error('Validator identity required', 403)
    files = read_json(FILES_JSON, [])
    my_ids = {f['file_id'] for f in files if f['owner_email'] == ident['email'] and f['owner_org'] == ident['org']}
    reqs = read_json(REQUESTS_JSON, [])
    incoming = [r for r in reqs if r['file_id'] in my_ids]
    incoming.sort(key=lambda r: r['created_at'], reverse=True)
    return jsonify(incoming)


def _find_request(rid):
    reqs = read_json(REQUESTS_JSON, [])
    for r in reqs:
        if r['request_id'] == rid:
            return reqs, r
    return reqs, None


def _owns_request(ident, req_rec):
    files = read_json(FILES_JSON, [])
    record = next((x for x in files if x['file_id'] == req_rec['file_id']), None)
    if not record:
        return False
    return ident['email'] == record['owner_email'] and ident['org'] == record['owner_org']


@app.route('/api/requests/<rid>/approve', methods=['POST'])
def api_approve_request(rid):
    ident = get_identity()
    if not ident or ident['role'] != 'validator':
        return json_error('Validator identity required', 403)

    reqs, rec = _find_request(rid)
    if not rec:
        return json_error('Request not found', 404)
    if rec['status'] != 'pending':
        return json_error('Request already decided')
    if not _owns_request(ident, rec):
        return json_error('You do not own this file', 403)

    files = read_json(FILES_JSON, [])
    file_rec = next(x for x in files if x['file_id'] == rec['file_id'])

    src_path = os.path.join(UPLOAD_ORIG, file_rec['stored_name'])
    out_ext = '.png' if file_rec['ext'] in IMAGE_EXT else file_rec['ext']
    out_name = f'{rid}{out_ext}'
    out_path = os.path.join(UPLOAD_WM, out_name)

    watermark_id = secrets.token_hex(32)  # unique 64-char credential for this exact copy
    try:
        stego.embed_watermark(file_rec['ext'], src_path, watermark_id, out_path)
    except Exception as e:
        return json_error(f'Watermarking failed: {e}', 500)

    block_data = {
        'event': 'APPROVED',
        'request_id': rid,
        'holder': rec['requester'],
        'approved_at': now(),
        'watermark_id': watermark_id,
    }
    block = blockchain.add_block(rec['file_id'], block_data)

    for r in reqs:
        if r['request_id'] == rid:
            r['status'] = 'approved'
            r['decided_at'] = now()
            r['block_index'] = block['index']
            r['block_hash'] = block['block_hash']
            r['watermark_id'] = watermark_id
            r['watermarked_stored_name'] = out_name
    write_json(REQUESTS_JSON, reqs)

    _, updated = _find_request(rid)
    return jsonify(updated)


@app.route('/api/requests/<rid>/reject', methods=['POST'])
def api_reject_request(rid):
    ident = get_identity()
    if not ident or ident['role'] != 'validator':
        return json_error('Validator identity required', 403)

    reqs, rec = _find_request(rid)
    if not rec:
        return json_error('Request not found', 404)
    if rec['status'] != 'pending':
        return json_error('Request already decided')
    if not _owns_request(ident, rec):
        return json_error('You do not own this file', 403)

    body = request.get_json(force=True, silent=True) or {}
    note = (body.get('note') or '').strip()

    for r in reqs:
        if r['request_id'] == rid:
            r['status'] = 'rejected'
            r['decided_at'] = now()
            r['note'] = note or None
    write_json(REQUESTS_JSON, reqs)

    _, updated = _find_request(rid)
    return jsonify(updated)


@app.route('/api/requests/<rid>/download', methods=['GET'])
def api_download_request(rid):
    ident = get_identity()
    if not ident:
        return json_error('Identity required', 403)
    _, rec = _find_request(rid)
    if not rec:
        return json_error('Request not found', 404)
    if rec['requester']['email'] != ident['email']:
        return json_error('Not your request', 403)
    if rec['status'] != 'approved':
        return json_error('Request is not approved')

    path = os.path.join(UPLOAD_WM, rec['watermarked_stored_name'])
    if not os.path.exists(path):
        return json_error('Watermarked file missing on server', 500)

    base, orig_ext = os.path.splitext(rec['filename'])
    actual_ext = os.path.splitext(rec['watermarked_stored_name'])[1]
    download_name = f'watermarked_{base}{actual_ext}'
    return send_file(path, as_attachment=True, download_name=download_name)


# ---------------------------------------------------------------- scan

@app.route('/api/scan', methods=['POST'])
def api_scan():
    if 'file' not in request.files or not request.files['file'].filename:
        return json_error('No file selected')
    f = request.files['file']
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return json_error(f'Unsupported file type for scanning: {ext or "(none)"}')

    tmp_path = os.path.join(SCAN_TMP, f'{uuid.uuid4().hex}{ext}')
    f.save(tmp_path)
    try:
        payload = stego.extract_watermark(ext, tmp_path)
    except Exception:
        payload = None
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    if not payload:
        return jsonify({
            'matched': False,
            'message': 'No watermark could be extracted. The file may be unprotected, '
                        'the original (unissued) copy, or corrupted.',
        })

    file_id, block = blockchain.find_block_by_watermark(payload)
    if not file_id:
        return jsonify({
            'matched': False,
            'message': 'A hidden watermark was found but does not match any record in this system.',
            'payload': payload,
        })

    files = read_json(FILES_JSON, [])
    file_rec = next((x for x in files if x['file_id'] == file_id), None)
    chain = blockchain.load_chain(file_id)

    return jsonify({
        'matched': True,
        'file': file_rec,
        'chain': chain,
        'matched_watermark_id': payload,
        'matched_block_index': block['index'],
        'last_holder': block['data'].get('holder'),
        'held_at': block['data'].get('approved_at', block['timestamp']),
    })


if __name__ == '__main__':
    app.run(debug=True, port=5000)
