import psycopg2
import os
from dotenv import load_dotenv

def migrate():
    load_dotenv()
    dsn = os.getenv("QUOTES_DATABASE_URL")
    if not dsn:
        print("Error: QUOTES_DATABASE_URL not found")
        return

    try:
        conn = psycopg2.connect(dsn)
        conn.autocommit = False # Use transaction
        cur = conn.cursor()

        print("Starting migration (V2 - Using new table)...")

        # 1. Get current sequence value or max item_numero
        cur.execute("SELECT COALESCE(MAX(item_numero), 0) FROM programacion_servicios;")
        max_item = cur.fetchone()[0]
        print(f"Current max item_numero: {max_item}")

        # 2. Create the new sequence
        cur.execute(f"CREATE SEQUENCE IF NOT EXISTS programacion_lab_item_numero_seq START WITH {max_item + 1};")

        # 3. Create programacion_lab (Owned by postgres)
        print("Creating programacion_lab...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS programacion_lab (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                item_numero INTEGER NOT NULL DEFAULT nextval('programacion_lab_item_numero_seq'),
                recep_numero CHARACTER VARYING(20) NOT NULL,
                ot CHARACTER VARYING(20),
                codigo_muestra TEXT,
                fecha_recepcion DATE,
                fecha_inicio DATE,
                fecha_entrega_estimada DATE,
                cliente_nombre CHARACTER VARYING(255),
                descripcion_servicio TEXT,
                proyecto CHARACTER VARYING(255),
                entrega_real DATE,
                estado_trabajo CHARACTER VARYING(50) DEFAULT 'PENDIENTE',
                cotizacion_lab CHARACTER VARYING(50),
                autorizacion_lab CHARACTER VARYING(50),
                nota_lab TEXT,
                dias_atraso_lab INTEGER DEFAULT 0,
                motivo_dias_atraso_lab TEXT,
                evidencia_envio_recepcion TEXT,
                envio_informes TEXT,
                created_by UUID,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_by UUID,
                activo BOOLEAN DEFAULT TRUE
            );
        """)

        # 4. Create extension tables
        print("Creating extension tables...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS programacion_comercial (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                programacion_id UUID NOT NULL UNIQUE REFERENCES programacion_lab(id) ON DELETE CASCADE,
                fecha_solicitud_com DATE,
                fecha_entrega_com DATE,
                evidencia_solicitud_envio CHARACTER VARYING(10) DEFAULT 'NO',
                dias_atraso_envio_coti INTEGER DEFAULT 0,
                motivo_dias_atraso_com TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS programacion_administracion (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                programacion_id UUID NOT NULL UNIQUE REFERENCES programacion_lab(id) ON DELETE CASCADE,
                numero_factura CHARACTER VARYING(50),
                estado_pago CHARACTER VARYING(50),
                estado_autorizar CHARACTER VARYING(50),
                nota_admin TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """)

        # 5. Migrate all data
        print("Migrating records to programacion_lab...")
        cur.execute("""
            INSERT INTO programacion_lab (
                id, item_numero, recep_numero, ot, codigo_muestra, fecha_recepcion, fecha_inicio, 
                fecha_entrega_estimada, cliente_nombre, descripcion_servicio, proyecto, entrega_real, 
                estado_trabajo, cotizacion_lab, autorizacion_lab, nota_lab, dias_atraso_lab, 
                motivo_dias_atraso_lab, evidencia_envio_recepcion, envio_informes, 
                created_by, created_at, updated_at, updated_by, activo
            )
            SELECT 
                id, item_numero, recep_numero, ot, codigo_muestra, fecha_recepcion, fecha_inicio, 
                fecha_entrega_estimada, cliente_nombre, descripcion_servicio, proyecto, entrega_real, 
                estado_trabajo, cotizacion_lab, autorizacion_lab, nota_lab, dias_atraso_lab, 
                motivo_dias_atraso_lab, evidencia_envio_recepcion, envio_informes, 
                created_by, created_at, updated_at, updated_by, activo
            FROM programacion_servicios;
        """)

        print("Migrating records to programacion_comercial...")
        cur.execute("""
            INSERT INTO programacion_comercial (programacion_id, fecha_solicitud_com, fecha_entrega_com, evidencia_solicitud_envio, dias_atraso_envio_coti, motivo_dias_atraso_com)
            SELECT id, fecha_solicitud_com, fecha_entrega_com, evidencia_solicitud_envio, dias_atraso_envio_coti, motivo_dias_atraso_com
            FROM programacion_servicios;
        """)

        print("Migrating records to programacion_administracion...")
        cur.execute("""
            INSERT INTO programacion_administracion (programacion_id, numero_factura, estado_pago, estado_autorizar, nota_admin)
            SELECT id, numero_factura, estado_pago, estado_autorizar, nota_admin
            FROM programacion_servicios;
        """)

        # 6. Create View
        print("Creating view cuadro_control...")
        cur.execute("""
            CREATE OR REPLACE VIEW cuadro_control AS
            SELECT 
                l.*,
                c.fecha_solicitud_com,
                c.fecha_entrega_com,
                c.evidencia_solicitud_envio,
                c.dias_atraso_envio_coti,
                c.motivo_dias_atraso_com,
                a.numero_factura,
                a.estado_pago,
                a.estado_autorizar,
                a.nota_admin
            FROM programacion_lab l
            LEFT JOIN programacion_comercial c ON l.id = c.programacion_id
            LEFT JOIN programacion_administracion a ON l.id = a.programacion_id;
        """)

        # 7. Add Triggers to the NEW table
        print("Re-attaching operational triggers to programacion_lab...")
        cur.execute("""
            CREATE TRIGGER trigger_programacion_lab_updated
            BEFORE UPDATE ON programacion_lab
            FOR EACH ROW
            EXECUTE FUNCTION update_programacion_updated_at();

            CREATE TRIGGER trigger_calculate_dias_atraso_lab
            BEFORE INSERT OR UPDATE ON programacion_lab
            FOR EACH ROW
            EXECUTE FUNCTION calculate_dias_atraso();
        """)

        print("Creating extension triggers for new records...")
        cur.execute("""
            CREATE OR REPLACE FUNCTION public.create_programacion_extensions()
             RETURNS trigger
             LANGUAGE plpgsql
             AS $function$
             BEGIN
                 INSERT INTO public.programacion_comercial (programacion_id) VALUES (NEW.id);
                 INSERT INTO public.programacion_administracion (programacion_id) VALUES (NEW.id);
                 RETURN NEW;
             END;
             $function$;

            DROP TRIGGER IF EXISTS trigger_create_programacion_extensions ON programacion_lab;
            CREATE TRIGGER trigger_create_programacion_extensions
            AFTER INSERT ON programacion_lab
            FOR EACH ROW
            EXECUTE FUNCTION public.create_programacion_extensions();
        """)

        conn.commit()
        print("Migration V2 completed successfully!")

    except Exception as e:
        if 'conn' in locals() and conn:
            conn.rollback()
        print(f"Migration V2 failed: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    migrate()
