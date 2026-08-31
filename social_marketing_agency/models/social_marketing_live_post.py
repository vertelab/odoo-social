# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, fields, models


class SocialLivePost(models.Model):
    """Brand-aware live post: enforces the per-brand publishing killswitch."""

    _inherit = 'social_marketing.live.post'

    brand_id = fields.Many2one(
        'social.brand', string='Brand', related='post_id.brand_id',
        store=True, index=True)

    def _check_publish_allowed(self):
        """Refuse to publish while the post's brand has publishing paused.

        Checked here rather than only in the interface, so a post that was
        already queued before the killswitch was flipped is still stopped.
        Scoped strictly to the post's own brand: every other brand keeps
        publishing.
        """
        allowed, reason = super()._check_publish_allowed()
        if not allowed:
            return allowed, reason

        brand = self.post_id.brand_id
        if brand and brand.publishing_paused:
            return False, _(
                "Publishing is paused for brand %(brand)s%(reason)s.",
                brand=brand.name,
                reason=': %s' % brand.publishing_paused_reason
                if brand.publishing_paused_reason else '')
        return True, ''
