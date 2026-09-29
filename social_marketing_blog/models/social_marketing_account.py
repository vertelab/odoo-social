# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SocialAccountBlog(models.Model):
    """Binds a blog channel to the website blog it publishes to and to the
    author articles are published under.

    Both fields are mandatory for a blog channel and meaningless for any
    other channel, so they are enforced by a constraint rather than by
    ``required=True`` (which would also demand them on LinkedIn accounts).
    """

    _inherit = 'social_marketing.account'

    blog_id = fields.Many2one(
        'blog.blog', string='Website Blog',
        help="The website blog this channel publishes articles to. "
             "Mandatory for a blog channel.")
    author_id = fields.Many2one(
        'res.partner', string='Author',
        default=lambda self: self.env.user.partner_id,
        help="The author articles are published under on this channel. "
             "Mandatory for a blog channel.")

    @api.constrains('blog_id', 'author_id', 'media_id')
    def _check_blog_channel_configuration(self):
        for account in self:
            if account.media_id.media_type != 'blog':
                continue
            if not account.blog_id or not account.author_id:
                raise ValidationError(_(
                    "A blog channel must have both a website blog and an "
                    "author. %s is missing one of them.", account.display_name))
