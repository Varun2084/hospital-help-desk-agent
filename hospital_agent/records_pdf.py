"""Synthetic (nakli) medical documents ke liye chhota PDF banane wala, bina kisi extra library ke.

Sirf demo fixtures ke liye: asli hospital me prescription aur lab report hospital ka medical-record system
aur Lab Information System dete hain; dashboard wahi original document dikhata hai, model use nahin likhta.
"""


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


SYNTHETIC = "SYNTHETIC DEMO DOCUMENT - NOT A REAL MEDICAL RECORD"


def make_pdf(title: str, lines: list[str], footer: str = SYNTHETIC) -> bytes:
    """Ek page ka A4 PDF: upar title, phir lines, neeche footer. Text latin-1 me (PDF ke base font)."""
    ops = ["BT", "/F2 16 Tf", "50 790 Td", f"({_escape(title)}) Tj", "/F1 11 Tf", "0 -30 Td"]
    for line in lines:
        ops += [f"({_escape(line)}) Tj", "0 -18 Td"]
    ops += ["ET", "BT", "/F2 9 Tf", "50 40 Td", f"({_escape(footer)}) Tj", "ET"]
    stream = "\n".join(ops).encode("latin-1", "replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)
