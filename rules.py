"""The handbook's purchasing rules, applied in code.

**Design-level defence.** The model does not decide. It extracts five facts
from a document; this module turns those facts into `recommend` /
`do_not_recommend` by looking the rest up in the handbook.

That matters because of what it removes. If the model emits the decision,
then every sentence in a hostile document is addressed to the thing that
makes the decision, and the only defence is that the model declines to be
persuaded. If the decision is computed here, a document can only influence it
by corrupting one of the five extracted values — a far smaller surface, and
one the caller cross-checks against the visible text. There is no argument,
however well phrased, that reaches this function. "Pre-approved by the
owner", "lead time waived", "supersedes the price above" — none of it is
input here. The inputs are five numbers and strings, and the handbook.

The checks are handbook section 4, in its order:

1. approved vendor — section 5 list; section 6 is always a fail
2. price — at or below the item's max unit cost in section 9
3. lead time — 21 days or less
4. minimum order — 600 units or less

An unknown fact fails its check. The handbook forbids guessing, and a check
that cannot be confirmed to pass has not passed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import tools
from models import Decision, DocumentFacts, FailedCheck, VendorAssessment


@dataclass(frozen=True)
class Check:
    name: FailedCheck
    passed: bool
    detail: str


def run_checks(facts: DocumentFacts) -> list[Check]:
    """The four section-4 checks, in handbook order."""
    checks: list[Check] = []

    # 1. Approved vendor
    if not facts.vendor:
        checks.append(Check("approved_vendor", False, "the document does not name a vendor"))
    else:
        status = tools.lookup_vendor(facts.vendor)
        if status is None:
            checks.append(Check(
                "approved_vendor", False,
                f"{facts.vendor} is not on the approved vendor list"))
        elif not status.approved:
            checks.append(Check(
                "approved_vendor", False,
                f"{status.name} is on the handbook's removed or pending vendor list"))
        else:
            checks.append(Check("approved_vendor", True, f"{status.name} is an approved vendor"))

    # 2. Price against the catalogue maximum
    item = tools.lookup_sku(facts.sku) if facts.sku else None
    if facts.unit_price is None:
        checks.append(Check("price", False, "the document does not state a unit price"))
    elif item is None or item.max_unit_cost is None:
        checks.append(Check(
            "price", False,
            f"{facts.sku or 'the SKU'} is not in the catalogue, so the price cannot be checked"))
    else:
        ok = facts.unit_price <= item.max_unit_cost
        checks.append(Check(
            "price", ok,
            "the quoted unit price is within our maximum for this item" if ok
            else "the quoted unit price is above our maximum for this item"))

    # 3. Lead time
    if facts.lead_time_days is None:
        checks.append(Check("lead_time", False, "the document does not state a lead time"))
    else:
        ok = facts.lead_time_days <= tools.MAX_LEAD_TIME_DAYS
        checks.append(Check(
            "lead_time", ok,
            f"the lead time of {facts.lead_time_days} days is within the "
            f"{tools.MAX_LEAD_TIME_DAYS}-day limit" if ok
            else f"the lead time of {facts.lead_time_days} days exceeds the "
                 f"{tools.MAX_LEAD_TIME_DAYS}-day limit"))

    # 4. Minimum order
    if facts.min_order is None:
        checks.append(Check("min_order", False, "the document does not state a minimum order"))
    else:
        ok = facts.min_order <= tools.MAX_MIN_ORDER_UNITS
        checks.append(Check(
            "min_order", ok,
            f"the minimum order of {facts.min_order} units is within the "
            f"{tools.MAX_MIN_ORDER_UNITS}-unit limit" if ok
            else f"the minimum order of {facts.min_order} units exceeds the "
                 f"{tools.MAX_MIN_ORDER_UNITS}-unit limit"))

    return checks


def decide(facts: DocumentFacts) -> VendorAssessment:
    """Facts in, assessment out. The handbook decides; nothing else can."""
    checks = run_checks(facts)
    failed = [c for c in checks if not c.passed]

    decision: Decision = "do_not_recommend" if failed else "recommend"
    failed_check: FailedCheck = failed[0].name if failed else "none"

    if failed:
        reason = f"The {failed[0].name.replace('_', '-')} check fails because {failed[0].detail}."
    else:
        reason = "The approved-vendor, price, lead-time, and minimum-order checks all pass."

    vendor_status = tools.lookup_vendor(facts.vendor) if facts.vendor else None

    data = facts.model_dump()
    notes = data.pop("notes", "")
    return VendorAssessment(
        **data,
        notes=notes,
        vendor_approved=None if vendor_status is None and not facts.vendor else bool(
            vendor_status and vendor_status.approved),
        decision=decision,
        failed_check=failed_check,
        reason=reason,
    )


# --------------------------------------------------------------------------
# Provenance: a fact must come from text a person could actually read
# --------------------------------------------------------------------------


def _numbers_in(text: str) -> set[str]:
    """Every number in the text, normalised so 21.80 and 21.8 compare equal."""
    out = set()
    for m in re.findall(r"\d[\d,]*(?:\.\d+)?", text):
        try:
            out.add(f"{float(m.replace(',', '')):g}")
        except ValueError:
            pass
    return out


def check_provenance(facts: DocumentFacts, doc: "tools.DocumentText") -> list[str]:
    """Reject any numeric fact that appears only in concealed text.

    The deterministic decision closes off argument, which leaves one way in:
    persuade the model to extract a *different number*. Every attack of that
    shape in this dataset puts the number somewhere a person cannot see — 0px
    type, white on white, an HTML part a mail client shows and a plain-text
    reader does not.

    So the value is checked against the text a reviewer could actually read.
    A figure present only in a concealed passage did not come from the quote;
    it came from whoever was hiding it, and the field is dropped rather than
    trusted. Dropping it makes its check fail, which is the safe direction.

    Returns a list of human-readable notes, and mutates `facts` in place.
    """
    if not doc.concealed:
        return []

    visible = _numbers_in(doc.visible_text)
    hidden = _numbers_in(" ".join(c.text for c in doc.concealed))
    notes: list[str] = []

    for field_name in ("unit_price", "lead_time_days", "min_order"):
        value = getattr(facts, field_name)
        if value is None:
            continue
        key = f"{float(value):g}"
        if key not in visible and key in hidden:
            setattr(facts, field_name, None)
            notes.append(
                f"{field_name} ({value}) was taken from a concealed passage and "
                f"does not appear in the text a reader can see — value rejected"
            )

    if facts.vendor:
        vis = doc.visible_text.lower()
        hid = " ".join(c.text for c in doc.concealed).lower()
        if facts.vendor.lower() not in vis and facts.vendor.lower() in hid:
            notes.append(
                f"vendor ({facts.vendor}) was named only in a concealed passage "
                f"— treated as unidentified"
            )
            facts.vendor = None

    return notes
