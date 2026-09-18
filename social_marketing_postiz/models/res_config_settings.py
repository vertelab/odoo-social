# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    postiz_api_url = fields.Char(
        'Postiz API URL',
        config_parameter='social_marketing_postiz.api_url',
        default='https://api.postiz.com',
        help='Base URL for Postiz API. Use https://api.postiz.com for cloud, '
             'or your self-hosted URL e.g. https://postiz.example.com')

    postiz_api_key = fields.Char(
        'Postiz API Key',
        config_parameter='social_marketing_postiz.api_key',
        help='Get your API key from Postiz: Settings → Developers → Public API')
