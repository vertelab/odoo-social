# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import fields, models


class SocialMediaBlog(models.Model):
    """Adds the blog as a selectable social media type.

    This is the channel definition, not the platform description: core
    already ships ``platform_blog`` on ``social_marketing.platform`` for the
    pre-flight publish rules. The two models are unrelated and their fields
    must not be copied across (``max_text_length`` on the platform is
    ``max_post_length`` on the media).
    """

    _inherit = 'social_marketing.media'

    media_type = fields.Selection(selection_add=[('blog', 'Blog')])
