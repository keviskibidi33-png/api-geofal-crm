from pathlib import Path

from app.utils.export_filename import build_filename_from_template


def write_report_export(
    output_dir: Path,
    template_filename: str,
    muestra: str,
    content: bytes,
) -> Path:
    output_path = output_dir / build_filename_from_template(template_filename, muestra)
    output_path.write_bytes(content)
    return output_path
