# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Brand scoping helper shared by the social dashboard sources.

The agency module (social_marketing_agency) scopes customer data per brand.
These dashboard sources must show only the data the viewing user may see:

- customer (portal) users: only their commercial partner's brands
- agency users in brand focus: only the focused session brand
- everyone else: everything (no filter)
"""

from odoo.http import request


def brand_domain(model, brand_path="brand_id"):
    """Return a domain that scopes ``brand_path`` to the current user.

    ``model`` is the recordset of the queried model (e.g. ``env["social_marketing.post"]``)
    so the brand field path can be validated against the right model.

    ``brand_path`` is the dotted field path from the queried model to
    ``social.brand`` (e.g. ``"brand_id"`` or ``"account_id.brand_id"``).
    Returns an empty domain when the model has no brand field (the agency
    module is not installed) or when no brand scope applies.
    """
    if not _brand_path_resolves(model, brand_path):
        return []
    user = model.env.user
    if user.share:
        return [
            (brand_path + ".partner_id", "=",
             user.partner_id.commercial_partner_id.id)
        ]
    if request and request.session.get("social_brand_id"):
        return [(brand_path, "=", request.session["social_brand_id"])]
    return []


def _brand_path_resolves(model, brand_path):
    """Return True when the dotted ``brand_path`` resolves on ``model``."""
    current = model._name
    for part in brand_path.split("."):
        field = model.env["ir.model.fields"].sudo().search([
            ("model_id.model", "=", current), ("name", "=", part),
        ], limit=1)
        if not field:
            return False
        if field.ttype in ("many2one", "many2many", "one2many") and field.relation:
            current = field.relation
        else:
            break
    return True
