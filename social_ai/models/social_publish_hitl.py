# -*- coding: utf-8 -*-
"""Social publish HITL — record-baserad HITL för utåtgående social publicering.

Publicering sker ALDRIG automatiskt: Social Coach skapar utkast (state=draft)
och begär godkännande via ai.coworker.hitl (action_type='social_publish').
Vid godkänt beslut publiceras posten; vid avslag stannar den i draft.
"""

import json
import logging

from odoo import models

_logger = logging.getLogger(__name__)


def request_social_publish(coworker, post, user_id=None, risk_level='high'):
    """Begär HITL-godkännande för publicering av en social post.

    Returnerar ai.coworker.hitl-posten (state='asked').
    """
    return coworker._request_hitl(
        'social_publish',
        summary='Publicera social post: %s' % (post.display_name or post.id),
        context={'model': 'social_marketing.post', 'res_id': post.id},
        risk_level=risk_level,
        user_id=user_id,
    )


class AICoworkerHITLSocialPublish(models.Model):
    """ai.coworker.hitl — publicera social post vid godkänd social_publish-request."""
    _inherit = 'ai.coworker.hitl'

    def action_approve(self):
        res = super().action_approve()
        for rec in self:
            if rec.action_type == 'social_publish':
                rec._publish_social_post()
        return res

    def _publish_social_post(self):
        """Publicera posten vid ett godkänt social_publish-beslut.

        Vid avslag (eller annat icke-godkänt tillstånd) stannar posten i draft.
        """
        self.ensure_one()
        if self.state != 'approved':
            return False
        post = self._resolve_post()
        if not post:
            _logger.warning('social_publish: ingen post för request %s', self.id)
            return False
        try:
            post.sudo().write({
                'post_method': 'now',
                'scheduled_date': False,
            })
            post.sudo()._action_post()
            return True
        except Exception as e:
            _logger.warning('social_publish misslyckades (post %s): %s', post.id, e)
            return False

    def _resolve_post(self):
        """Hämta social_marketing.post från context (model/res_id)."""
        try:
            ctx = json.loads(self.context or '{}')
        except Exception:
            ctx = {}
        if ctx.get('model') == 'social_marketing.post' and ctx.get('res_id'):
            return self.env['social_marketing.post'].browse(
                ctx['res_id']).exists()
        return self.env['social_marketing.post'].browse()
