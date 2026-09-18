# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

import logging
import time

import requests

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class SocialLivePost(models.Model):
    """ A social 'live' post, as opposed to a social_marketing.post, represents a post that is
    actually on a social_marketing.account instance.

    Basically, a social_marketing.post that is posted on 4 social_marketing.accounts will create 4 instances
    of the social.live.post. """

    _name = 'social_marketing.live.post'
    _description = 'Social Live Post'

    post_id = fields.Many2one('social_marketing.post', string="Social Post", required=True, readonly=True, ondelete="cascade")
    social_account_id = fields.Many2one('social_marketing.account', string="Social Account", required=True, readonly=True, ondelete="cascade", oldname='account_id')
    message = fields.Char('Message', compute='_compute_message',
        help="Content of the social_marketing.post message that is post-processed (links are shortened, UTMs, ...)")
    live_post_link = fields.Char('Post Link', compute='_compute_live_post_link',
        help="Link of the live post on the target media.")
    failure_reason = fields.Text('Failure Reason', readonly=True,
        help="""The reason why a post is not successfully posted on the Social Media (eg: connection error, duplicated post, ...).""")
    state = fields.Selection([
        ('ready', 'Ready'),
        ('posting', 'Posting'),
        ('posted', 'Posted'),
        ('failed', 'Failed')],
        string='Status', default='ready', required=True, readonly=True,
        help="""Most social.live.posts directly go from Ready to Posted/Failed since they result of a single call to the third party API.
        A 'Posting' state is also available for those that are sent through batching (like push notifications).""")
    engagement = fields.Integer("Engagement", help="Number of people engagements with the post (Likes, comments...)")
    likes = fields.Integer("Likes", readonly=True, help="Number of likes/reactions on the post.")
    comments = fields.Integer("Comments", readonly=True, help="Number of comments on the post.")
    shares = fields.Integer("Shares", readonly=True, help="Number of shares/reposts of the post.")
    company_id = fields.Many2one('res.company', 'Company', related='social_account_id.company_id')

    @api.depends(lambda self:
        ['post_id.message', 'post_id.message_plain', 'post_id.utm_campaign_id', 'social_account_id.media_type', 'social_account_id.utm_medium_id', 'post_id.source_id'] +
        ['post_id.%s' % field for field in self.env['social_marketing.post']._get_post_message_modifying_fields()])
    def _compute_message(self):
        """ Prepares the message of the parent post, and shortens links to contain UTM data. """
        for live_post in self:
            message = self.env['mail.render.mixin'].sudo()._shorten_links_text(
                live_post.post_id.message_plain,
                live_post._get_utm_values())

            live_post.message = self.env['social_marketing.post']._prepare_post_content(
                message,
                live_post.social_account_id.media_type,
                **{field: live_post.post_id[field] for field in self.env['social_marketing.post']._get_post_message_modifying_fields()})

    @api.depends('social_account_id.media_id')
    def _compute_live_post_link(self):
        for live_post in self:
            live_post.live_post_link = False

    @api.depends('state', 'social_account_id')
    def _compute_display_name(self):
        """ ex: [Facebook] Odoo Social: posted, [Twitter] Mitchell Admin: failed, ... """
        state_description_values = dict(self._fields['state']._description_selection(self.env))
        for live_post in self:
            live_post.display_name = f'{live_post.social_account_id.display_name}: {state_description_values.get(live_post.state)}'

    @api.model_create_multi
    def create(self, vals_list):
        res = super(SocialLivePost, self).create(vals_list)
        res.mapped('post_id')._check_post_completion()
        return res

    def write(self, vals):
        res = super(SocialLivePost, self).write(vals)
        if vals.get('state'):
            self.mapped('post_id')._check_post_completion()
        return res

    def action_retry_post(self):
        self._post()

    @api.model
    def refresh_statistics(self):
        # as refreshing the statistics is a recurring task, we ignore occasional "read timeouts"
        # from the third party services, as it would most likely mean a temporary slow connection
        # and/or a slow response from their side
        try:
            live_posts = self.env['social_marketing.live.post']
            live_posts._refresh_statistics()
            live_posts._snapshot_engagement()
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            _logger.warning("Failed to refresh the live post statistics.", exc_info=True)

    def _refresh_statistics(self):
        """ Every social module should override this method.

        This is the method responsible for fetching the post data per social media.

        It will be called manually every time we need to refresh the social_marketing.stream data:
            - social.stream creation/edition
            - 'Feed' kanban loading
            - 'Refresh' button on 'Feed' kanban
            - ...
        """
        pass

    def _snapshot_gap_days(self, age_days):
        """Return the minimum snapshot gap (in days) for a post of the given age.

        Decay schedule: daily for the first week, weekly for days 8-90,
        monthly after day 90.
        """
        if age_days <= 7:
            return 1
        if age_days <= 90:
            return 7
        return 30

    def _snapshot_engagement(self):
        """Append engagement snapshots for posts that are due per the decay schedule.

        Idempotent via UNIQUE(live_post_id, metric, date) and a search-first
        check against the most recent snapshot.
        """
        stat_model = self.env['social_marketing.live_post.stat']
        today = fields.Date.context_today(self)
        now = fields.Datetime.now()
        for live_post in self:
            published = live_post.post_id.published_date or live_post.create_date
            if not published:
                continue
            age_days = (fields.Datetime.from_string(now) - fields.Datetime.from_string(published)).days
            gap = live_post._snapshot_gap_days(age_days)
            last = stat_model.search([
                ('live_post_id', '=', live_post.id),
                ('metric', '=', 'engagement'),
            ], order='date desc', limit=1)
            if last and (fields.Date.from_string(today) - last.date).days < gap:
                continue
            values = {
                'engagement': live_post.engagement,
                'likes': live_post.likes,
                'comments': live_post.comments,
                'shares': live_post.shares,
            }
            for metric, value in values.items():
                if value is False or value is None:
                    continue
                existing = stat_model.search([
                    ('live_post_id', '=', live_post.id),
                    ('metric', '=', metric),
                    ('date', '=', today),
                ], limit=1)
                if existing:
                    existing.write({'value': value})
                else:
                    stat_model.create({
                        'live_post_id': live_post.id,
                        'metric': metric,
                        'value': value,
                        'date': today,
                    })

    def _post(self):
        """ Every social module should override this method.
        This will make the actual post on the related social_marketing.account through the third party API """
        pass

    def _get_utm_values(self):
        self.ensure_one()

        post_id = self.post_id
        return {
            'campaign_id': post_id.utm_campaign_id.id,
            'medium_id': self.social_account_id.utm_medium_id.id,
            'source_id': post_id.source_id.id,
        }

    def _filter_by_media_types(self, media_types):
        return self.filtered(lambda post: post.social_account_id.media_id.media_type in media_types)

    # ------------------------------------------------------------------
    # Job-queue dispatch (publishing pipeline)
    # ------------------------------------------------------------------

    def _get_rate_limit_delay(self):
        """ Delay (seconds) to respect before publishing.

        Uses the per-media override (social.publish.rate.limit) when it
        exists, otherwise the global default
        social_publish_rate_limit_delay_seconds (default 1.0). """
        self.ensure_one()
        media = self.social_account_id.media_id
        if media:
            limit = self.env['social.publish.rate.limit'].search(
                [('media_id', '=', media.id)], limit=1)
            if limit:
                return limit.delay_seconds
        return float(self.env['ir.config_parameter'].get_param(
            'social_publish_rate_limit_delay_seconds', '1.0'))

    def _dispatch_post(self, step_id=None):
        """ Publish the live post (called by the queue_job worker).

        :param step_id: id of the dispatched pipeline step to update. """
        self.ensure_one()
        step = self.env['social.publish.pipeline.step'].browse(step_id) \
            if step_id else self.env['social.publish.pipeline.step']

        delay = self._get_rate_limit_delay()
        if delay > 0:
            time.sleep(delay)

        try:
            self._post()
        except Exception as exc:  # noqa: BLE001 - retry via queue_job
            _logger.exception("Live post %s failed during dispatch", self.id)
            self.write({'state': 'failed', 'failure_reason': str(exc)[:250]})
            if step:
                step.write({
                    'state': 'failed',
                    'stage': 'failed',
                    'result': str(exc)[:1000],
                })
            raise
        else:
            if step:
                step.write({
                    'state': 'done',
                    'stage': 'published',
                    'result': _('published'),
                })
            # live_post.write already triggers _check_post_completion when the
            # provider sets state='posted'; call it explicitly for robustness.
            self.post_id._check_post_completion()
            return True
