# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import fields, models, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    instagram_use_own_account = fields.Boolean(
        "Use your own Instagram Account",
        config_parameter='social_marketing.instagram_use_own_account',
        help="Enable to use your own Facebook/Instagram Developer App instead of the shared one.")

    instagram_app_id = fields.Char(
        "Facebook App ID (for Instagram)",
        config_parameter='social_marketing.instagram_app_id',
        compute='_compute_instagram_app_id', inverse='_inverse_instagram_app_id')

    instagram_app_secret = fields.Char(
        "Facebook App Secret (for Instagram)",
        config_parameter='social_marketing.instagram_app_secret',
        compute='_compute_instagram_app_secret', inverse='_inverse_instagram_app_secret')

    @api.onchange('instagram_use_own_account')
    def _onchange_instagram_use_own_account(self):
        if not self.instagram_use_own_account:
            self.instagram_app_id = None
            self.instagram_app_secret = None

    def _compute_instagram_app_id(self):
        is_manager = self.env.user.has_group('social_marketing.group_social_marketing_manager')
        app_id = self.env['ir.config_parameter'].sudo().get_param('social_marketing.instagram_app_id')
        for setting in self:
            setting.instagram_app_id = app_id if is_manager else None

    def _inverse_instagram_app_id(self):
        for setting in self:
            if self.env.user.has_group('social_marketing.group_social_marketing_manager'):
                self.env['ir.config_parameter'].sudo().set_param(
                    'social_marketing.instagram_app_id', setting.instagram_app_id)

    def _compute_instagram_app_secret(self):
        is_manager = self.env.user.has_group('social_marketing.group_social_marketing_manager')
        secret = self.env['ir.config_parameter'].sudo().get_param('social_marketing.instagram_app_secret')
        for setting in self:
            setting.instagram_app_secret = secret if is_manager else None

    def _inverse_instagram_app_secret(self):
        for setting in self:
            if self.env.user.has_group('social_marketing.group_social_marketing_manager'):
                self.env['ir.config_parameter'].sudo().set_param(
                    'social_marketing.instagram_app_secret', setting.instagram_app_secret)
