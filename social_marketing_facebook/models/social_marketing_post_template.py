# -*- coding: utf-8 -*-
from odoo import fields, models


class SocialMarketingPostTemplate(models.Model):
    _inherit = 'social_marketing.post.template'

    facebook_message = fields.Text('Facebook Message')
    facebook_image_ids = fields.Many2many('ir.attachment', string='Facebook Images',
        relation='social_marketing_post_template_facebook_image_ids_rel',
        column1='social_marketing_post_template_id', column2='ir_attachment_id')
