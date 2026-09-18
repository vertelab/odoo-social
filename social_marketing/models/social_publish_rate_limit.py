# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import fields, models


class SocialPublishRateLimit(models.Model):
    """ Per-media publish rate limit (delay in seconds between jobs). """

    _name = 'social.publish.rate.limit'
    _description = 'Social Publish Rate Limit'

    media_id = fields.Many2one(
        'social_marketing.media', string='Media', required=True,
        ondelete='cascade', index=True)
    delay_seconds = fields.Float(
        'Delay (seconds)', default=1.0,
        help='Minimum delay between publish jobs for this media. '
             'Falls back to the global default setting when empty.')
