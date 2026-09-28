# coding: utf-8
# Vertel Sverige AB AGPL-3

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    social_marketing_render_service_url = fields.Char(
        string='Render Service URL',
        config_parameter='social_marketing.render_service_url',
        help='Base URL of the Node render service for image templates, '
             'e.g. http://render-odoo:8600')

    social_marketing_render_service_token = fields.Char(
        string='Render Service Token',
        config_parameter='social_marketing.render_service_token',
        help='Bearer token used to authenticate render service calls. '
             'Stored via ir.config_parameter; set from pillar in production.')
