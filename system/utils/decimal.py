
import re
from typing import Optional

def parse_number(text: str) -> Optional[float]:
    """Convierte una cadena con formato latino/europeo a float.
    Reglas:
      - extrae el primer "token numérico"
      - considera el ÚLTIMO separador (',' o '.') como separador decimal
      - elimina los otros separadores (miles)
    """
    if text is None:
        return None
    s = str(text)
    m = re.search(r"([-+]?\d[\d\.,]*)", s)
    if not m:
        return None
    tok = m.group(1)

    last_dot = tok.rfind('.')
    last_com = tok.rfind(',')

    # Elegimos el último como separador decimal
    if last_dot == -1 and last_com == -1:
        # Solo dígitos
        dec_sep = None
    elif last_dot > last_com:
        dec_sep = '.'
    else:
        dec_sep = ','

    # Elimina todo lo que no sea dígito o separador decimal elegido
    out_chars = []
    for i, ch in enumerate(tok):
        if ch.isdigit():
            out_chars.append(ch)
        elif dec_sep and ch == dec_sep:
            # conservar solo el primer decimal (el que corresponda al último separador real)
            out_chars.append('.')
            dec_sep = None  # ya reemplazado, ignora el resto
        # otros separadores se descartan

    try:
        return float(''.join(out_chars))
    except ValueError:
        return None
