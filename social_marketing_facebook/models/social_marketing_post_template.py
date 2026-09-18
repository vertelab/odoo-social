# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import api, fields, models
from odoo.addons.mail.tools.link_preview import get_link_preview_from_url


class SocialMarketingPostTemplate(models.Model):
    _inherit = 'social_marketing.post.template'

    facebook_message = fields.Html('Facebook Message', sanitize=True)
    facebook_image_ids = fields.Many2many('ir.attachment', string='Facebook Images',
        relation='social_marketing_post_template_facebook_image_ids_rel',
        column1='social_marketing_post_template_id', column2='ir_attachment_id')

    display_facebook_preview = fields.Boolean('Display Facebook Preview', compute='_compute_display_facebook_preview')
    facebook_preview = fields.Html('Facebook Preview', compute='_compute_facebook_preview')

    @api.depends('message', 'account_ids.media_id.media_type')
    def _compute_display_facebook_preview(self):
        for post in self:
            post.display_facebook_preview = (
                post.message_plain and
                'facebook' in post.account_ids.media_id.mapped('media_type'))

    @api.depends(lambda self: ['message', 'image_ids', 'display_facebook_preview'] + self._get_post_message_modifying_fields())
    def _compute_facebook_preview(self):
        for post in self:
            if not post.display_facebook_preview:
                post.facebook_preview = False
                continue

            image_urls = []
            link_preview = {}
            if post.image_ids:
                image_urls = [
                    f'/web/image/{image._origin.id or image.id}'
                    for image in post.image_ids.sorted(lambda image: image._origin.id or image.id, reverse=True)
                ]
            elif url_in_message := self.env['social_marketing.post']._extract_url_from_message(post.message_plain):
                preview = get_link_preview_from_url(url_in_message) or {}
                link_preview['url'] = url_in_message
                if image_url := preview.get('og_image'):
                    image_urls.append(image_url)
                if title := preview.get('og_title'):
                    link_preview['title'] = title

            post.facebook_preview = self.env['ir.qweb']._render('social_marketing_facebook.facebook_preview', {
                **post._prepare_preview_values("facebook"),
                'message': post._prepare_post_content(
                    post.message_plain,
                    'facebook',
                    **{field: post[field] for field in post._get_post_message_modifying_fields()}),
                'image_urls': image_urls,
                'link_preview': link_preview,
            })
