# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import api, fields, models


class SocialMediaPostiz(models.Model):
    _inherit = 'social_marketing.media'

    postiz_provider = fields.Char('Postiz Provider',
        help="Provider identifier used in Postiz API payloads. "
             "e.g. 'linkedin', 'linkedin-page', 'instagram', 'facebook', 'x', "
             "'youtube', 'tiktok', 'pinterest', 'threads', 'bluesky', 'reddit', "
             "'discord', 'slack', 'telegram', 'medium', 'devto', 'wordpress'.")
