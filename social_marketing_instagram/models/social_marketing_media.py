# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SocialMediaInstagram(models.Model):
    _inherit = 'social_marketing.media'

    media_type = fields.Selection(selection_add=[('instagram', 'Instagram')])

    instagram_business_account_id = fields.Char('Instagram Business Account ID')
    instagram_access_token = fields.Char('Instagram Access Token')
