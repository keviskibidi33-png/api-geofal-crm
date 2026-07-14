import openpyxl

def inspect():
    p = "app/templates/informes/Informes agregado/Abra/Template_ABRA.xlsx"
    wb = openpyxl.load_workbook(p)
    ws = wb['FORMATO']
    print("--- Merged ranges for Template_ABRA.xlsx ---")
    for r in ws.merged_cells.ranges:
        print(r)

if __name__ == "__main__":
    inspect()
