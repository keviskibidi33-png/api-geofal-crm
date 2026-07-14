import psycopg2

urls = [
    "postgresql://postgres:fA1xpV4Qy5vcuXcgDA5MbBQQ2Jh32CcF@localhost:5432/postgres",
    "postgresql://postgres:Li4Rj2DmjJpkiZtQ@localhost:5432/postgres",
    "postgresql://postgres:F4xvOgZobs6EBgiAkKkkDKd8Agz7QzLi@localhost:5432/postgres",
    "postgresql://directus:directus@localhost:5432/directus",
    # Try 192.168.18.250 as well
    "postgresql://postgres:fA1xpV4Qy5vcuXcgDA5MbBQQ2Jh32CcF@192.168.18.250:5432/postgres",
    "postgresql://postgres:Li4Rj2DmjJpkiZtQ@192.168.18.250:5432/postgres",
]

for url in urls:
    try:
        conn = psycopg2.connect(url, connect_timeout=2)
        print(f"SUCCESS: {url.split('@')[0]}@{url.split('@')[1]}")
        conn.close()
        break
    except Exception as e:
        # Print with cp1252 decoding
        err_str = str(e)
        try:
            # Let's extract the raw exception bytes or decode manually
            # In python, e.args[0] or str(e) might contain the unicode string with surrogate escapes or just standard string.
            # Let's encode it to latin-1/cp1252 and then decode it.
            decoded_msg = err_str.encode('utf-8', errors='ignore').decode('cp1252', errors='replace')
            print(f"FAILED: {url.split('@')[0]}@{url.split('@')[1]} -> {decoded_msg}")
        except Exception as err:
            print(f"FAILED: {url.split('@')[0]}@{url.split('@')[1]} -> {repr(e)}")
