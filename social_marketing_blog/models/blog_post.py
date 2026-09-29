# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import fields, models


class BlogPostBlogChannel(models.Model):
    """Links a website article back to the live post that published it.

    Added by this bridge, never by ``website_blog`` itself: the field exists
    only while the bridge is installed, and uninstalling it drops the column.
    The marker is what makes publication idempotent — a retried dispatch
    finds the article through it instead of creating a second one.
    """

    _inherit = 'blog.post'

    social_live_post_id = fields.Many2one(
        'social_marketing.live.post', string='Social Live Post',
        copy=False, ondelete='cascade', index=True,
        help="The social marketing live post this article was published from.")

    _sql_constraints = [
        ('social_live_post_id_uniq', 'UNIQUE(social_live_post_id)',
         'This live post has already been published as a blog article.'),
    ]
