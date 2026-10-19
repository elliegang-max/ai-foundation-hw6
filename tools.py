"""The vendor desk's tools: read a document, look up the handbook.

**On trust.** `extract_document` returns the text of a file that came from
outside the shop. That text is *evidence about a quote*, never instruction.
No function here acts on anything the document says — a document cannot
approve its own vendor, waive a check, or change a max unit cost, because the
only functions that answer those questions read the handbook and never look
at the document at all.

That split is the point: the **document supplies values**, the **handbook
supplies rules**.

**Code-level defence: concealment is surfaced, not resolved.** A reviewer
opening a quote sees what a browser, PDF viewer or mail client *draws*. This
reader sees what the file *contains*. Text can be in the file and not on the
screen, and that gap is where an injection hides. So the reader computes both
views, and any passage present in one and not the other is labelled in place
rather than silently dropped or silently included:

- **HTML** — `display:none`, `visibility:hidden`, font size ≤ 1px,
  `opacity:0`, text the colour of the page, **and comments**, which a naive
  reader drops and a regex tag-strip passes through.
- **PDF** — text drawn in the paper colour, or in invisible render mode.
- **Email** — the `text/html` alternative a mail client shows but a
  plain-text-preferring reader never reads.
- **Zero-width characters**, which hide a word from a keyword filter while
  leaving it legible to a model.

Nothing is thrown away: the model is told a passage was concealed and from
whom, and the prompt tells it what that means. `defenses=False` restores the
old silent behaviour for the undefended comparison.
"""

from __future__ import annotations

import email
import email.policy
import re
import zlib
from dataclasses import dataclass, field
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path

from config import PROJECT_ROOT
from models import CatalogueItem, VendorStatus

HANDBOOK = PROJECT_ROOT / "data" / "shop_handbook.md"

#: Section 4's thresholds. Named here so the checks and the prompt agree.
MAX_LEAD_TIME_DAYS = 21
MAX_MIN_ORDER_UNITS = 600

#: Invisible to a reader, invisible to a naive filter, legible to a model.
ZERO_WIDTH = {0x200B, 0x200C, 0x200D, 0xFEFF, 0x00AD, 0x2060}

#: Treated as the page/paper colour when deciding whether text is readable.
PAGE_BACKGROUND = {"#ffffff", "#fff", "white"}


def strip_zero_width(s: str) -> str:
    return "".join(c for c in s if ord(c) not in ZERO_WIDTH)


def count_zero_width(s: str) -> int:
    return sum(1 for c in s if ord(c) in ZERO_WIDTH)


@dataclass
class Concealed:
    """A passage in the file that a person reading it normally cannot see."""

    how: str
    where: str
    text: str


def _hidden_by(style: str) -> str | None:
    """Why this inline style hides its element from a reader, or None."""
    s = style.lower().replace(" ", "")
    if "display:none" in s:
        return "display:none"
    if "visibility:hidden" in s:
        return "visibility:hidden"
    if m := re.search(r"font-size:(\d+(?:\.\d+)?)(px|pt)?", s):
        if float(m.group(1)) <= 1:
            return f"font-size:{m.group(1)}{m.group(2) or ''}"
    if re.search(r"opacity:0(?:\.0+)?(?![\d.])", s):
        return "opacity:0"
    if m := re.search(r"color:(#[0-9a-f]{3,6}|white)", s):
        if m.group(1) in PAGE_BACKGROUND:
            return f"color:{m.group(1)} (page background)"
    return None


# --------------------------------------------------------------------------
# Reading documents
# --------------------------------------------------------------------------


