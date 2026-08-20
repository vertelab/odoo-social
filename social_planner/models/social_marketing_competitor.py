# -*- coding: utf-8 -*-
# Vertel AB AGPL-3

from odoo import _, api, fields, models


class SocialMarketingCompetitor(models.Model):
    """ Competitor analysis — track and compare competitor presence,
    growth and engagement on social media. """

    _name = 'social_marketing.competitor'
    _description = 'Competitor'
    _order = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('Competitor Name', required=True)
    active = fields.Boolean('Active', default=True)

    media_type = fields.Selection([
        ('linkedin', 'LinkedIn'),
        ('facebook', 'Facebook'),
        ('instagram', 'Instagram'),
        ('twitter', 'Twitter / X'),
        ('youtube', 'YouTube'),
        ('tiktok', 'TikTok'),
        ('other', 'Other'),
    ], string='Platform', required=True, default='linkedin')
    social_handle = fields.Char('Handle / URL')
    profile_url = fields.Char('Profile URL')

    follower_count = fields.Integer('Followers', readonly=True)
    follower_trend = fields.Float('Follower Trend %', digits=(3, 1), readonly=True)
    engagement_rate = fields.Float('Engagement Rate %', digits=(3, 2), readonly=True)
    avg_likes = fields.Integer('Avg Likes', readonly=True)
    avg_comments = fields.Integer('Avg Comments', readonly=True)
    avg_shares = fields.Integer('Avg Shares', readonly=True)
    post_frequency_weekly = fields.Float('Posts/Week', digits=(3, 1), readonly=True)

    competitor_type = fields.Selection([
        ('direct', 'Direct Competitor'),
        ('indirect', 'Indirect Competitor'),
        ('aspirational', 'Aspirational / Benchmark'),
        ('partner', 'Partner'),
    ], string='Type', default='direct', required=True)
    threat_level = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ], string='Threat Level', default='medium')
    description = fields.Text('Description')

    company_id = fields.Many2one('res.company', string='Company',
        default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', string='Analyst',
        default=lambda self: self.env.user)
    tag_ids = fields.Many2many('social_marketing.competitor.tag', string='Tags')

    snapshot_ids = fields.One2many('social_marketing.competitor.snapshot',
        'competitor_id', string='Snapshots')
    snapshot_count = fields.Integer('Snapshots', compute='_compute_snapshot_count')
    last_checked = fields.Datetime('Last Checked', readonly=True)
    top_content_theme = fields.Char('Top Content Theme', readonly=True)

    @api.depends('snapshot_ids')
    def _compute_snapshot_count(self):
        for comp in self:
            comp.snapshot_count = len(comp.snapshot_ids)

    def action_take_snapshot(self):
        self.ensure_one()
        vals = {
            'competitor_id': self.id,
            'follower_count': self.follower_count,
            'engagement_rate': self.engagement_rate,
            'avg_likes': self.avg_likes,
            'avg_comments': self.avg_comments,
            'avg_shares': self.avg_shares,
            'post_frequency_weekly': self.post_frequency_weekly,
        }
        self.env['social_marketing.competitor.snapshot'].create(vals)
        self.last_checked = fields.Datetime.now()

    def action_open_profile(self):
        """Open the competitor's profile URL in a new browser tab."""
        self.ensure_one()
        if not self.profile_url:
            raise UserError(_('No profile URL set for this competitor.'))
        return {
            'type': 'ir.actions.act_url',
            'url': self.profile_url,
            'target': 'new',
        }

    def action_compare(self):
        """Open the competitor list filtered to the same platform for comparison."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Competitors — %s' % self.media_type,
            'res_model': 'social_marketing.competitor',
            'view_mode': 'list,form',
            'domain': [('media_type', '=', self.media_type)],
            'target': 'current',
        }

    def action_update_metrics(self, follower_count=0, engagement_rate=0.0,
                               avg_likes=0, avg_comments=0, avg_shares=0,
                               post_frequency=0.0, top_theme=False):
        self.ensure_one()
        old_followers = self.follower_count
        self.write({
            'follower_count': follower_count,
            'follower_trend': ((follower_count - old_followers) / old_followers * 100) if old_followers else 0,
            'engagement_rate': engagement_rate,
            'avg_likes': avg_likes,
            'avg_comments': avg_comments,
            'avg_shares': avg_shares,
            'post_frequency_weekly': post_frequency,
            'top_content_theme': top_theme or self.top_content_theme,
            'last_checked': fields.Datetime.now(),
        })
        self.action_take_snapshot()


class SocialMarketingCompetitorTag(models.Model):
    _name = 'social_marketing.competitor.tag'
    _description = 'Competitor Tag'
    _order = 'name'

    name = fields.Char('Tag', required=True)
    color = fields.Integer('Color', default=0)


class SocialMarketingCompetitorSnapshot(models.Model):
    """ Historical snapshot of competitor metrics for trend analysis. """

    _name = 'social_marketing.competitor.snapshot'
    _description = 'Competitor Snapshot'
    _order = 'snapshot_date desc, id desc'
    _rec_name = 'snapshot_date'

    competitor_id = fields.Many2one('social_marketing.competitor',
        string='Competitor', required=True, ondelete='cascade')
    snapshot_date = fields.Datetime('Date', default=fields.Datetime.now, required=True)
    follower_count = fields.Integer('Followers')
    engagement_rate = fields.Float('Engagement Rate %', digits=(3, 2))
    avg_likes = fields.Integer('Avg Likes')
    avg_comments = fields.Integer('Avg Comments')
    avg_shares = fields.Integer('Avg Shares')
    post_frequency_weekly = fields.Float('Posts/Week', digits=(3, 1))
    notes = fields.Text('Notes')
    company_id = fields.Many2one(related='competitor_id.company_id', store=True)
