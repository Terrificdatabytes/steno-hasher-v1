import hashlib
import json
import os
from datetime import datetime, timezone

from storage import read_json, write_json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHAIN_DIR = os.path.join(BASE_DIR, 'data', 'chains')


def _now():
    return datetime.now(timezone.utc).isoformat()


def _chain_path(file_id):
    return os.path.join(CHAIN_DIR, f'{file_id}.json')


def _hash_block(index, timestamp, prev_hash, data):
    payload = json.dumps(
        {'index': index, 'timestamp': timestamp, 'prev_hash': prev_hash, 'data': data},
        sort_keys=True, default=str
    )
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def load_chain(file_id):
    return read_json(_chain_path(file_id), [])


def save_chain(file_id, chain):
    os.makedirs(CHAIN_DIR, exist_ok=True)
    write_json(_chain_path(file_id), chain)


def create_genesis(file_id, data):
    timestamp = _now()
    prev_hash = '0' * 64
    block_hash = _hash_block(0, timestamp, prev_hash, data)
    block = {
        'index': 0, 'timestamp': timestamp, 'prev_hash': prev_hash,
        'data': data, 'block_hash': block_hash,
    }
    save_chain(file_id, [block])
    return block


def add_block(file_id, data):
    chain = load_chain(file_id)
    if not chain:
        raise ValueError('Chain does not exist for this file yet')
    prev = chain[-1]
    index = prev['index'] + 1
    timestamp = _now()
    prev_hash = prev['block_hash']
    block_hash = _hash_block(index, timestamp, prev_hash, data)
    block = {
        'index': index, 'timestamp': timestamp, 'prev_hash': prev_hash,
        'data': data, 'block_hash': block_hash,
    }
    chain.append(block)
    save_chain(file_id, chain)
    return block


def verify_chain(chain):
    for i, block in enumerate(chain):
        expected = _hash_block(block['index'], block['timestamp'], block['prev_hash'], block['data'])
        if expected != block['block_hash']:
            return False
        if i > 0 and block['prev_hash'] != chain[i - 1]['block_hash']:
            return False
    return True


def find_block_by_watermark(watermark_id):
    """Search every chain for a block whose embedded watermark_id matches.
    Returns (file_id, block) or (None, None)."""
    if not os.path.isdir(CHAIN_DIR):
        return None, None
    for fname in os.listdir(CHAIN_DIR):
        if not fname.endswith('.json'):
            continue
        file_id = fname[:-5]
        chain = load_chain(file_id)
        for block in chain:
            if block.get('data', {}).get('watermark_id') == watermark_id:
                return file_id, block
    return None, None
