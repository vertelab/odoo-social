# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

import json
import threading

from collections import defaultdict
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class SocialPost(models.Model):
    """ A social_marketing.post represents a post that will be published on multiple social_marketing.accounts at once.
    It doesn't do anything on its own except storing the global post configuration (message, images, ...).

    This model inherits from `social_marketing.post.template` which contains the common part of both
    (all fields related to the post content like the message, the images...). So we do not
    duplicate the code by inheriting from it. We can generate a `social_marketing.post` from a
    `social_marketing.post.template` with `action_generate_post`.

    When posted, it actually creates several instances of social.live.posts (one per social_marketing.account)
    that will publish their content through the third party API of the social_marketing.account. """

    _name = 'social_marketing.post'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'utm.source.mixin', 'social_marketing.post.template']  #
    _description = 'Social Post'
    _order = 'create_date desc'
    # NOTE: _rec_name must be set on THIS class, not only on the template.
    # The template's `_rec_name = 'message'` is a class attribute that is NOT
    # inherited when the template is referenced by name in `_inherit` (Python
    # MRO only includes actual base classes). Without it, utm.source.mixin's
    # `name` field makes Odoo fall back to `_rec_name = 'name'`, and the mixin
    # then generates the utm source name from the wrong field — programmatic
    # creation (AI/Social Coach, tests) crashes with a null `utm_source.name`.
    _rec_name = 'message'

    pipeline_step_ids = fields.One2many(
        'social.publish.pipeline.step', 'post_id',
        string='Publishing Pipeline Log', readonly=True,
        help='Audit trail of the post publishing pipeline stages.')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('posting', 'Posting'),
        ('posted', 'Posted')],
        string='Status', default='draft', readonly=True, required=True,
        help="The post is considered as 'Posted' when all its sub-posts (one per social account) are either 'Failed' "
             "or 'Posted'")
    has_post_errors = fields.Boolean("There are post errors on sub-posts", compute='_compute_has_post_errors')
    account_ids = fields.Many2many(domain="[('id', 'in', account_allowed_ids)]")
    image_ids = fields.Many2many('ir.attachment', string='Attach Images',
        relation='social_marketing_post_image_ids_rel',
        column1='social_marketing_post_id', column2='ir_attachment_id')
    account_allowed_ids = fields.Many2many('social_marketing.account', string='Allowed Accounts',
                                           compute='_compute_account_allowed_ids',
                                           help='List of the accounts which can be selected for this post.')
    company_id = fields.Many2one('res.company', string='Company',
                                 default=lambda self: self.env.company,
                                 domain=lambda self: [('id', 'in', self.env.companies.ids)])
    media_ids = fields.Many2many('social_marketing.media', compute='_compute_media_ids', store=True,
                                 help="The social medias linked to the selected social accounts.")
    live_post_ids = fields.One2many('social_marketing.live.post', 'post_id', string="Posts By Account", readonly=True,
                                    help="Sub-posts that will be published on each selected social accounts.")
    live_posts_by_media = fields.Char('Live Posts by Social Media', compute='_compute_live_posts_by_media',
                                      readonly=True,
                                      help="Special technical field that holds a dict containing the live posts names by media ids (used for kanban view).")

    post_method = fields.Selection([
        ('now', 'Send now'),
        ('scheduled', 'Schedule later')], string="When", default='now', required=True,
        help="Publish your post immediately or schedule it at a later time.")
    scheduled_date = fields.Datetime('Scheduled Date')
    published_date = fields.Datetime('Published Date', readonly=True,
                                     help="When the global post was published. The actual sub-posts published dates "
                                          "may be different depending on the media.")
    # stored for better calendar view performance
    calendar_date = fields.Datetime('Calendar Date', compute='_compute_calendar_date', store=True, readonly=False)
    # technical field used by the calendar view (hatch the social_marketing.post)
    is_hatched = fields.Boolean(string="Hatched", compute='_compute_is_hatched')
    # UTM
    utm_campaign_id = fields.Many2one('utm.campaign', domain="[('is_auto_campaign', '=', False)]",
                                      string="Campaign", ondelete="set null")
    source_id = fields.Many2one(readonly=False)
    # Statistics
    stream_posts_count = fields.Integer("Feed Posts Count", compute='_compute_stream_posts_count')
    engagement = fields.Integer("Engagement", compute='_compute_post_engagement',
                                help="Number of people engagements with the post (Likes, comments...)")
    click_count = fields.Integer('Number of clicks', compute="_compute_click_count")

    @api.depends('company_id')
    def _compute_account_allowed_ids(self):
        """Compute the allowed social accounts for this social post.

        If the company is set on the post, we can attach to it account in the same company
        or without a company. If no company is set on this post, we can attach to it any
        social account.
        """
        all_account_allowed_ids = self.env['social_marketing.account'].search([])

        for post in self:
            post.account_allowed_ids = all_account_allowed_ids.filtered_domain(post._get_company_domain())

    @api.depends('live_post_ids.engagement')
    def _compute_post_engagement(self):
        results = self.env['social_marketing.live.post']._read_group(
            [('post_id', 'in', self.ids)],
            ['post_id'],
            ['engagement:sum']
        )
        engagement_per_post = {
            post.id: engagement_total
            for post, engagement_total in results
        }
        for post in self:
            post.engagement = engagement_per_post.get(post.id, 0)

    @api.depends('live_post_ids.state')
    def _compute_has_post_errors(self):
        for post in self:
            post.has_post_errors = any(live_post.state == 'failed' for live_post in post.live_post_ids)

    @api.depends('state', 'post_method', 'scheduled_date', 'published_date')
    def _compute_calendar_date(self):
        for post in self:
            if post.state == 'posted':
                post.calendar_date = post.published_date
            elif post.post_method == 'now':
                post.calendar_date = False
            else:
                post.calendar_date = post.scheduled_date

    @api.depends('live_post_ids.social_account_id', 'live_post_ids.display_name')
    def _compute_live_posts_by_media(self):
        """ See field 'help' for more information. """
        for post in self:
            accounts_by_media = {media_id: [] for media_id in post.media_ids.ids}
            for live_post in post.live_post_ids.filtered(lambda lp: lp.social_account_id.media_id.ids):
                accounts_by_media[live_post.social_account_id.media_id.id].append(live_post.display_name)
            post.live_posts_by_media = json.dumps(accounts_by_media)

    @api.depends('state')
    def _compute_is_hatched(self):
        for post in self:
            post.is_hatched = post.state == 'draft'

    def _compute_click_count(self):
        # Filter by `medium_id` so we can compute the click count based
        # on the current companies (1 account == 1 medium)
        medium_ids = self.account_ids.mapped('utm_medium_id')

        if not self.source_id.ids or not medium_ids.ids:
            # not "source_id", the records are not yet created
            for post in self:
                post.click_count = 0
        else:
            query = """
                SELECT COUNT(DISTINCT(click.id)) as click_count, link.source_id
                  FROM link_tracker_click click
            INNER JOIN link_tracker link ON link.id = click.link_id
                 WHERE link.source_id IN %s AND link.medium_id IN %s
              GROUP BY link.source_id
            """

            self.env.cr.execute(query, [tuple(self.source_id.ids), tuple(medium_ids.ids)])
            click_data = self.env.cr.dictfetchall()
            mapped_data = {datum['source_id']: datum['click_count'] for datum in click_data}
            for post in self:
                post.click_count = mapped_data.get(post.source_id.id, 0)

    # @api.depends('state')
    # def _compute_display_name(self):
    #     """ We use the first 20 chars of the message (or "Post" if no message yet).
    #     We also add "(Draft)" at the end if the post is still in draft state. """
    #     for post in self:
    #         post.display_name = self._prepare_post_name(
    #             post.message,
    #             state=post.state if post.state == 'draft' else False,
    #         )

    @api.model
    def default_get(self, fields):
        """ When created from the calendar view, we set the post as scheduled at the selected date. """

        result = super(SocialPost, self).default_get(fields)
        default_calendar_date = self.env.context.get('default_calendar_date')
        if default_calendar_date and ('post_method' in fields or 'scheduled_date' in fields):
            result.update({
                'post_method': 'scheduled',
                'scheduled_date': default_calendar_date
            })
        return result

    @api.model_create_multi
    def create(self, vals_list):
        """Every post will have a unique corresponding utm.source for statistics computation purposes.
        This way, it will be possible to see every leads/quotations generated through a particular post."""

        # Validate the message up front: the utm.source.mixin creates the
        # source inside the super chain, before the _check_message_not_empty
        # constraint can run. Without this guard an empty message would crash
        # on the utm_source.name NOT NULL constraint instead of raising the
        # proper UserError.
        for vals in vals_list:
            if not (vals.get('message') or '').strip():
                raise UserError(_("The 'message' field is required for post ID."))

        # if a scheduled_date / published_date is specified, it should be the one used as the calendar date
        # this is normally handled by the `_compute_calendar_date` but in create mode,
        # it is not called when a default value for the calendar_date field is passed
        # if the post_method is set to 'now' unset the calendar_date to avoid displaying it in the calendar
        for vals in vals_list:
            if vals.get('state') == 'posted' and 'published_date' in vals:
                vals['calendar_date'] = vals['published_date']
            elif vals.get('post_method') == 'now':
                vals['calendar_date'] = False
            elif 'scheduled_date' in vals:
                vals['calendar_date'] = vals['scheduled_date']

        res = super(SocialPost, self).create(vals_list)

        cron = self.env.ref('social_marketing.ir_cron_post_scheduled')
        cron_trigger_dates = set([
            post.scheduled_date
            for post in res
            if post.scheduled_date
        ])
        if cron_trigger_dates:
            cron._trigger(cron_trigger_dates)

        return res

    def write(self, vals):
        if vals.get('calendar_date'):
            if any(post.state not in ('draft', 'scheduled') for post in self):
                raise UserError(_("You cannot reschedule a post that has already been posted."))

            vals['scheduled_date'] = vals['calendar_date']

        if vals.get('scheduled_date'):
            cron = self.env.ref('social_marketing.ir_cron_post_scheduled')
            cron._trigger(at=fields.Datetime.from_string(vals.get('scheduled_date')))

        return super(SocialPost, self).write(vals)

    def _check_post_access(self):
        """
        Raise an error if the user cannot post on a social media
        """
        if any(not post.account_ids for post in self):
            raise UserError(_(
                'Please specify at least one account to post into (for post ID(s) %s).',
                ', '.join([str(post.id) for post in self if not post.account_ids])
            ))
        errors = defaultdict(list)
        for post in self:
            for media in post.media_ids.filtered(
                    lambda media: media.max_post_length and post.message_length > media.max_post_length):
                errors[post].append(_("%s (max %s chars)", media.name, media.max_post_length))
        if bool(errors):
            raise ValidationError(_(
                "Due to length restrictions, the following posts cannot be posted:\n %s",
                "\n".join(["%s : %s" % (post.display_name, ",".join(err)) for post, err in errors.items()])
            ))

    def _get_target_platforms(self):
        """ Platforms this post is targeted at (see platform_ids). """
        self.ensure_one()
        return self.platform_ids

    def _validate_platform_rules(self):
        """ Pre-flight: check the post against each target platform's rules.

        The limits themselves are data on ``social_marketing.platform`` so a
        platform changing its rules does not require a code change. Raised at
        scheduling time so the user finds out while they can still fix it,
        rather than at publish time when the post is already queued.
        """
        violations = []
        for post in self:
            for platform in post._get_target_platforms():
                violations.extend(platform._validate_post(post))
        if violations:
            raise ValidationError(_(
                "This post does not satisfy the rules of every target "
                "platform:\n%s", "\n".join("- %s" % v for v in violations)))

    def action_schedule(self):
        self._check_post_access()
        self._validate_platform_rules()
        self.write({'state': 'scheduled'})

    def action_set_draft(self):
        self._check_post_access()
        self.write({'state': 'draft'})

    def action_post(self):
        self._check_post_access()
        self._validate_platform_rules()

        self.write({
            'post_method': 'now',
            'scheduled_date': False
        })

        self._action_post()

    def action_redirect_to_clicks(self):
        action = self.env["ir.actions.actions"]._for_xml_id("link_tracker.link_tracker_action")
        action['domain'] = [
            ('source_id', '=', self.source_id.id),
            ('medium_id', 'in', self.account_ids.mapped('utm_medium_id').ids),
        ]
        return action

    def _pipeline_log(self, stage, state='done', result=None, live_post_id=None):
        """ Create an audit step record for the post (system-level, sudo).

        policy_id is optional: it only exists when social_planner is installed,
        so it is read defensively. """
        self.ensure_one()
        policy = self.policy_id if 'policy_id' in self._fields else False
        self.env['social.publish.pipeline.step'].sudo().create({
            'post_id': self.id,
            'live_post_id': live_post_id.id if live_post_id else False,
            'stage': stage,
            'state': state,
            'result': result or False,
            'policy_version': policy.version if policy else False,
        })

    def _action_post(self):
        """ Dispatch each live post through the job queue (queue_job).

        Replaces the synchronous loop: one queue.job per live post, workers
        claim jobs with FOR UPDATE SKIP LOCKED (safe in HA), retry/backoff on
        transient errors, per-media rate limiting. The post is only completed
        once all live posts are terminal (published or failed). """
        # Only the live posts that do not exist yet are dispatched, so a
        # second call for the same post is a no-op instead of a re-publish.
        new_live_posts = self.env['social_marketing.live.post']
        for post in self:
            known_ids = set(post.live_post_ids.ids)
            post.write({
                'state': 'posting',
                'published_date': fields.Datetime.now(),
                'live_post_ids': [
                    (0, 0, live_post)
                    for live_post in post._prepare_live_post_values()],
            })
            new_live_posts |= post.live_post_ids.filtered(
                lambda lp: lp.id not in known_ids)

        # A brand with publishing paused is stopped here as well as inside
        # _dispatch_post, so no job is even created for it.
        blocked = self.env['social_marketing.live.post']
        for live_post in new_live_posts:
            allowed, reason = live_post._check_publish_allowed()
            if not allowed:
                blocked |= live_post
                live_post._block_publishing(reason)
        new_live_posts -= blocked

        # One pending pipeline step per newly created live post, created
        # before commit so the steps persist together with the live posts.
        step_by_live = {}
        for live_post in new_live_posts:
            step = self.env['social.publish.pipeline.step'].sudo().create({
                'post_id': live_post.post_id.id,
                'live_post_id': live_post.id,
                'stage': 'dispatched',
                'state': 'pending',
            })
            step_by_live[live_post.id] = step

        if not getattr(threading.current_thread(), 'testing', False):
            # If there's a link in the message, the Facebook / Twitter API will fetch it
            # to build a preview. The link tracker must exist before the job runs,
            # so flush and commit before enqueuing (the jobs must survive the commit).
            self.mapped('live_post_ids.message')
            self.env.cr.commit()

        for live_post in new_live_posts:
            step = step_by_live[live_post.id]
            live_post.with_delay(
                priority=10,
                max_retries=5,
                description=_('Publish live post %s for %s',
                              live_post.display_name,
                              live_post.post_id.display_name),
                identity_key='social_publish_live_%s' % live_post.id,
            )._dispatch_post(step_id=step.id)
        return True

    def _prepare_live_post_values(self):
        """ Values for the live posts still missing for this post.

        Accounts that already have a live post are skipped: re-posting an
        already dispatched post must not create a second published item.
        The database unique index on ``idempotency_key`` is the real
        guarantee; this only avoids provoking it on the normal path.
        """
        self.ensure_one()

        existing_account_ids = set(
            self.live_post_ids.mapped('social_account_id').ids)
        return [{
            'post_id': self.id,
            'social_account_id': account.id,
        } for account in self.account_ids
            if account.id not in existing_account_ids]

    def _check_post_completion(self):
        """ This method will check if all live.posts related to the post are completed ('posted' / 'failed').
        If it's the case, we can mark the post itself as 'posted'. """

        before = {post.id: post.state for post in self}
        posts_to_complete = self.filtered(
            lambda post: all(
                live_post.state in ('posted', 'failed', 'retracted')
                for live_post in post.live_post_ids
            )
        )

        for post in posts_to_complete:
            posts_failed = Markup('<br>').join([
                '  - ' + live_post.display_name
                for live_post in post.live_post_ids
                if live_post.state == 'failed'
            ])

            if posts_failed:
                post._message_log(body=_("Message posted partially. These are the ones that couldn't be posted:%s",
                                         Markup("<br/>") + posts_failed))
            else:
                post._message_log(body=_("Message posted"))

        if posts_to_complete:
            posts_to_complete.sudo().write({'state': 'posted'})

        # Log a completed pipeline step on the posting→posted transition.
        for post in self:
            if before.get(post.id) != 'posted' and post.state == 'posted':
                failed = post.live_post_ids.filtered(
                    lambda lp: lp.state == 'failed')
                post._pipeline_log(
                    'completed',
                    result=_('Posted (%(posted)s channel(s))%(failed)s',
                             posted=len(post.live_post_ids) - len(failed),
                             failed=', %s failed' % len(failed) if failed else ''))

    def _get_company_domain(self):
        self.ensure_one()
        if self.company_id:
            return ['|', ('company_id', '=', False), ('company_id', '=', self.company_id.id)]
        return ['|', ('company_id', '=', False), ('company_id', 'in', self.env.companies.ids)]

    @api.model
    def _cron_publish_scheduled(self):
        """ Method called by the cron job that searches for social_marketing.posts that were scheduled and need
        to be published and calls _action_post() on them."""

        self.search([
            ('post_method', '=', 'scheduled'),
            ('state', '=', 'scheduled'),
            ('scheduled_date', '<=', fields.Datetime.now())
        ])._action_post()
