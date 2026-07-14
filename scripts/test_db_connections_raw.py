import sys
import psycopg2

conn_str = "host=127.0.0.1 port=54322 user=postgres password=postgres dbname=postgres"
try:
    conn = psycopg2.connect(conn_str)
    cur = conn.cursor()
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")
    tables = [row[0] for row in cur.fetchall()]
    print(f"Tables in public schema: {tables}")
    
    # Check if muestras_concreto exists
    if "muestras_concreto" in tables:
        print("-> muestras_concreto exists!")
        cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'muestras_concreto';")
        cols = cur.fetchall()
        print("Columns in muestras_concreto:")
        for col, dtype in cols:
            print(f"   {col} ({dtype})")
            
    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
