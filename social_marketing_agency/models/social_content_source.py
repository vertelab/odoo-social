# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression
import pytz

from odoo.tools.safe_eval import safe_eval

from odoo.addons.social_marketing.models.social_data_binding_core import (
    collect_tokens,
)
from odoo.addons.social_marketing.models.social_marketing_post_template import (
    _html_to_plain_text,
)

from .content_source_core import (
    WEEKDAYS,
    compute_next_occurrence,
    pick_next_id,
)

_logger = logging.getLogger(__name__)


def _tz_get(self):
    return [(tz, tz) for tz in sorted(pytz.all_timezones, key=lambda t: t)]

class SocialContentSource(models.Model):
    """A recurring generator of social posts from any Odoo model.

    "Post one product every Monday at 08:47" without writing code: pick a
    model, a domain, a schedule and a template. The cron then rotates through
    the qualifying records and creates one post per run. Generated posts are
    always drafts; nothing here publishes anything.
    """

    _name = 'social.content.source'
    _inherit = ['social.brand.focus.mixin']
    _description = 'Social Content Source'
    _order = 'name'

    name = fields.Char('Name', required=True)
    brand_id = fields.Many2one(
        'social.brand', string='Brand', required=True, ondelete='cascade',
        index=True, default=lambda self: self._get_default_brand(),
        help="Brand this source belongs to. Records of other brands are "
             "never picked up.")
    model_id = fields.Many2one(
        'ir.model', string='Model', required=True, ondelete='cascade',
        help="What to post about, for example Product Template.")
    model_name = fields.Char(related='model_id.model', string='Model Name',
                             store=True, readonly=True)
    domain = fields.Char('Domain', default='[]',
                         help="Which records of the model qualify.")

    post_template_id = fields.Many2one(
        'social_marketing.post.template', string='Post Template',
        help="Text template. Every {{ token }} it uses must be registered "
             "as a data binding on the template itself, pointing at a field "
             "of this source's model.")
    image_template_id = fields.Many2one(
        'social.image.template', string='Image Template')
    account_ids = fields.Many2many(
        'social_marketing.account', string='Accounts',
        help="Where the generated posts will be published once a human "
             "approves them.")
    utm_campaign_id = fields.Many2one(
        'utm.campaign', string='Campaign', ondelete='set null',
        domain="[('is_auto_campaign', '=', False)]",
        help="Stamped onto every generated post, so the campaign groups "
             "everything this source produced.")

    interval_type = fields.Selection(
        [('daily', 'Daily'), ('weekly', 'Weekly'), ('monthly', 'Monthly')],
        string='Interval', required=True, default='weekly')
    weekday = fields.Selection(
        [('mon', 'Monday'), ('tue', 'Tuesday'), ('wed', 'Wednesday'),
         ('thu', 'Thursday'), ('fri', 'Friday'), ('sat', 'Saturday'),
         ('sun', 'Sunday')],
        string='Weekday', default='mon',
        help="Used when the interval is weekly.")
    day_of_month = fields.Integer(
        'Day of Month', default=1,
        help="Used when the interval is monthly. Clamped to the length of "
             "the month, so 31 lands on the last day of February.")
    time_of_day = fields.Float(
        'Time of Day', required=True, default=8.0,
        help="Odoo float time in UTC: 08:47 is 8.783333.")
    tz = fields.Selection(
        _tz_get, string='Timezone',
        default=lambda self: self.env.user.tz or 'UTC', required=True,
        help="Timezone the schedule is expressed in. A weekly source set to "
             "08:47 fires at 08:47 local time, not 08:47 UTC.")


    active = fields.Boolean('Active', default=True)
    last_run = fields.Datetime('Last Run', readonly=True, copy=False)
    next_run = fields.Datetime(
        'Next Run', readonly=True, copy=False, store=True,
        compute='_compute_next_run')

    cycle = fields.Integer(
        'Rotation Cycle', default=1, readonly=True, copy=False,
        help="Incremented every time the pool is exhausted and rotation "
             "starts over.")
    log_ids = fields.One2many(
        'social.content.source.log', 'source_id', string='Generated Posts')
    log_count = fields.Integer('Generated', compute='_compute_log_count')
    unbound_token_warning = fields.Char(
        'Unbound Tokens', compute='_compute_unbound_token_warning',
        help="Filled in when the post template uses tokens this source "
             "cannot resolve, which would generate empty posts.")

    # ── Computes and constraints ─────────────────────────────────────────

    @api.depends('log_ids')
    def _compute_log_count(self):
        for source in self:
            source.log_count = len(source.log_ids)

    def _unbound_tokens(self):
        """Tokens the post template uses that this source cannot resolve.

        A token resolves only when the template carries a
        ``social.data.binding`` of that name pointing at this source's own
        model. Anything else renders as an empty string, so it is listed
        here rather than left to be discovered in a published post.
        """
        self.ensure_one()
        template = self.post_template_id
        if not template:
            return []
        model_name = self.model_id.model
        bound = set(template.binding_ids.filtered(
            lambda binding: binding.model_id.model == model_name
        ).mapped('name'))
        return [token for token in collect_tokens(template.message or '')
                if token not in bound]

    @api.depends('model_id', 'post_template_id',
                 'post_template_id.message',
                 'post_template_id.binding_ids.name',
                 'post_template_id.binding_ids.model_id')
    def _compute_unbound_token_warning(self):
        for source in self:
            unbound = source._unbound_tokens() if source.post_template_id else []
            source.unbound_token_warning = ', '.join(unbound)

    @api.constrains('model_id', 'post_template_id')
    def _check_template_tokens_are_bound(self):
        for source in self:
            unbound = source._unbound_tokens()
            if unbound:
                raise ValidationError(_(
                    "Post template %(template)s uses tokens this source "
                    "cannot resolve: %(tokens)s. Register a data binding "
                    "for each of them on the template, pointing at a field "
                    "of %(model)s. Without one the token renders as empty "
                    "text and every generated post is blank.",
                    template=source.post_template_id.display_name or '',
                    tokens=', '.join(unbound),
                    model=source.model_id.model or ''))

    @api.depends('interval_type', 'weekday', 'day_of_month', 'time_of_day', 'tz',
                 'last_run', 'active')
    def _compute_next_run(self):
        for source in self:
            if not source.active or not source.interval_type:
                source.next_run = False
                continue
            base = source.last_run or fields.Datetime.now()
            source.next_run = source._next_occurrence(base)

    @api.constrains('day_of_month')
    def _check_day_of_month(self):
        for source in self:
            if source.interval_type == 'monthly' and not (
                    1 <= source.day_of_month <= 31):
                raise ValidationError(
                    _('Day of month must be between 1 and 31.'))

    @api.constrains('time_of_day')
    def _check_time_of_day(self):
        for source in self:
            if not (0.0 <= source.time_of_day < 24.0):
                raise ValidationError(
                    _('Time of day must be between 0.0 and 24.0.'))

    @api.constrains('domain')
    def _check_domain(self):
        for source in self:
            try:
                parsed = safe_eval(source.domain or '[]')
            except Exception as exc:
                raise ValidationError(
                    _('The domain is not valid Python: %s', exc))
            if not isinstance(parsed, list):
                raise ValidationError(_('The domain must be a list.'))

    # ── Scheduling ───────────────────────────────────────────────────────

    def _next_occurrence(self, from_dt=None):
        """Next scheduled datetime strictly after ``from_dt``.

        Input and output are naive UTC, which is what Odoo stores, but the
        schedule itself is expressed in the source's own timezone. A weekly
        source asking for Monday 08:47 means 08:47 where the brand is, so the
        arithmetic happens in local time and only the result is converted
        back. Doing it the other way round drifts by an hour twice a year.
        """
        self.ensure_one()
        from_dt = from_dt or fields.Datetime.now()
        zone = pytz.timezone(self.tz or 'UTC')
        local_from = pytz.utc.localize(from_dt).astimezone(zone).replace(
            tzinfo=None)
        local_next = compute_next_occurrence(
            local_from,
            self.interval_type,
            weekday=self.weekday,
            day_of_month=self.day_of_month,
            time_of_day=self.time_of_day,
        )
        if not local_next:
            return local_next
        return zone.localize(local_next).astimezone(pytz.utc).replace(
            tzinfo=None)

    # ── Record rotation ──────────────────────────────────────────────────

    def _candidate_domain(self):
        """Domain of qualifying records, brand scoped when the model allows.

        Brand scoping is not optional: if the target model carries a
        ``brand_id``, only records of this source's brand can ever qualify.
        """
        self.ensure_one()
        domain = safe_eval(self.domain or '[]')
        target = self.env[self.model_id.model]
        if 'brand_id' in target._fields:
            domain = expression.AND(
                [domain, [('brand_id', '=', self.brand_id.id)]])
        return domain

    def _candidate_records(self):
        self.ensure_one()
        target = self.env[self.model_id.model]
        return target.search(self._candidate_domain(), order='id')

    def _pick_next_record(self):
        """Return the next qualifying record not yet posted by this source.

        Rotation is stable (ascending id) and never repeats a record while an
        unposted one remains. Once the pool is exhausted the cycle counter is
        bumped and rotation starts over from the first record.
        """
        self.ensure_one()
        candidates = self._candidate_records()
        if not candidates:
            return candidates
        posted = self.log_ids.filtered(
            lambda log: log.cycle == self.cycle).mapped('res_id')
        next_id, restarted = pick_next_id(candidates.ids, posted)
        if restarted:
            self.cycle += 1
        return candidates.browse(next_id)

    # ── Post generation ──────────────────────────────────────────────────

    def _prepare_post_values(self, record):
        """Values for the draft post generated from ``record``.

        Token substitution goes through the post template's registered
        ``social.data.binding`` records, the same path (and the same
        formatting) the template's own preview uses. There is no implicit
        "any field name is a token" fallback: a token nobody registered
        renders empty, on purpose, and :meth:`_check_template_tokens_are_bound`
        refuses to let a source be saved in that state.
        """
        self.ensure_one()
        template = self.post_template_id
        message = template.render_bound_message(record) if template else ''
        # Emptiness is judged on the plain text, not on the markup: a
        # template that is one token renders to "<p></p>", which is not a
        # message, and a post model constraint would reject it anyway.
        if not _html_to_plain_text(message):
            message = '<p>%s</p>' % (record.display_name or '')
        return {
            'message': message,
            'brand_id': self.brand_id.id,
            'account_ids': [(6, 0, self.account_ids.ids)],
            'utm_campaign_id': self.utm_campaign_id.id or False,
            # Automation never publishes. A human gate is not negotiable.
            'state': 'draft',
            'post_method': 'scheduled',
        }

    def _attach_generated_image(self, post, record):
        """Best effort image render; a dead render service must not block."""
        self.ensure_one()
        if not self.image_template_id:
            return
        try:
            # The image template's own bindings supply the values, which is
            # also what turns a binary field into a /web/image/... source
            # the render service can actually fetch.
            attachment = self.image_template_id.render_template_for_record(
                record)
        except Exception:
            _logger.warning(
                'Content source %s could not render an image for %s,%s',
                self.id, record._name, record.id, exc_info=True)
            return
        if attachment:
            post.image_ids = [(4, attachment.id)]

    def _generate_post(self):
        """Create one DRAFT post for the next record in the rotation.

        Returns the created post, or an empty recordset when the source has
        nothing to post about.
        """
        self.ensure_one()
        Post = self.env['social_marketing.post']
        record = self._pick_next_record()
        if not record:
            _logger.info(
                'Content source %s (%s) has no qualifying records',
                self.name, self.id)
            return Post
        post = Post.create(self._prepare_post_values(record))
        self._attach_generated_image(post, record)
        self.env['social.content.source.log'].create({
            'source_id': self.id,
            'res_id': record.id,
            'post_id': post.id,
            'cycle': self.cycle,
        })
        self.last_run = fields.Datetime.now()
        return post

    def action_generate_now(self):
        """Manual trigger, useful to check a source before trusting the cron."""
        self.ensure_one()
        post = self._generate_post()
        if not post:
            raise UserError(
                _('No qualifying record left to post for this source.'))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'social_marketing.post',
            'res_id': post.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }

    def action_view_generated_posts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Generated Posts'),
            'res_model': 'social_marketing.post',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.log_ids.mapped('post_id').ids)],
        }

    # ── Cron ─────────────────────────────────────────────────────────────

    @api.model
    def _cron_generate_posts(self):
        """Run every source whose next_run has come. One bad source must not
        stop the others, so failures are logged and skipped."""
        now = fields.Datetime.now()
        due = self.search([('next_run', '!=', False), ('next_run', '<=', now)])
        for source in due:
            try:
                with self.env.cr.savepoint():
                    source._generate_post()
            except Exception:
                _logger.exception(
                    'Content source %s (%s) failed to generate a post',
                    source.name, source.id)
        return True


class SocialContentSourceLog(models.Model):
    """Link between a content source, the record it posted and the post.

    This is what makes rotation stable: it records what has already gone out
    for a given source and rotation cycle.
    """

    _name = 'social.content.source.log'
    _description = 'Social Content Source Log'
    _order = 'date desc, id desc'

    source_id = fields.Many2one(
        'social.content.source', string='Source', required=True,
        ondelete='cascade', index=True)
    brand_id = fields.Many2one(
        related='source_id.brand_id', string='Brand', store=True, index=True)
    res_model = fields.Char(
        related='source_id.model_name', string='Model', store=True)
    res_id = fields.Integer('Record ID', required=True, index=True)
    post_id = fields.Many2one(
        'social_marketing.post', string='Post', ondelete='set null')
    cycle = fields.Integer('Rotation Cycle', default=1, required=True)
    date = fields.Datetime('Date', default=fields.Datetime.now, required=True)

    def _compute_display_name(self):
        for log in self:
            log.display_name = '%s / %s,%s' % (
                log.source_id.name or '', log.res_model or '', log.res_id)


# Exposed so views and tests share the same weekday ordering.
__all__ = ['SocialContentSource', 'SocialContentSourceLog', 'WEEKDAYS']
