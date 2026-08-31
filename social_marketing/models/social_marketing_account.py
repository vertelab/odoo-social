# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import _, models, fields, api
from odoo.http import request

import logging
import time
import requests
from datetime import timedelta

from odoo.addons.social_marketing.models.social_marketing_provider_response import classify_response

_logger = logging.getLogger(__name__)


class SocialAccount(models.Model):
    """ A social_marketing.account represents an actual account on the related social_marketing.media.
    Ex: A Facebook Page or a Twitter Account.

    These social_marketing.accounts will then be used to send generic social_marketing.posts to multiple social_marketing.accounts.
    They are also used to display a 'dashboard' of statistics on the 'Feed' view.

    Account statistic fields are 'computed' manually through the _compute_statistics method
    that is overridden by each actual social module implementations (social_marketing_facebook, social_marketing_twitter, ...).
    The statistics computation is run manually when visualizing the Feed. """

    _name = 'social_marketing.account'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Social Account'

    def _get_default_company(self):
        """When the user is redirected to the callback URL of the different media,
        the company in the environment is always the company of the current user and not
        necessarily the selected company.

        So, before the authentication process, we store the selected company in the
        user session (see <social_marketing.media>::action_add_account) to be able to retrieve it
        here.
        """
        if request and 'social_marketing_company_id' in request.session:
            company_id = request.session['social_marketing_company_id']
            if not company_id:  # All companies
                return False
            if company_id in self.env.companies.ids:
                return company_id
        return self.env.company

    name = fields.Char('Name', required=True)
    active = fields.Boolean("Active", default=True)
    media_id = fields.Many2one('social_marketing.media', string="Social Media", required=True, readonly=True,
       help="Related Social Media (Facebook, Twitter, ...).", ondelete='cascade')
    media_type = fields.Selection(related='media_id.media_type')
    stats_link = fields.Char("Stats Link", compute='_compute_stats_link',
        help="Link to the external Social Account statistics")
    image = fields.Image("Image", max_width=128, max_height=128, readonly=True)
    is_media_disconnected = fields.Boolean('Link with external Social Media is broken')
    social_account_handle = fields.Char("Handle / Short Name",
                                        help="Contains the social media handle of the person that created this account. E.g: '@odoo.official' for the 'Odoo' X account")

    audience = fields.Integer("Audience", readonly=True,
        help="General audience of the Social Account (Page Likes, Account Follows, ...).")
    audience_trend = fields.Float("Audience Trend", readonly=True, digits=(3, 0),
        help="Percentage of increase/decrease of the audience over a defined period.")
    engagement = fields.Integer("Engagement", readonly=True,
        help="Number of people engagements with your posts (Likes, Comments, ...).")
    engagement_trend = fields.Float("Engagement Trend", readonly=True, digits=(3, 0),
        help="Percentage of increase/decrease of the engagement over a defined period.")
    stories = fields.Integer("Stories", readonly=True,
        help="Number of stories created from your posts (Shares, Re-tweets, ...).")
    stories_trend = fields.Float("Stories Trend", readonly=True, digits=(3, 0),
        help="Percentage of increase/decrease of the stories over a defined period.")
    has_trends = fields.Boolean("Has Trends?",
        help="Defines whether this account has statistics tends or not.")
    has_account_stats = fields.Boolean("Has Account Stats", default=True,
        help="""Defines whether this account has Audience/Engagements/Stories stats.
        Account with stats are displayed on the dashboard.""")
    utm_medium_id = fields.Many2one('utm.medium', string="UTM Medium", required=True, ondelete='restrict',
        help="Every time an account is created, a utm.medium is also created and linked to the account")
    company_id = fields.Many2one('res.company', 'Company', default=_get_default_company,
                                 domain=lambda self: [('id', 'in', self.env.companies.ids)],
                                 help="Link an account to a company to restrict its usage or keep empty to let all companies use it.")
    reach = fields.Integer("Reach", readonly=True,
        help="Number of unique people who saw any of the account's content.")
    impressions = fields.Integer("Impressions", readonly=True,
        help="Total number of times the account's content was displayed.")
    last_backfilled_date = fields.Date('Last Backfilled Date', readonly=True,
        help="Tracks the most recent date covered by the historical statistics backfill.")

    # --- Token health -------------------------------------------------
    # Social credentials expire. Without an expiry date and a warning ahead
    # of it, publishing simply stops one day with no visible cause.
    token_expiry_date = fields.Datetime(
        'Credentials Expire On', tracking=True,
        help="When the access token of this account expires. Set by the "
             "platform module at (re)authentication time.")
    token_expiry_state = fields.Selection([
        ('unknown', 'Unknown'),
        ('ok', 'Valid'),
        ('expiring', 'Expiring Soon'),
        ('expired', 'Expired'),
    ], string='Credentials Status', compute='_compute_token_expiry_state',
        store=True,
        help="Valid, expiring within the warning window, or already expired.")
    token_warning_sent_date = fields.Datetime(
        'Expiry Warning Sent', readonly=True, copy=False,
        help="When the last credentials expiry warning was raised. Prevents "
             "the cron from warning about the same expiry over and over.")

    def _compute_statistics(self):
        """ Every social module should override this method if it 'has_account_stats'.
        As the values depend on third party data, it's compute triggered manually that stores the data on the
        various stats fields (audience, engagement, stories) as well as related trends fields (if 'has_trends'). """
        pass

    def _compute_stats_link(self):
        """ Every social module should override this method.
        The 'stats_link' is an external link to the actual social_marketing.media statistics for this account.
        Ex: https://www.facebook.com/Odoo-Social-557894618055440/insights """
        for account in self:
            account.stats_link = False

    @api.depends('name')
    def _compute_display_name(self):
        """ ex: [Facebook] Odoo Social, [Twitter] Mitchell Admin, ... """
        for account in self:
            account.display_name = f"{account.name if account.name else ''}"

    @api.model_create_multi
    def create(self, vals_list):
        """Every account has a unique corresponding utm.medium for statistics
        computation purposes. This way, it will be possible to see every leads
        or quotations generated through a particular account."""

        if all(vals.get('media_id') and vals.get('name') for vals in vals_list):
            # as 'media_id' and 'name' are required fields, we will let the 'create' handle the error
            # if they are not present
            media_all = self.env['social_marketing.media'].search([('id', 'in', [vals.get('media_id') for vals in vals_list])])
            media_names = {
                social_marketing_media.id: social_marketing_media.name
                for social_marketing_media in media_all
            }

            medium_all = self.env['utm.medium'].create([{
                "name": "[%(media_name)s] %(account_name)s" % {
                    "media_name": media_names.get(vals['media_id']),
                    "account_name": vals['name']
                }
            } for vals in vals_list])

            for vals, medium in zip(vals_list, medium_all):
                vals['utm_medium_id'] = medium.id

        res = super(SocialAccount, self).create(vals_list)
        res._compute_statistics()
        return res

    def write(self, vals):
        """ If name is updated, reflect the change on medium_id (see #create method). """
        if vals.get('name'):
            for social_marketing_account in self.filtered(lambda social_marketing_account: social_marketing_account.utm_medium_id):
                social_marketing_account.utm_medium_id.write({
                    'name': "[%(media_name)s] %(account_name)s" % {
                        "media_name": social_marketing_account.media_id.name,
                        "account_name": vals['name']
                    }
                })

        return super(SocialAccount, self).write(vals)

    @api.model
    def refresh_statistics(self):
        """ Will re-compute the statistics of all active accounts. """
        all_accounts = self.env['social_marketing.account'].search([('has_account_stats', '=', True)]).sudo()
        # As computing the statistics is a recurring task, we ignore occasional "read timeouts"
        # from the third-party services, as it would most likely mean a temporary slow connection
        # and/or a slow response from their side.
        try:
            all_accounts._compute_statistics()
            all_accounts._snapshot_statistics()
            all_accounts._compute_snapshot_trends()
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            _logger.warning("Failed to refresh social account statistics.", exc_info=True)
        return [{
            'id': account.id,
            'name': account.name,
            'is_media_disconnected': account.is_media_disconnected,
            'audience': account.audience,
            'audience_trend': account.audience_trend,
            'engagement': account.engagement,
            'engagement_trend': account.engagement_trend,
            'stories': account.stories,
            'stories_trend': account.stories_trend,
            'has_trends': account.has_trends,
            'media_id': [account.media_id.id],
            'media_type': account.media_id.media_type,
            'stats_link': account.stats_link
        } for account in all_accounts]

    def _compute_trend(self, value, delta_30d):
        return 0.0 if value - delta_30d <= 0 else (delta_30d / (value - delta_30d)) * 100

    def _compute_trend_from_snapshots(self, metric, days=30):
        """Compute a metric trend from stored snapshots (no extra API fetch).

        Trend is ``(latest - past) / past * 100`` comparing the latest snapshot
        against the snapshot from ``days`` ago.
        """
        self.ensure_one()
        stat_model = self.env['social_marketing.account.stat']
        latest = stat_model.search([
            ('social_account_id', '=', self.id),
            ('metric', '=', metric),
        ], order='date desc', limit=1)
        if not latest:
            return 0.0
        past = stat_model.search([
            ('social_account_id', '=', self.id),
            ('metric', '=', metric),
            ('date', '<=', latest.date - timedelta(days=days)),
        ], order='date desc', limit=1)
        if not past or not past.value:
            return 0.0
        return (latest.value - past.value) / past.value * 100

    def _compute_snapshot_trends(self):
        """Populate the ``*_trend`` fields from stored snapshots."""
        for account in self:
            account.audience_trend = account._compute_trend_from_snapshots('audience')
            account.engagement_trend = account._compute_trend_from_snapshots('engagement')
            account.stories_trend = account._compute_trend_from_snapshots('stories')

    def _snapshot_statistics(self):
        """Append daily snapshots of the account's current metric values.

        Idempotent: the UNIQUE(social_account_id, metric, date) constraint plus a
        search-first write means a same-day re-run updates the row rather
        than duplicating it.
        """
        stat_model = self.env['social_marketing.account.stat']
        today = fields.Date.context_today(self)
        metrics = (
            ('audience', 'audience'),
            ('engagement', 'engagement'),
            ('stories', 'stories'),
            ('reach', 'reach'),
            ('impressions', 'impressions'),
        )
        for account in self:
            for metric, field_name in metrics:
                value = account[field_name]
                if value is False or value is None:
                    continue
                existing = stat_model.search([
                    ('social_account_id', '=', account.id),
                    ('metric', '=', metric),
                    ('date', '=', today),
                ], limit=1)
                if existing:
                    existing.write({'value': value})
                else:
                    stat_model.create({
                        'social_account_id': account.id,
                        'metric': metric,
                        'value': value,
                        'date': today,
                    })

    def _backfill_statistics(self, window_start, window_end):
        """Fetch historical statistics for a window — overridden per platform.

        Platform modules implement this to call their analytics API for the
        given (inclusive) date window and create ``social_marketing.account.stat``
        rows. The base implementation is a no-op.
        """
        pass

    def _backfill_get(self, url, params=None, headers=None, timeout=30):
        """GET helper for backfill with one rate-limit backoff retry.

        On a rate-limit response, waits ``retry_after`` (capped at 60s) and
        retries once. ``last_backfilled_date`` only advances on success, so a
        give-up here is still resumable on the next cron run.
        """
        for attempt in (1, 2):
            response = requests.get(url, params=params, headers=headers, timeout=timeout)
            classified = classify_response(response)
            if classified.has_exceeded_rate_limit() and attempt == 1:
                _logger.warning(
                    "Backfill rate-limited, backing off %s s.",
                    min(classified.retry_after, 60))
                time.sleep(min(classified.retry_after, 60))
                continue
            return response
        return response

    def _create_stat_snapshot(self, metric, value, date):
        """Find-or-create a single account.stat snapshot (idempotent)."""
        self.ensure_one()
        stat_model = self.env['social_marketing.account.stat']
        existing = stat_model.search([
            ('social_account_id', '=', self.id),
            ('metric', '=', metric),
            ('date', '=', date),
        ], limit=1)
        if existing:
            existing.write({'value': value})
        else:
            stat_model.create({
                'social_account_id': self.id,
                'metric': metric,
                'value': value,
                'date': date,
            })

    @api.model
    def _cron_backfill_statistics(self, retention_days=730, window_days=30):
        """One-time backfill across accounts, windowed oldest-first and resumable.

        Iterates 30-day windows per account, advancing ``last_backfilled_date``
        so an interrupted run resumes without duplicating completed windows.
        """
        accounts = self.search([('has_account_stats', '=', True)])
        end = fields.Date.today()
        for account in accounts:
            account._backfill_account_statistics(retention_days, window_days, end)

    def _backfill_account_statistics(self, retention_days, window_days, end):
        self.ensure_one()
        start = end - timedelta(days=retention_days)
        cursor = self.last_backfilled_date or start
        while cursor < end:
            window_end = min(cursor + timedelta(days=window_days), end)
            self._backfill_statistics(cursor, window_end)
            self.write({'last_backfilled_date': window_end})
            cursor = window_end

    def action_backfill_statistics(self, retention_days=730, window_days=30):
        """Manually trigger backfill for a single account (from the UI)."""
        self.ensure_one()
        self._backfill_account_statistics(
            retention_days, window_days, fields.Date.today())
        return True

    @api.model
    def _get_token_warning_days(self):
        """ How many days ahead of expiry a warning should be raised. """
        return int(self.env['ir.config_parameter'].sudo().get_param(
            'social_token_expiry_warning_days', '7'))

    @api.depends('token_expiry_date')
    def _compute_token_expiry_state(self):
        now = fields.Datetime.now()
        warning_days = self._get_token_warning_days()
        for account in self:
            if not account.token_expiry_date:
                account.token_expiry_state = 'unknown'
            elif account.token_expiry_date <= now:
                account.token_expiry_state = 'expired'
            elif account.token_expiry_date <= now + timedelta(days=warning_days):
                account.token_expiry_state = 'expiring'
            else:
                account.token_expiry_state = 'ok'

    def _notify_token_expiring(self):
        """ Raise a visible warning that these credentials are about to die.

        An activity plus a chatter message, not only a log line: the point is
        that somebody notices before publishing quietly stops.
        """
        activity_type = self.env.ref(
            'mail.mail_activity_data_todo', raise_if_not_found=False)
        for account in self:
            body = _(
                "The credentials of %(account)s expire on %(date)s. "
                "Renew them before then, otherwise publishing to this account "
                "will stop.",
                account=account.display_name,
                date=account.token_expiry_date)
            account.message_post(body=body)
            if activity_type:
                account.activity_schedule(
                    act_type_xmlid='mail.mail_activity_data_todo',
                    summary=_('Renew social credentials'),
                    note=body,
                    user_id=account._get_token_warning_user().id,
                )
            account.token_warning_sent_date = fields.Datetime.now()
        return self

    def _get_token_warning_user(self):
        """ Who should act on an expiring token. """
        self.ensure_one()
        manager = self.env.ref(
            'social_marketing.group_social_marketing_manager',
            raise_if_not_found=False)
        if manager and manager.users:
            return manager.users[0]
        return self.env.user

    @api.model
    def _cron_check_token_expiry(self):
        """ Warn about accounts whose credentials expire within the window.

        Only warns once per expiry: an account that was already warned about
        its current ``token_expiry_date`` is skipped, so the cron does not
        nag every day.
        """
        warning_days = self._get_token_warning_days()
        horizon = fields.Datetime.now() + timedelta(days=warning_days)
        candidates = self.search([
            ('token_expiry_date', '!=', False),
            ('token_expiry_date', '<=', horizon),
        ])
        to_warn = candidates.filtered(
            lambda account: not account.token_warning_sent_date
            or account.token_warning_sent_date < account._warning_window_start())
        if to_warn:
            to_warn._notify_token_expiring()
        return to_warn

    def _warning_window_start(self):
        """ Start of the warning window for this account's current expiry. """
        self.ensure_one()
        return self.token_expiry_date - timedelta(
            days=self._get_token_warning_days())

    def _filter_by_media_types(self, media_types):
        return self.filtered(lambda account: account.media_type in media_types)

    def _get_multi_company_error_message(self):
        """Return an error message if the social accounts information can not be updated by the current user."""
        if not self.env.user.has_group('base.group_multi_company'):
            return

        cids = request.httprequest.cookies.get('cids')
        if cids:
            allowed_company_ids = {int(cid) for cid in cids.split(',')}
        else:
            allowed_company_ids = {self.env.company.id}

        accounts_other_companies = self.filtered(
            lambda account: account.company_id and account.company_id.id not in allowed_company_ids)

        if accounts_other_companies:
            return _(
                'Create other accounts for %(media_names)s for this company or ask %(company_names)s to share their accounts',
                media_names=', '.join(accounts_other_companies.mapped('media_id.name')),
                company_names=', '.join(accounts_other_companies.mapped('company_id.name')),
            )

    def _action_disconnect_accounts(self, disconnection_info=None):
        _logger.warning("Social account disconnected: %s. Reason: %s",
                        ", ".join(self.mapped("display_name")),
                        disconnection_info or "Not provided",
                        stack_info=True)
        self.sudo().write({'is_media_disconnected': True})
