# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import fields, models


class SocialMarketingAccountStat(models.Model):
    """ Daily snapshot of account-level metrics (Serie A).

    Account statistics are recorded as time-series snapshots so trends and
    growth curves can be computed from stored history instead of from
    single values that are overwritten on every refresh.
    """

    _name = 'social_marketing.account.stat'
    _description = 'Social Account Stat (Snapshot)'
    _order = 'date desc, id desc'

    social_account_id = fields.Many2one(
        'social_marketing.account', string='Social Account',
        required=True, ondelete='cascade', index=True, oldname='account_id')
    metric = fields.Selection([
        ('audience', 'Audience'),
        ('engagement', 'Engagement'),
        ('stories', 'Stories'),
        ('reach', 'Reach'),
        ('impressions', 'Impressions'),
    ], string='Metric', required=True)
    value = fields.Float('Value', required=True)
    date = fields.Date('Date', required=True, default=fields.Date.context_today)
    company_id = fields.Many2one('res.company', related='social_account_id.company_id', store=True)

    _sql_constraints = [
        ('account_metric_date_uniq',
         'UNIQUE(social_account_id, metric, date)',
         'Only one snapshot per metric per day per account is allowed.'),
    ]
