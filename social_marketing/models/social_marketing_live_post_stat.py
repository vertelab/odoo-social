# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import fields, models


class SocialMarketingLivePostStat(models.Model):
    """ Post-level engagement snapshot (Serie B).

    Engagement metrics are captured at decreasing frequency as the post
    ages (the decay schedule) so the growth curve is preserved without
    unbounded row volume.
    """

    _name = 'social_marketing.live_post.stat'
    _description = 'Social Live Post Stat (Snapshot)'
    _order = 'date desc, id desc'

    live_post_id = fields.Many2one(
        'social_marketing.live.post', string='Live Post',
        required=True, ondelete='cascade', index=True)
    metric = fields.Selection([
        ('engagement', 'Engagement'),
        ('likes', 'Likes'),
        ('comments', 'Comments'),
        ('shares', 'Shares'),
    ], string='Metric', required=True)
    value = fields.Float('Value', required=True)
    date = fields.Date('Date', required=True, default=fields.Date.context_today)

    _sql_constraints = [
        ('live_post_metric_date_uniq',
         'UNIQUE(live_post_id, metric, date)',
         'Only one snapshot per metric per day per live post is allowed.'),
    ]
