# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import fields, models

# The interaction types the unified inbox knows about. Declared here because
# the stream type is what tells us what a fetcher pulled: a stream that pulls
# comments produces comments, one that pulls direct messages produces direct
# messages. Nothing is guessed from the content of the item itself.
SOCIAL_INTERACTION_TYPES = [
    ('comment', 'Comment'),
    ('like', 'Like'),
    ('share', 'Share'),
    ('mention', 'Mention'),
    ('direct_message', 'Direct Message'),
    ('other', 'Other'),
]


class SocialStreamType(models.Model):
    """ Technical model that allows social module implementations ('social_marketing_facebook', 'social_marketing_twitter', ...)
    to introduce their own social stream types (eg: 'Page Posts' for Facebook, 'Keyword' for Twitter, ...) """

    _name = 'social_marketing.stream.type'
    _description = 'Social Stream Post'

    name = fields.Char("Name", readonly=True, required=True, translate=True)
    stream_type = fields.Char("Stream type name (technical)", readonly=True, required=True)
    media_id = fields.Many2one('social_marketing.media', string="Social Media", readonly=True, required=True)
    interaction_type = fields.Selection(
        SOCIAL_INTERACTION_TYPES, string="Interaction Type",
        default='other', required=True,
        help="What kind of incoming interaction this stream pulls. Stream "
             "posts created by the stream inherit it, which is how the inbox "
             "tells a comment from a direct message. Platform modules should "
             "declare it on their stream type data records; anything that "
             "does not declare it stays 'other'.")
