# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

import hashlib
import logging
import time
from datetime import timedelta

import requests

from odoo import _, api, fields, models, SUPERUSER_ID
from odoo.exceptions import UserError

from odoo.addons.social_marketing.models.social_marketing_provider_response import (
    classify_response,
)

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
        ('failed', 'Failed'),
        ('retracted', 'Retracted')],
        string='Status', default='ready', required=True, readonly=True,
        help="""Most social.live.posts directly go from Ready to Posted/Failed since they result of a single call to the third party API.
        A 'Posting' state is also available for those that are sent through batching (like push notifications).""")
    engagement = fields.Integer("Engagement", help="Number of people engagements with the post (Likes, comments...)")
    likes = fields.Integer("Likes", readonly=True, help="Number of likes/reactions on the post.")
    comments = fields.Integer("Comments", readonly=True, help="Number of comments on the post.")
    shares = fields.Integer("Shares", readonly=True, help="Number of shares/reposts of the post.")
    company_id = fields.Many2one('res.company', 'Company', related='social_account_id.company_id')

    # --- Idempotency -------------------------------------------------
    # Derived from (post, account), never random: the same post for the
    # same account always yields the same key, so a retried or
    # double-triggered dispatch collides on the unique index instead of
    # publishing twice.
    idempotency_key = fields.Char(
        'Idempotency Key', compute='_compute_idempotency_key',
        store=True, precompute=True, readonly=True, index=True,
        help="Stable key derived from the post and the account. Guarantees "
             "that a post can only be published once per account.")

    # --- Retry / backoff ---------------------------------------------
    attempt_count = fields.Integer(
        'Attempts', default=0, readonly=True,
        help="Number of publishing attempts made so far.")
    max_attempts = fields.Integer(
        'Max Attempts', default=lambda self: self._default_max_attempts(),
        help="Publishing is abandoned once this many attempts have failed.")
    next_retry_date = fields.Datetime(
        'Next Retry', readonly=True,
        help="When the next publishing attempt is due. Empty when no further "
             "attempt is scheduled.")
    failure_category = fields.Selection([
        ('transient', 'Transient'),
        ('permanent', 'Permanent'),
    ], string='Failure Type', readonly=True,
        help="Transient failures (network, HTTP 5xx, rate limited) are "
             "retried with an increasing delay. Permanent ones (revoked "
             "auth, rejected content) stop immediately.")

    # --- Platform identity (needed to retract) ------------------------
    platform_post_id = fields.Char(
        'Platform Post ID', readonly=True, copy=False,
        help="Identifier of the published item on the platform. Required to "
             "retract the post afterwards.")
    permalink = fields.Char(
        'Permalink', readonly=True, copy=False,
        help="Public URL of the published item on the platform.")

    _sql_constraints = [
        ('idempotency_key_uniq', 'UNIQUE(idempotency_key)',
         'This post has already been published to this account.'),
    ]

    @api.model
    def _default_max_attempts(self):
        return int(self.env['ir.config_parameter'].sudo().get_param(
            'social_publish_max_attempts', '5'))

    @api.depends('post_id', 'social_account_id')
    def _compute_idempotency_key(self):
        for live_post in self:
            post_id = live_post.post_id.id or live_post.post_id._origin.id
            account_id = (live_post.social_account_id.id
                          or live_post.social_account_id._origin.id)
            if not post_id or not account_id:
                live_post.idempotency_key = False
                continue
            live_post.idempotency_key = live_post._build_idempotency_key(
                post_id, account_id)

    @api.model
    def _build_idempotency_key(self, post_id, account_id):
        """Stable key for a (post, account) pair."""
        raw = 'social_marketing.post:%s|social_marketing.account:%s' % (
            post_id, account_id)
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()

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

    def _check_publish_allowed(self):
        """ Hook: may this live post go out right now?

        Returns ``(allowed, reason)``. The base implementation always allows
        publishing; ``social_marketing_agency`` overrides it to enforce the
        per-brand publishing killswitch. Enforced at dispatch and not only in
        the UI, so an already-queued job for a paused brand is stopped too. """
        self.ensure_one()
        return True, ''

    def _block_publishing(self, reason, step=None):
        """ Record a live post that was refused before reaching the platform. """
        self.ensure_one()
        self.write({
            'state': 'failed',
            'failure_reason': reason[:250],
            'failure_category': 'permanent',
            'next_retry_date': False,
        })
        if step:
            step.write({
                'state': 'failed',
                'stage': 'failed',
                'result': reason[:1000],
            })
        else:
            self.post_id._pipeline_log(
                'failed', state='failed', result=reason[:1000],
                live_post_id=self)
        self.post_id._check_post_completion()

    def _classify_failure(self, exception):
        """ Return 'transient' or 'permanent' for a publishing exception.

        Classification of the provider response itself is delegated to
        ``social_marketing_provider_response.classify_response``; this method
        only maps that verdict onto the retry decision.

        Transient: network errors, HTTP 5xx, rate limiting.
        Permanent: revoked or expired auth, and any other 4xx (rejected
        content, malformed request), which retrying cannot fix.
        """
        if isinstance(exception, (requests.exceptions.ConnectionError,
                                  requests.exceptions.Timeout)):
            return 'transient'

        response = getattr(exception, 'response', None)
        if response is None:
            # No provider response to classify: nothing says a retry would
            # behave differently, so do not hammer the platform.
            return 'permanent'

        classified = classify_response(response)
        if classified.has_exceeded_rate_limit():
            return 'transient'
        if classified.is_unauthorized():
            return 'permanent'

        status_code = getattr(response, 'status_code', 0) or 0
        if status_code >= 500:
            return 'transient'
        return 'permanent'

    def _get_retry_delay_seconds(self, attempt):
        """ Exponential backoff: base * 2 ** (attempt - 1), capped. """
        base = float(self.env['ir.config_parameter'].sudo().get_param(
            'social_publish_retry_base_seconds', '60'))
        cap = float(self.env['ir.config_parameter'].sudo().get_param(
            'social_publish_retry_max_seconds', '3600'))
        return min(base * (2 ** max(attempt - 1, 0)), cap)

    def _register_failure(self, exception, step=None):
        """ Record a failed attempt and schedule a retry when it makes sense.

        A transient failure below the attempt ceiling leaves the live post
        ready with ``next_retry_date`` set. A permanent failure, or a
        transient one that ran out of attempts, is terminal.
        """
        self.ensure_one()
        category = self._classify_failure(exception)
        attempt = self.attempt_count + 1
        max_attempts = self.max_attempts or self._default_max_attempts()
        retryable = category == 'transient' and attempt < max_attempts

        values = {
            'attempt_count': attempt,
            'failure_category': category,
            'failure_reason': str(exception)[:250],
        }
        if retryable:
            delay = self._get_retry_delay_seconds(attempt)
            values['state'] = 'ready'
            values['next_retry_date'] = (
                fields.Datetime.now() + timedelta(seconds=delay))
        else:
            values['state'] = 'failed'
            values['next_retry_date'] = False
        self.write(values)

        if step:
            step.write({
                'state': 'failed',
                'stage': 'failed',
                'result': _(
                    '%(category)s failure on attempt %(attempt)s/%(maximum)s: '
                    '%(error)s',
                    category=category, attempt=attempt,
                    maximum=max_attempts, error=str(exception))[:1000],
            })
        return retryable

    def _dispatch_post(self, step_id=None):
        """ Publish the live post (called by the queue_job worker).

        :param step_id: id of the dispatched pipeline step to update. """
        self.ensure_one()
        step = self.env['social.publish.pipeline.step'].browse(step_id) \
            if step_id else self.env['social.publish.pipeline.step']

        allowed, reason = self._check_publish_allowed()
        if not allowed:
            _logger.info("Live post %s blocked before dispatch: %s",
                         self.id, reason)
            self._block_publishing(reason, step=step)
            return False

        if self.state == 'posted':
            # Already published for this (post, account): a re-dispatch of the
            # same job must never produce a second published item.
            _logger.info(
                "Live post %s already posted, skipping duplicate dispatch",
                self.id)
            return True

        delay = self._get_rate_limit_delay()
        if delay > 0:
            time.sleep(delay)

        try:
            self._post()
        except Exception as exc:  # noqa: BLE001 - retry via queue_job
            _logger.exception("Live post %s failed during dispatch", self.id)
            self._register_failure(exc, step=step)
            self.post_id._check_post_completion()
            raise
        else:
            self.write({
                'attempt_count': self.attempt_count + 1,
                'next_retry_date': False,
                'failure_category': False,
            })
            self._store_platform_identity()
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

    # ------------------------------------------------------------------
    # Platform identity and retract
    # ------------------------------------------------------------------

    def _store_platform_identity(self):
        """ Persist the platform post id and permalink after publishing.

        The provider's ``_post`` usually stores them already; this fills in
        whatever is still missing from ``_fetch_platform_identity`` so that
        retracting later is always possible.
        """
        self.ensure_one()
        if self.platform_post_id and self.permalink:
            return
        identity = self._fetch_platform_identity() or {}
        values = {}
        if not self.platform_post_id and identity.get('platform_post_id'):
            values['platform_post_id'] = identity['platform_post_id']
        if not self.permalink and identity.get('permalink'):
            values['permalink'] = identity['permalink']
        if values:
            self.write(values)

    def _fetch_platform_identity(self):
        """ Hook: return ``{'platform_post_id': ..., 'permalink': ...}``.

        Overridden by the per-platform modules when the identity is not set
        directly by ``_post``. """
        self.ensure_one()
        return {}

    def _retract(self):
        """ Hook: remove the published item from the platform.

        Per-platform modules override this with the actual API call and
        should raise on failure. The generic implementation is a no-op so
        that the surrounding bookkeeping can be shared. """
        self.ensure_one()
        return True

    def _check_retract_allowed(self):
        """ Retracting is a human action.

        Refuse to run for the superuser or in a sudo'd environment, so no
        cron, queue job or automated rule can silently pull published
        content down without somebody accountable behind it.
        """
        self.ensure_one()
        if self.env.su or self.env.uid == SUPERUSER_ID:
            raise UserError(_(
                "Retracting a published post is a manual action and cannot "
                "be performed by automation. Please retract it as a logged-in "
                "user."))

    def action_retract(self):
        """ Remove the published item from the platform and record the fact. """
        for live_post in self:
            live_post._check_retract_allowed()

            if live_post.state != 'posted':
                raise UserError(_(
                    "Only a published post can be retracted (%(name)s is "
                    "%(state)s).",
                    name=live_post.display_name, state=live_post.state))

            try:
                live_post._retract()
            except Exception as exc:  # noqa: BLE001 - reported to the user
                _logger.exception(
                    "Live post %s could not be retracted", live_post.id)
                live_post.post_id._pipeline_log(
                    'retracted', state='failed',
                    result=str(exc)[:1000], live_post_id=live_post)
                raise UserError(_(
                    "Could not retract %(name)s: %(error)s",
                    name=live_post.display_name, error=exc)) from exc

            live_post.write({
                'state': 'retracted',
                'next_retry_date': False,
                'failure_reason': False,
            })
            live_post.post_id._pipeline_log(
                'retracted',
                result=_('Retracted from %(account)s by %(user)s',
                         account=live_post.social_account_id.display_name,
                         user=live_post.env.user.display_name),
                live_post_id=live_post)
        return True
