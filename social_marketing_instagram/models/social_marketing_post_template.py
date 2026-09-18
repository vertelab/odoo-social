# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import api, fields, models


class SocialMarketingPostTemplate(models.Model):
    _inherit = 'social_marketing.post.template'

    instagram_message = fields.Html('Instagram Message', sanitize=True)
    instagram_image_ids = fields.Many2many('ir.attachment', string='Instagram Images',
        relation='social_marketing_post_template_instagram_image_ids_rel',
        column1='social_marketing_post_template_id', column2='ir_attachment_id')

    display_instagram_preview = fields.Boolean('Display Instagram Preview', compute='_compute_display_instagram_preview')
    instagram_preview = fields.Html('Instagram Preview', compute='_compute_instagram_preview')
    is_instagram = fields.Boolean(compute='_compute_is_instagram')

    @api.depends('platform_ids')
    def _compute_is_instagram(self):
        for post in self:
            post.is_instagram = 'instagram' in post.platform_ids.mapped('code')

    @api.depends('message', 'account_ids.media_id.media_type')
    def _compute_display_instagram_preview(self):
        for post in self:
            post.display_instagram_preview = (
                post.message_plain and
                'instagram' in post.account_ids.media_id.mapped('media_type'))

    @api.depends(lambda self: ['message', 'image_ids', 'display_instagram_preview'] + self._get_post_message_modifying_fields())
    def _compute_instagram_preview(self):
        for post in self:
            if not post.display_instagram_preview:
                post.instagram_preview = False
                continue

            image_urls = []
            if post.image_ids:
                image_urls = [
                    f'/web/image/{image._origin.id or image.id}'
                    for image in post.image_ids.sorted(lambda image: image._origin.id or image.id, reverse=True)
                ]

            post.instagram_preview = self.env['ir.qweb']._render('social_marketing_instagram.instagram_preview', {
                **post._prepare_preview_values("instagram"),
                'message': post._prepare_post_content(
                    post.message_plain,
                    'instagram',
                    **{field: post[field] for field in post._get_post_message_modifying_fields()}),
                'image_urls': image_urls,
            })
