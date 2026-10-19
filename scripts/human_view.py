"""Render each vendor document the way a person would see it, and diff that
against what the agent's reader actually extracted.

The point is the gap. A reviewer opens a quote in a browser, a PDF viewer or a
mail client and sees what those applications *draw*. The agent's reader sees
what the file *contains*. Text can be in the file and not on the screen, and
that gap is where an injection hides.

How "what a person sees" is computed per format:

- **HTML** — drop `<script>`, `<style>` and comments (a browser never paints
  them), then drop any element whose inline style makes it invisible:
  `display:none`, `visibility:hidden`, a font size of 0 or 1px, opacity 0, or
  a text colour equal to the page background.
- **PDF** — walk the content stream tracking the fill colour, and keep only
  text drawn in a colour that is not the paper colour. Invisible text render
  mode (`3 Tr`) is dropped too.
- **Email** — take the part a mail client displays. For
  `multipart/alternative` that is the **HTML** part, not the plain one, and
  the HTML rules above then apply to it.

Zero-width characters are stripped before comparison, since they are invisible
to a reader and to most keyword filters but not to a model.
"""

from __future__ import annotations

import email
import email.policy
import json
import re
import sys
import zlib
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tools  # noqa: E402
from config import PROJECT_ROOT  # noqa: E402

DOCS = PROJECT_ROOT / "data" / "practice_docs"
OUT = PROJECT_ROOT / "output" / "human_view.json"

ZERO_WIDTH = {0x200B, 0x200C, 0x200D, 0xFEFF, 0x00AD, 0x2060}
PAGE_BACKGROUND = {"#ffffff", "#fff", "white"}


def strip_zero_width(s: str) -> str:
    return "".join(c for c in s if ord(c) not in ZERO_WIDTH)


def _invisible(style: str) -> str | None:
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
            return f"color:{m.group(1)} on white"
    return None


class _HumanHTML(HTMLParser):
    """Visible text only, plus a record of everything concealed."""

    DROP = {"script", "style"}
    BREAK = {"p", "div", "br", "h1", "h2", "h3", "li", "tr", "header", "footer"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.visible: list[str] = []
        self.hidden: list[dict] = []
        self._drop = 0
        self._hide: list[str] = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        reason = _invisible(d.get("style", "")) if d.get("style") else None
        if tag in self.DROP:
            self._drop += 1
        elif reason:
            self._hide.append(reason)
            self.hidden.append({"how": reason, "tag": tag, "text": ""})
        elif tag in self.BREAK:
            self.visible.append("\n")
        elif tag in {"td", "th"}:
            self.visible.append(" | ")

    def handle_endtag(self, tag):
        if tag in self.DROP and self._drop:
            self._drop -= 1
        elif self._hide and tag not in self.DROP:
            # closing the hidden element (approximate: these docs don't nest)
            self._hide.pop()
        elif tag in self.BREAK:
            self.visible.append("\n")

    def handle_comment(self, data):
        self.hidden.append({"how": "HTML comment", "tag": "<!---->", "text": data.strip()})

    def handle_data(self, data):
        text = data.strip()
        if not text or self._drop:
            return
        if self._hide:
            self.hidden[-1]["text"] += text
        else:
            self.visible.append(text)

    def text(self) -> str:
        j = "".join(self.visible)
        j = re.sub(r"\n\s*\|?\s*", "\n", re.sub(r"[ \t]*\|[ \t]*", " | ", j))
        return "\n".join(l.strip(" |").strip() for l in j.splitlines() if l.strip(" |").strip())


def human_html(raw: str):
    p = _HumanHTML()
    p.feed(raw)
    p.close()
    return p.text(), [h for h in p.hidden if h["text"]]


def human_pdf(path: Path):
    raw = __import__("pypdf").PdfReader(str(path)).pages[0].get_contents().get_data()
    try:
        raw = zlib.decompress(raw)
    except Exception:
        pass
    s = raw.decode("latin-1")
    cur, visible, hidden, hidden_fill = "0 0 0", [], [], None
    for tok in re.finditer(r"([\d.]+ [\d.]+ [\d.]+)\s+rg|([\d.]+)\s+g|\((.*?)\)\s*Tj", s):
        if tok.group(1):
            cur = tok.group(1)
        elif tok.group(2):
            cur = " ".join([tok.group(2)] * 3)
        elif tok.group(3) is not None:
            text = tok.group(3).replace("\\(", "(").replace("\\)", ")")
            if all(abs(float(x) - 1.0) < 1e-6 for x in cur.split()):
                hidden.append(text)
                hidden_fill = cur  # the fill the hidden run was drawn in
            else:
                visible.append(text)
    h = [{"how": f"white text on white paper (fill `{hidden_fill} rg`)",
          "tag": "pdf", "text": " ".join(hidden)}] if hidden else []
    return "\n".join(visible), h


def human_eml(path: Path):
    msg = email.message_from_bytes(path.read_bytes(), policy=email.policy.default)
    parts = {}
    for part in msg.walk():
        if part.is_multipart():
            continue
        try:
            parts[part.get_content_type()] = part.get_content()
        except Exception:
            pass
    headers = [f"{h}: {msg[h]}" for h in ("From", "To", "Date", "Subject") if msg[h]]
    # A mail client prefers the HTML alternative when there is one.
    if "text/html" in parts:
        body, hidden = human_html(parts["text/html"])
        shown = "text/html (what a mail client displays)"
    else:
        body, hidden = parts.get("text/plain", ""), []
        shown = "text/plain (the only body part)"
    return "\n".join(headers) + "\n\n" + body, hidden, shown


def main() -> None:
    report = {}
    for p in sorted(DOCS.iterdir()):
        agent_text = strip_zero_width(tools.extract_document(p).text)
        shown = None
        if p.suffix == ".html":
            human, hidden = human_html(p.read_text(encoding="utf-8"))
            shown = "rendered HTML"
        elif p.suffix == ".pdf":
            human, hidden = human_pdf(p)
            shown = "rendered PDF page"
        else:
            human, hidden, shown = human_eml(p)
        human = strip_zero_width(human)

        # Which concealed strings actually reached the agent?
        for h in hidden:
            probe = strip_zero_width(h["text"])[:60]
            h["reached_the_agent"] = bool(probe) and probe in agent_text

        report[p.name] = {
            "what_a_person_sees_via": shown,
            "human_visible_text": human,
            "agent_extracted_text": agent_text,
            "concealed_passages": hidden,
            "agent_saw_text_a_person_cannot": any(h["reached_the_agent"] for h in hidden),
        }

    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"{'document':34}{'concealed':>10}{'reached agent':>15}  how")
    for name, r in report.items():
        hid = r["concealed_passages"]
        reached = sum(1 for h in hid if h["reached_the_agent"])
        how = "; ".join(sorted({h["how"] for h in hid})) or "—"
        print(f"{name:34}{len(hid):>10}{reached:>15}  {how}")
    print(f"\nwrote {OUT.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
