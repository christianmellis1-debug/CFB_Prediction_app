from concurrent.futures import ThreadPoolExecutor
from urllib.request import urlopen
from pathlib import Path
p=Path(__file__).parent/'inputs'
def f(y):
 dest=p/f'pbp{y}.parquet'
 if not dest.exists():
  with urlopen(f'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_cfb_pbp/play_by_play_{y}.parquet',timeout=60) as r:dest.write_bytes(r.read())
 print(y,dest.stat().st_size,flush=True)
with ThreadPoolExecutor(3) as e:list(e.map(f,[2024,2025,2026]))
