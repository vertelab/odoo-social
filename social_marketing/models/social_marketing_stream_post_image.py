# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import models, fields


class SocialStreamAttachment(models.Model):
    """ A social_marketing.stream.post.image represents an image that was shared with a social_marketing.stream.post.
    It only contains the URL of the image on the related social_marketing.media. """

    _name = 'social_marketing.stream.post.image'
    _description = 'Social Stream Post Image Attachment'

    image_url = fields.Char("Image URL", readonly=True, required=True)
    stream_post_id = fields.Many2one('social_marketing.stream.post', string="Stream Post", ondelete="cascade")
