# -*- coding: utf-8 -*-
from odoo import fields, models


class SocialMarketingPost(models.Model):
    _inherit = 'social_marketing.post'

    facebook_image_ids = fields.Many2many('ir.attachment', string='Facebook Images',
        relation='social_marketing_post_facebook_image_ids_rel',
        column1='social_marketing_post_id', column2='ir_attachment_id')
