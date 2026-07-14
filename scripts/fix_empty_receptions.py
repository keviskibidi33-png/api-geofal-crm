"""
Script de Reparación de Recepciones con 0 Muestras.
Busca recepciones que tengan 0 muestras registradas en la base de datos,
descarga su Excel correspondiente desde Supabase Storage,
lo procesa con ExcelLogic para recuperar las muestras y las inserta.

Uso:
  python scripts/fix_empty_receptions.py --apply
"""
import sys
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

import os
import requests
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.modules.recepcion.models import RecepcionMuestra, MuestraConcreto
from app.modules.recepcion.excel import ExcelLogic
from app.modules.tracing.service import TracingService

def download_supabase_file(bucket: str, object_key: str) -> bytes:
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise Exception("Faltan las credenciales de Supabase en las variables de entorno.")
    
    url = f"{supabase_url}/storage/v1/object/{bucket}/{object_key}"
    headers = {"Authorization": f"Bearer {supabase_key}"}
    
    res = requests.get(url, headers=headers)
    if res.status_code != 200:
        raise Exception(f"Error descargando archivo de Supabase Storage: {res.status_code} - {res.text}")
    return res.content

def main():
    parser = argparse.ArgumentParser(description="Reparar muestras vacías de recepciones")
    parser.add_argument("--apply", action="store_true", help="Guardar los cambios en la base de datos.")
    parser.add_argument("--recepcion", type=str, default=None, help="Reparar un número de recepción específico.")
    args = parser.parse_args()

    db: Session = SessionLocal()
    excel_logic = ExcelLogic()

    try:
        # 1. Consultar recepciones con 0 muestras
        query = db.query(RecepcionMuestra)
        if args.recepcion:
            query = query.filter(RecepcionMuestra.numero_recepcion == args.recepcion)
        
        recepciones = query.all()
        repaired_count = 0
        
        for r in recepciones:
            muestras_actuales = db.query(MuestraConcreto).filter(MuestraConcreto.recepcion_id == r.id).count()
            if muestras_actuales > 0:
                # No requiere reparación
                continue
                
            print(f"\nProcesando Recepción ID: {r.id} | OT: {r.numero_ot} | N° Recepción: {r.numero_recepcion}")
            
            if not r.object_key or not r.bucket:
                print("[-] No tiene archivo Excel asociado en Supabase. Omitiendo.")
                continue
                
            print(f"[+] Descargando {r.object_key} desde bucket '{r.bucket}'...")
            try:
                excel_content = download_supabase_file(r.bucket, r.object_key)
            except Exception as e:
                print(f"[-] Error al descargar archivo: {e}")
                continue
                
            print("[+] Parseando Excel para extraer muestras...")
            try:
                parsed_data = excel_logic.parsear_recepcion(excel_content)
                muestras_data = parsed_data.get("muestras", [])
            except Exception as e:
                print(f"[-] Error parseando Excel: {e}")
                continue
                
            if not muestras_data:
                print("[-] No se encontraron muestras en el archivo Excel parseado.")
                continue
                
            print(f"[+] Se encontraron {len(muestras_data)} muestras en el Excel.")
            
            # Crear y vincular las muestras de concreto
            for i, m_dict in enumerate(muestras_data):
                m_dict["item_numero"] = i + 1
                
                # Valores por defecto para Control Probetas
                for field in ['elemento', 'fosa', 'densidad', 'status_ensayo', 'status_entrega', 'fecha_entrega']:
                    if not m_dict.get(field) or m_dict.get(field, '').strip() == '':
                        m_dict[field] = "-"
                        
                print(f"    -> Muestra {m_dict['item_numero']}: Lem {m_dict.get('codigo_muestra_lem')} | Ident: {m_dict.get('identificacion_muestra')} | F'c: {m_dict.get('fc_kg_cm2')}")
                
                if args.apply:
                    nueva_muestra = MuestraConcreto(recepcion_id=r.id, **m_dict)
                    db.add(nueva_muestra)
            
            if args.apply:
                db.flush()
                # Sincronizar trazabilidad del flujo
                TracingService.actualizar_trazabilidad(db, r.numero_recepcion)
                print("[+] Muestras y trazabilidad guardadas exitosamente.")
                repaired_count += 1
            else:
                print("[*] Modo Dry-Run. No se guardaron los cambios en BD.")

        if args.apply and repaired_count > 0:
            db.commit()
            print(f"\n[SUCCESS] Se repararon {repaired_count} recepciones de manera exitosa.")
        elif repaired_count == 0:
            print("\n[*] No se aplicaron cambios o no hubo recepciones para reparar.")
            
    except Exception as e:
        db.rollback()
        print(f"\n[FATAL] Ocurrió un error inesperado: {e}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    main()
