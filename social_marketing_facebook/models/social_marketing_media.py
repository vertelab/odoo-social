# -*- coding: utf-8 -*-
from odoo import api, fields, models

MEDIA_TYPE = 'facebook'


class SocialMediaFacebook(models.Model):
    _inherit = 'social_marketing.media'

    media_type = fields.Selection(selection_add=[('facebook', 'Facebook')])

    facebook_app_id = fields.Char('Facebook App ID')
    facebook_app_secret = fields.Char('Facebook App Secret')
    facebook_page_id = fields.Char('Facebook Page ID')
    facebook_page_access_token = fields.Char('Page Access Token')
