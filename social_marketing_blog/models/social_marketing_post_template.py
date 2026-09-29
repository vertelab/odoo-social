# -*- coding: utf-8 -*-
# Vertel Sverige AGPL-3

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SocialPostTemplateBlog(models.Model):
    """Adds the article title a blog channel needs.

    Declared on the template so ``social_marketing.post`` inherits it. The
    field is optional in general and only required once the post actually
    targets a blog channel: existing network-only posts legitimately have no
    title.
    """

    _inherit = 'social_marketing.post.template'

    title = fields.Char(
        'Title',
        help="Article title. Required for blog channels, where it becomes the "
             "title of the published article.")

    targets_blog_channel = fields.Boolean(
        'Targets a Blog Channel',
        compute='_compute_targets_blog_channel',
        help="Whether any selected channel publishes to the local blog. Used "
             "to show the title field only when it is meaningful.")

    @api.depends('account_ids', 'account_ids.media_id',
                 'account_ids.media_id.media_type')
    def _compute_targets_blog_channel(self):
        for post in self:
            post.targets_blog_channel = 'blog' in post.account_ids.mapped(
                'media_id.media_type')

    @api.constrains('title', 'account_ids')
    def _check_title_for_blog_target(self):
        for post in self:
            if post.targets_blog_channel and not post.title:
                raise ValidationError(_(
                    "A title is required when publishing to a blog channel: "
                    "it becomes the title of the published article."))
