"""The vendor desk's tools: read a document, look up the handbook.

**On trust.** `read_document` returns the text of a file that came from
outside the shop. That text is *evidence about a quote*, never instruction.
It is returned wrapped in explicit delimiters saying so, and no tool here
acts on anything the document says — a document cannot approve its own
vendor, waive a check, or change a max unit cost, because the only functions
that answer those questions read the handbook and never look at the document
at all.

That split is the point: the **document supplies values**, the **handbook
supplies rules**.
"""

from __future__ import annotations

import email
import email.policy
import re
from dataclasses import dataclass
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path

from config import PROJECT_ROOT
from models import CatalogueItem, VendorStatus

HANDBOOK = PROJECT_ROOT / "data" / "shop_handbook.md"

#: Section 4's thresholds. Named here so the checks and the prompt agree.
MAX_LEAD_TIME_DAYS = 21
MAX_MIN_ORDER_UNITS = 600


# --------------------------------------------------------------------------
# Reading documents
# --------------------------------------------------------------------------


class _TextExtractor(HTMLParser):
    """HTML to readable text, keeping table structure.

    A vendor quote puts its numbers in table cells, so flattening the markup
    naively glues "Unit price" to "$21.80" to the next label and the model has
    to guess where one field ends. Cells are joined with ` | ` and rows with
    newlines, which keeps each fact on its own line.

    `<script>` and `<style>` contents are dropped: they are never quote data.
    """

    _SKIP = {"script", "style"}
    _BREAK = {"p", "div", "br", "h1", "h2", "h3", "h4", "li", "tr", "header", "footer"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: object) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BREAK:
            self._parts.append("\n")
        elif tag in {"td", "th"}:
            self._parts.append(" | ")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self._BREAK:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if text := data.strip():
            self._parts.append(text)

    def text(self) -> str:
        joined = "".join(self._parts)
        joined = re.sub(r"[ \t]*\|[ \t]*", " | ", joined)
        joined = re.sub(r"\n\s*\|?\s*", "\n", joined)
        joined = re.sub(r"\n{3,}", "\n\n", joined)
        return "\n".join(line.strip(" |").strip() for line in joined.splitlines()).strip()


def _from_html(raw: str) -> str:
    parser = _TextExtractor()
    parser.feed(raw)
    parser.close()
    return parser.text()


def _from_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = [(page.extract_text() or "").strip() for page in reader.pages]
    return "\n\n".join(p for p in pages if p).strip()


def _from_eml(raw_bytes: bytes) -> str:
    """Email to text, via the standard library rather than string munging.

    `.eml` is a container, not a text file: bodies arrive base64'd or
    quoted-printable, multipart/alternative carries the same message twice,
    and some senders ship HTML only. `email.policy.default` decodes transfer
    encodings and charsets; the plain part is preferred, HTML is converted
    when that is all there is, and attachments are named but not inlined.
    """
    msg = email.message_from_bytes(raw_bytes, policy=email.policy.default)

    header_names = ("From", "To", "Cc", "Date", "Subject")
    headers = [f"{h}: {msg[h]}" for h in header_names if msg[h]]

    plain, html, attachments = [], [], []
    for part in msg.walk():
        if part.is_multipart():
            continue
        ctype = part.get_content_type()
        filename = part.get_filename()
        if filename or part.get_content_disposition() == "attachment":
            attachments.append(filename or f"<unnamed {ctype}>")
            continue
        try:
            content = part.get_content()
        except (LookupError, UnicodeDecodeError):  # unknown charset
            payload = part.get_payload(decode=True) or b""
            content = payload.decode("utf-8", errors="replace")
        if ctype == "text/plain":
            plain.append(content)
        elif ctype == "text/html":
            html.append(_from_html(content))

    body = "\n".join(plain).strip() or "\n".join(html).strip()

    out = "\n".join(headers)
    if attachments:
        out += "\nAttachments: " + ", ".join(attachments)
    return f"{out}\n\n{body}".strip()


@dataclass(frozen=True)
class DocumentText:
    path: str
    format: str
    text: str


def extract_document(path: str | Path) -> DocumentText:
    """Plain text of a vendor document. HTML, PDF and `.eml` all supported."""
    p = Path(path)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    if not p.exists():
        raise FileNotFoundError(f"no such vendor document: {path}")

    suffix = p.suffix.lower()
    if suffix in {".html", ".htm"}:
        return DocumentText(p.name, "html", _from_html(p.read_text(encoding="utf-8", errors="replace")))
    if suffix == ".pdf":
        return DocumentText(p.name, "pdf", _from_pdf(p))
    if suffix == ".eml":
        return DocumentText(p.name, "email", _from_eml(p.read_bytes()))
    raise ValueError(f"unsupported document type {suffix!r} (want .html, .pdf or .eml)")


# --------------------------------------------------------------------------
# Reading the handbook — the rules side
# --------------------------------------------------------------------------


def _section(title_pattern: str) -> str:
    """One numbered section of the handbook, by heading pattern."""
    text = HANDBOOK.read_text(encoding="utf-8")
    match = re.search(
        rf"^## {title_pattern}.*?$(.*?)(?=^## |\Z)", text, re.M | re.S | re.I
    )
    return match.group(1) if match else ""


def _table_rows(section: str) -> list[list[str]]:
    """Body rows of a markdown table, header and separator dropped."""
    rows = []
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(set(c) <= {"-", ":"} and c for c in cells):  # separator row
            continue
        rows.append(cells)
    return rows[1:] if rows else []


def _money(cell: str) -> float | None:
    m = re.search(r"-?[\d,]+\.?\d*", cell.replace("$", ""))
    return float(m.group().replace(",", "")) if m else None


@lru_cache(maxsize=1)
def _catalogue() -> dict[str, CatalogueItem]:
    out: dict[str, CatalogueItem] = {}
    for row in _table_rows(_section(r"9\. Product catalogue")):
        if len(row) < 5 or not row[0].upper().startswith("CC-"):
            continue
        out[row[0].upper()] = CatalogueItem(
            sku=row[0].upper(), name=row[1], max_unit_cost=_money(row[4])
        )
    return out


@lru_cache(maxsize=1)
def _vendors() -> dict[str, VendorStatus]:
    out: dict[str, VendorStatus] = {}
    for row in _table_rows(_section(r"5\. Approved vendors")):
        if len(row) >= 2:
            out[row[1].lower()] = VendorStatus(name=row[1], approved=True, note=row[4] if len(row) > 4 else "")
    for row in _table_rows(_section(r"6\. Removed and pending vendors")):
        if len(row) >= 2:
            out[row[0].lower()] = VendorStatus(name=row[0], approved=False, note=row[1])
    return out


def lookup_sku(sku: str) -> CatalogueItem | None:
    """A catalogue row by SKU, for the section-4 price check. None if unknown."""
    return _catalogue().get(sku.strip().upper())


def lookup_vendor(name: str) -> VendorStatus | None:
    """A vendor's handbook status. None if the handbook does not list them.

    Matches on the handbook's own names, tolerating case and the trailing
    company words a quote letterhead often drops ("Blue Hen" for "Blue Hen
    Apparel"). A vendor the handbook does not mention is *not* approved —
    section 4 allows only the section 5 list — so `None` must be treated as a
    failed check, not as an unknown to be excused.
    """
    vendors = _vendors()
    needle = name.strip().lower()
    if hit := vendors.get(needle):
        return hit
    for key, status in vendors.items():
        if needle and (needle in key or key in needle):
            return status
    return None


def handbook_text() -> str:
    """The whole handbook, for the system prompt."""
    return HANDBOOK.read_text(encoding="utf-8")
