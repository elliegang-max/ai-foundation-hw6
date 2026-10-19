"""The structured types the vendor desk works in.

Two ideas shape these:

**Unknown is a value, not a blank.** The handbook forbids guessing a number
that the document does not state, so every extracted fact is optional and
`None` means "the document did not say". A missing price must survive to the
output rather than be filled in with a plausible one.

**The decision is a verdict on facts, not an opinion.** `Decision` is a closed
set of two, and `VendorAssessment` carries the four checks separately from the
decision they add up to — so a wrong answer can be traced to the check that
produced it rather than to the model's mood.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

#: The only two decisions the handbook allows (section 4).
Decision = Literal["recommend", "do_not_recommend"]

#: Which of the four section-4 checks a `do_not_recommend` turned on. `none`
#: is for a `recommend`, where no check failed.
FailedCheck = Literal["none", "approved_vendor", "price", "lead_time", "min_order"]


class DocumentFacts(BaseModel):
    """What the document itself says. Values only — no judgement.

    Everything is optional because the handbook's rule is explicit: if the
    document does not state a price, lead time, or minimum order, it is
    unknown, and inventing one is worse than reporting the gap.
    """

    vendor: str | None = Field(
        default=None,
        description="Vendor name exactly as the document gives it.",
    )
    sku: str | None = Field(
        default=None,
        description="Campus Customs SKU, e.g. CC-HD-006. None if not stated.",
    )
    unit_price: float | None = Field(
        default=None,
        description="Quoted unit price in dollars. None if not stated.",
    )
    lead_time_days: int | None = Field(
        default=None,
        description="Lead time in days. Convert weeks to days. None if not stated.",
    )
    min_order: int | None = Field(
        default=None,
        description="Minimum order in units. None if not stated.",
    )


class VendorAssessment(DocumentFacts):
    """The facts, plus the handbook's verdict on them.

    This is what the agent returns. It extends `DocumentFacts` so the extracted
    values and the judgement travel together, and the checks are recorded
    individually so a bad decision can be traced to the check that caused it.
    """

    vendor_approved: bool | None = Field(
        default=None,
        description=(
            "True if the vendor is on the handbook's approved list (section 5). "
            "False if on the removed or pending list (section 6). None if the "
            "vendor could not be identified at all."
        ),
    )
    decision: Decision = Field(
        description=(
            "'recommend' only if all four section-4 checks pass: approved "
            "vendor, unit price at or below the catalogue max, lead time 21 "
            "days or less, minimum order 600 units or less. Otherwise "
            "'do_not_recommend'."
        ),
    )
    failed_check: FailedCheck = Field(
        description=(
            "The check that decided a 'do_not_recommend'. 'none' for a "
            "'recommend'. Where several failed, name the first in handbook "
            "order: approved_vendor, price, lead_time, min_order."
        ),
    )
    reason: str = Field(
        description=(
            "One sentence naming the purchasing check that decided it, as "
            "handbook section 13 requires. No internal figures: never quote "
            "our max unit cost or margins, which section 4 keeps confidential."
        ),
    )

    def key_fields(self) -> dict[str, object]:
        """Just the six fields `data/practice_key.json` scores."""
        return {
            "vendor": self.vendor,
            "sku": self.sku,
            "unit_price": self.unit_price,
            "lead_time_days": self.lead_time_days,
            "min_order": self.min_order,
            "decision": self.decision,
        }


class CatalogueItem(BaseModel):
    """One row of the handbook's product catalogue (section 9)."""

    sku: str
    name: str
    max_unit_cost: float | None = None


class VendorStatus(BaseModel):
    """What the handbook says about a vendor (sections 5 and 6)."""

    name: str
    approved: bool
    note: str = ""
