import sys
from pathlib import Path
from sqlalchemy import create_engine, text

# Add parent directory to sys.path
sys.path.append(str(Path(__file__).resolve().parents[1]))

hosts = ["127.0.0.1", "localhost", "192.168.18.250", "db.geofal.com.pe"]
password = "F4xvOgZobs6EBgiAkKkkDKd8Agz7QzLi"

for host in hosts:
    url = f"postgresql://postgres:{password}@{host}:5432/postgres?sslmode=disable"
    print(f"Testing connection to {host}...")
    try:
        engine = create_engine(url, connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            res = conn.execute(text("SELECT 1")).scalar()
            print(f"-> SUCCESS for {host}: result={res}")
    except Exception as e:
        # Avoid Unicode decode issues in printing
        err_msg = str(e).encode('utf-8', errors='replace').decode('utf-8')
        print(f"-> FAILED for {host}: {type(e).__name__} - {err_msg[:200]}")
