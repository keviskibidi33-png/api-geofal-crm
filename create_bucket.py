import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent / ".env")

from sqlalchemy import text
from app.database import engine

def create_storage_bucket():
    with engine.connect() as conn:
        try:
            # Create Bucket
            conn.execute(text("""
                INSERT INTO storage.buckets (id, name, public) 
                VALUES ('recepciones', 'recepciones', true) 
                ON CONFLICT (id) DO NOTHING;
            """))
            print("Bucket 'recepciones' created (or already exists).")
            
            # Create Policy (simplified)
            # Note: Creating policies via SQL might fail if not owner or superuser, 
            # but usually service_role key or postgres user (which we use in dev?) has rights.
            # RLS policies are tricky in raw SQL if they already exist.
            
            # Check if policy exists first? Or just try?
            # PostgreSQL doesn't have "CREATE POLICY IF NOT EXISTS" directly in all versions.
            # Best to wrap in DO block.
            
            conn.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_policies WHERE tablename = 'objects' AND policyname = 'Public Access Recepciones'
                    ) THEN
                        CREATE POLICY "Public Access Recepciones" ON storage.objects FOR ALL USING ( bucket_id = 'recepciones' );
                    END IF;
                END
                $$;
            """))
            print("Policy 'Public Access Recepciones' ensured.")

            conn.commit()
            
        except Exception as e:
            print(f"Error creating bucket/policy: {e}")

if __name__ == "__main__":
    create_storage_bucket()
