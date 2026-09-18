# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import models, api, fields
from odoo.addons.mail.tools.link_preview import get_link_preview_from_url


class SocialPostTemplate(models.Model):
    _inherit = 'social_marketing.post.template'

    display_linkedin_preview = fields.Boolean('Display LinkedIn Preview', compute='_compute_display_linkedin_preview')
    linkedin_preview = fields.Html('LinkedIn Preview', compute='_compute_linkedin_preview')

    # LinkedIn publishing settings (audience, comments, brand partnership, media)
    linkedin_audience = fields.Selection([
        ('public', 'Everyone (Public)'),
        ('connections', 'Connections only'),
        ('group', 'A specific group'),
    ], string='LinkedIn Audience', default='public')
    linkedin_group_urn = fields.Char(
        'LinkedIn Group URN',
        help="URN of the LinkedIn group to post to when audience is a group, "
             "e.g. 'urn:li:group:12345'.")
    linkedin_comments = fields.Selection([
        ('anyone', 'Anyone'),
        ('connections', 'Connections only'),
        ('off', 'Off (no comments)'),
    ], string='LinkedIn Comments', default='anyone')
    linkedin_brand_partnership = fields.Boolean(
        'LinkedIn Brand Partnership',
        help="Mark the post as a brand partnership (paid partnership label).")
    linkedin_media_type = fields.Selection([
        ('image', 'Image'),
        ('video', 'Video'),
    ], string='LinkedIn Media Format', default='image')
    linkedin_image_width = fields.Integer('LinkedIn Image Width (px)', default=1200)
    linkedin_image_height = fields.Integer('LinkedIn Image Height (px)', default=627)
    is_linkedin = fields.Boolean(compute='_compute_is_linkedin')

    @api.depends('platform_ids')
    def _compute_is_linkedin(self):
        for post in self:
            post.is_linkedin = 'linkedin' in post.platform_ids.mapped('code')

    @api.depends('message', 'account_ids.media_id.media_type')
    def _compute_display_linkedin_preview(self):
        for post in self:
            post.display_linkedin_preview = (
                post.message_plain and
                'linkedin' in post.account_ids.media_id.mapped('media_type'))

    @api.depends(lambda self: ['message', 'image_ids', 'display_linkedin_preview'] + self._get_post_message_modifying_fields())
    def _compute_linkedin_preview(self):
        for post in self:
            if not post.display_linkedin_preview:
                post.linkedin_preview = False
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

            post.linkedin_preview = self.env['ir.qweb']._render('social_marketing_linkedin.linkedin_preview', {
                **post._prepare_preview_values("linkedin"),
                'message': post._prepare_post_content(
                    post.message_plain,
                    'linkedin',
                    **{field: post[field] for field in post._get_post_message_modifying_fields()}),
                'image_urls': image_urls,
                'link_preview': link_preview,
            })
