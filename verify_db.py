import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()
db_url = os.environ.get('DATABASE_URL')
conn = psycopg2.connect(db_url)
cur = conn.cursor()

print("TABLES:")
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public';")
for row in cur.fetchall():
    print(f" - {row[0]}")

print("\nENUMS:")
cur.execute("SELECT t.typname, e.enumlabel FROM pg_type t JOIN pg_enum e ON t.oid = e.enumtypid JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace WHERE n.nspname = 'public';")
enums = {}
for row in cur.fetchall():
    enums.setdefault(row[0], []).append(row[1])
for k, v in enums.items():
    print(f" - {k}: {v}")

print("\nINDEXES:")
cur.execute("SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename != 'alembic_version';")
for row in cur.fetchall():
    print(f" - {row[0]}")