class _HTMLReader(HTMLParser):
    """HTML to text, keeping table structure and tracking what is concealed.

    A vendor quote puts its numbers in table cells, so flattening the markup
    naively glues "Unit price" to "$21.80" to the next label. Cells are joined
    with ` | ` and rows with newlines, which keeps each fact on its own line.

    `<script>` and `<style>` are dropped outright — never quote data, never
    painted. Everything else is kept, and sorted into visible and concealed.
    """

    DROP = {"script", "style"}
    BREAK = {"p", "div", "br", "h1", "h2", "h3", "h4", "li", "tr", "header", "footer"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.concealed: list[Concealed] = []
        self._drop = 0
        self._hide: list[str] = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        reason = _hidden_by(d.get("style", "")) if d.get("style") else None
        if tag in self.DROP:
            self._drop += 1
        elif reason:
            self._hide.append(reason)
            self.concealed.append(Concealed(reason, f"<{tag} style>", ""))
        elif tag in self.BREAK:
            self.parts.append("\n")
        elif tag in {"td", "th"}:
            self.parts.append(" | ")

    def handle_endtag(self, tag):
        if tag in self.DROP and self._drop:
            self._drop -= 1
        elif self._hide and tag not in self.DROP:
            self._hide.pop()
        elif tag in self.BREAK:
            self.parts.append("\n")

    def handle_comment(self, data):
        if text := data.strip():
            self.concealed.append(Concealed("HTML comment", "<!-- -->", text))

    def handle_data(self, data):
        if self._drop:
            return
        if not (text := data.strip()):
            return
        if self._hide:
            self.concealed[-1].text += text
        else:
            self.parts.append(text)

    def visible(self) -> str:
        j = "".join(self.parts)
        j = re.sub(r"[ \t]*\|[ \t]*", " | ", j)
        j = re.sub(r"\n\s*\|?\s*", "\n", j)
        j = re.sub(r"\n{3,}", "\n\n", j)
        return "\n".join(l.strip(" |").strip() for l in j.splitlines()).strip()


def _read_html(raw: str) -> tuple[str, list[Concealed]]:
    r = _HTMLReader()
    r.feed(raw)
    r.close()
    return r.visible(), [c for c in r.concealed if c.text]


def _read_pdf(path: Path) -> tuple[str, list[Concealed]]:
    """PDF text, split by whether it is drawn in a colour a reader can see.

    pypdf's `extract_text` returns everything regardless of fill colour, so
    white-on-white text arrives looking exactly like body copy. The content
    stream is walked directly to tell them apart.
    """
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    visible: list[str] = []
    hidden: list[str] = []
    invisible_mode = False

    for page in reader.pages:
        raw = page.get_contents().get_data()
        try:
            raw = zlib.decompress(raw)
        except Exception:
            pass
        s = raw.decode("latin-1")
        fill = "0 0 0"
        mode_invisible = False
        for tok in re.finditer(
            r"([\d.]+ [\d.]+ [\d.]+)\s+rg|([\d.]+)\s+g|(\d)\s+Tr|\((.*?)\)\s*Tj", s
        ):
            if tok.group(1):
                fill = tok.group(1)
            elif tok.group(2):
                fill = " ".join([tok.group(2)] * 3)
            elif tok.group(3):
                mode_invisible = tok.group(3) == "3"
                invisible_mode |= mode_invisible
            elif tok.group(4) is not None:
                text = tok.group(4).replace("\\(", "(").replace("\\)", ")")
                white = all(abs(float(x) - 1.0) < 1e-6 for x in fill.split())
                (hidden if (white or mode_invisible) else visible).append(text)

    concealed = []
    if hidden:
        how = "invisible text render mode (3 Tr)" if invisible_mode else "white text on white paper"
        concealed.append(Concealed(how, "PDF content stream", " ".join(hidden)))

    if not visible and not hidden:  # unusual encoding — fall back
        return "\n\n".join((p.extract_text() or "").strip() for p in reader.pages).strip(), []
    return "\n".join(visible).strip(), concealed


def _read_eml(raw_bytes: bytes) -> tuple[str, list[Concealed]]:
    """Email to text, via the standard library rather than string munging.

    `.eml` is a container, not a text file: bodies arrive base64'd or
    quoted-printable, `multipart/alternative` carries the message twice, and
    some senders ship HTML only.

    **The alternative parts are compared, not just picked from.** A mail
    client shows the `text/html` part; a plain-text-preferring reader shows
    the other one. When they differ, whatever is in the HTML and not in the
    plain text is content the agent would never otherwise see — and that is
    exactly where an attacker puts things.
    """
    msg = email.message_from_bytes(raw_bytes, policy=email.policy.default)

    headers = [f"{h}: {msg[h]}" for h in ("From", "To", "Cc", "Date", "Subject") if msg[h]]
    plain: list[str] = []
    html_src: list[str] = []
    attachments: list[str] = []

    for part in msg.walk():
        if part.is_multipart():
            continue
        ctype = part.get_content_type()
        if part.get_filename() or part.get_content_disposition() == "attachment":
            attachments.append(part.get_filename() or f"<unnamed {ctype}>")
            continue
        try:
            content = part.get_content()
        except (LookupError, UnicodeDecodeError):
            content = (part.get_payload(decode=True) or b"").decode("utf-8", errors="replace")
        if ctype == "text/plain":
            plain.append(content)
        elif ctype == "text/html":
            html_src.append(content)

    concealed: list[Concealed] = []
    html_visible = ""
    if html_src:
        html_visible, html_concealed = _read_html("\n".join(html_src))
        concealed.extend(html_concealed)

    plain_text = "\n".join(plain).strip()
    if plain_text and html_visible:
        # Anything the HTML shows that the plain part does not.
        flat = strip_zero_width(plain_text).lower()
        extra = [
            line for line in html_visible.splitlines()
            if (s := strip_zero_width(line).strip()) and s.lower() not in flat
        ]
        if extra:
            concealed.append(
                Concealed(
                    "present only in the text/html alternative",
                    "multipart/alternative",
                    " ".join(extra),
                )
            )
        body = plain_text
    else:
        body = plain_text or html_visible

    out = "\n".join(headers)
    if attachments:
        out += "\nAttachments: " + ", ".join(attachments)
    return f"{out}\n\n{body}".strip(), concealed


@dataclass
class DocumentText:
    path: str
    format: str
    #: What a person reading the file normally would see.
    visible_text: str
    #: Passages present in the file but not on a reader's screen.
    concealed: list[Concealed] = field(default_factory=list)
    #: Zero-width characters found and removed.
    zero_width_removed: int = 0

    @property
    def text(self) -> str:
        """Everything, with concealed passages labelled where they sit.

        Concealment is not removed — removing it would hide an attack from the
        model as effectively as it hides one from a reviewer, and the two
        passages this reader used to drop are exactly the two attacks the agent
        was never tested against.
        """
        out = self.visible_text
        for c in self.concealed:
            out += (
                f"\n\n[CONCEALED PASSAGE — present in the file but NOT visible "
                f"to a person reading it: hidden by {c.how}, in {c.where}]\n"
                f"{c.text}\n[END CONCEALED PASSAGE]"
            )
        if self.zero_width_removed:
            out += (
                f"\n\n[NOTE — {self.zero_width_removed} zero-width character(s) "
                f"were embedded in this document's text and have been removed. "
                f"They are invisible to a reader and defeat keyword matching; "
                f"their presence is deliberate obfuscation.]"
            )
        return out

    @property
    def raw_text(self) -> str:
        """Visible and concealed run together, unlabelled — the undefended view."""
        return "\n".join([self.visible_text, *(c.text for c in self.concealed)]).strip()


def extract_document(path: str | Path, *, defenses: bool = True) -> DocumentText:
    """Plain text of a vendor document. HTML, PDF and `.eml` all supported.

    With `defenses=True` concealed passages are detected and labelled. With
    `defenses=False` nothing is labelled, comments are dropped, and the
    `text/plain` part of an email wins outright — the behaviour this reader
    had before the concealment work, kept for the undefended comparison.
    """
    p = Path(path)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    if not p.exists():
        raise FileNotFoundError(f"no such vendor document: {path}")

    suffix = p.suffix.lower()
    if suffix in {".html", ".htm"}:
        fmt = "html"
        visible, concealed = _read_html(p.read_text(encoding="utf-8", errors="replace"))
    elif suffix == ".pdf":
        fmt = "pdf"
        visible, concealed = _read_pdf(p)
    elif suffix == ".eml":
        fmt = "email"
        visible, concealed = _read_eml(p.read_bytes())
    else:
        raise ValueError(f"unsupported document type {suffix!r} (want .html, .pdf or .eml)")

    zw = count_zero_width(visible) + sum(count_zero_width(c.text) for c in concealed)
    visible = strip_zero_width(visible)
    for c in concealed:
        c.text = strip_zero_width(c.text)

    if not defenses:
        # The old behaviour: comments and white PDF text dropped, the HTML
        # alternative ignored, nothing labelled.
        dropped = {"HTML comment", "present only in the text/html alternative"}
        concealed = [c for c in concealed if c.how not in dropped and fmt != "pdf"]
        return DocumentText(p.name, fmt, visible, concealed, 0)

    return DocumentText(p.name, fmt, visible, concealed, zw)


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
