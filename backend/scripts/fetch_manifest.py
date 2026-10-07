"""Reproduce saved source downloads without hardcoding time-sensitive product URLs."""
import json
from pathlib import Path
from backend.scripts.download_data import download
root=Path(__file__).resolve().parents[1]
for item in json.loads((root/'data/download_manifest.json').read_text(encoding='utf8')):
    target=(root/item['path']).resolve()
    if not target.is_relative_to((root/'data/raw').resolve()):raise ValueError('Manifest path outside raw data')
    download(item['url'],target,item.get('query'))
