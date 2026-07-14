import zipfile
import re
import sys
sys.path.append('.')
from app.modules.common.excel_xml import find_template_path

path = find_template_path('Template_GranAgregado.xlsx')
with zipfile.ZipFile(path, 'r') as z:
    for name in z.namelist():
        if name.startswith('xl/worksheets/'):
            content = z.read(name).decode('utf-8', errors='ignore')
            # Look for <v>495</v> or <v>496</v> or <v>499</v>
            matches = re.findall(r'<c r="([^"]+)"[^>]*><v>(495|496|499)</v></c>', content)
            if matches:
                print(f'{name} matches: {matches}')
            # Also search for elements with t="s" and the value
            matches_s = re.findall(r'<c [^>]*r="([^"]+)"[^>]*t="s"[^>]*><v>(495|496|499)</v>', content)
            if matches_s:
                print(f'{name} matches_s: {matches_s}')
