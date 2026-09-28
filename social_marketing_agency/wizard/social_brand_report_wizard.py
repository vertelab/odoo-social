# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

""" Customer facing monthly report for one brand.

The report answers the only question a customer really asks about a retainer:
what did the work produce. Volume alone never answers it, so the report puts
volume, engagement, attributed leads and revenue, the content that performed
best and the review trail on the same page.

Two rules shape the whole file.

First, the attribution figures come from optional bridge modules
(social_marketing_crm, social_marketing_sale, social_marketing_mass_mailing).
This module depends on none of them, so every attribution field is looked up in
the registry at runtime, and a figure is only ever printed when the field both
exists and is readable by the user producing the report. A section that reports
zero leads because the CRM bridge is not installed would read to the customer as
"your campaign produced nothing", which is the opposite of the truth. Whatever
cannot be measured is named as unmeasured instead, in the measurement notes.

Second, there is no sudo() anywhere. Everything is gathered as the user who
presses the button, so the record rules that keep a customer inside their own
brands apply to the report exactly as they apply to the interface.
"""

from datetime import datetime, time

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.tools.misc import format_date, format_datetime


# Stat metrics reported back to the customer, in the order they are printed.
ENGAGEMENT_METRICS = (
    ('engagement', 'Engagements'),
    ('likes', 'Likes'),
    ('comments', 'Comments'),
    ('shares', 'Shares'),
)

# Pipeline stages that count as evidence that the work went through review.
REVIEW_STAGES = (
    'submitted',
    'compliance_checked',
    'approved',
    'awaiting_customer',
    'rejected',
)

MAX_ACTIVITY_LINES = 20


class SocialBrandReportWizard(models.TransientModel):
    _name = 'social.brand.report.wizard'
    _description = 'Brand Performance Report'

    brand_id = fields.Many2one(
        'social.brand', string='Brand', required=True,
        default=lambda self: self._default_brand_id())
    date_from = fields.Date(
        'Period Start', required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(
        'Period End', required=True,
        default=lambda self: fields.Date.context_today(self))
    top_post_count = fields.Integer(
        'Number of Top Posts', default=5,
        help="How many of the best performing posts to show individually.")

    @api.model
    def _default_brand_id(self):
        brand_id = self.env.context.get('default_brand_id')
        if brand_id:
            return brand_id
        active_model = self.env.context.get('active_model')
        if active_model == 'social.brand':
            return self.env.context.get('active_id')
        return False

    @api.constrains('date_from', 'date_to')
    def _check_period(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise ValidationError(
                    _("The period start must not be later than the period end."))

    @api.constrains('top_post_count')
    def _check_top_post_count(self):
        for wizard in self:
            if wizard.top_post_count < 0:
                raise ValidationError(
                    _("The number of top posts cannot be negative."))

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------

    def _checked_brand(self):
        """Return the brand, refusing brands the current user cannot see.

        Two mechanisms restrict brands in this module and the report honours
        both: the record rules that scope customer users to their own brands,
        and the ``social.brand.search()`` override that scopes an agency brand
        user to the brands assigned to them. Searching for the brand as the
        current user is the only check that covers both, so it is the check
        used here.
        """
        self.ensure_one()
        brand = self.brand_id
        brand.check_access('read')
        # search(), not search_count(): search_count() goes straight to
        # _search() and would step past the social.brand.search() override
        # that scopes an agency brand user to their assigned brands.
        if not self.env['social.brand'].search([('id', '=', brand.id)]):
            raise AccessError(_(
                "You are not allowed to produce a report for this brand."))
        return brand

    # ------------------------------------------------------------------
    # Period handling
    # ------------------------------------------------------------------

    def _period_bounds(self):
        """Return the period as naive UTC datetimes.

        The dates on the wizard are the customer's calendar days, while
        published_date and create_date are stored in UTC, so the day
        boundaries are resolved in the user's timezone first.
        """
        self.ensure_one()
        user_tz = pytz.timezone(self.env.user.tz or 'UTC')
        start = user_tz.localize(
            datetime.combine(self.date_from, time.min)).astimezone(pytz.UTC)
        end = user_tz.localize(
            datetime.combine(self.date_to, time.max)).astimezone(pytz.UTC)
        return start.replace(tzinfo=None), end.replace(tzinfo=None)

    # ------------------------------------------------------------------
    # Optional bridge detection
    # ------------------------------------------------------------------

    def _readable_fields(self, model_name, field_names):
        """True when every named field exists on the model and may be read.

        A missing field means the bridge module is not installed. A field that
        exists but is not accessible means the bridge is installed and the user
        producing the report is not allowed to see those figures. Neither is a
        zero, and both are reported as unmeasured.
        """
        model = self.env[model_name]
        for field_name in field_names:
            field = model._fields.get(field_name)
            if field is None or not field.is_accessible(self.env):
                return False
        return True

    # ------------------------------------------------------------------
    # Data gathering
    # ------------------------------------------------------------------

    def _period_posts(self, brand):
        start, end = self._period_bounds()
        return self.env['social_marketing.post'].search([
            ('brand_id', '=', brand.id),
            ('state', '=', 'posted'),
            ('published_date', '>=', start),
            ('published_date', '<=', end),
        ], order='published_date desc, id desc')

    def _platform_lines(self, live_posts):
        """Publications per platform, counted per live post.

        One post published to three accounts is one post in the volume total
        and three publications spread over the platforms of those accounts,
        which is why the two numbers do not have to match.
        """
        counted = {}
        for live_post in live_posts:
            media = live_post.social_account_id.media_id
            key = media.id or 0
            name = media.name or _("Unknown platform")
            entry = counted.setdefault(key, {'name': name, 'count': 0})
            entry['count'] += 1
        return sorted(
            counted.values(), key=lambda line: (-line['count'], line['name']))

    def _latest_stat_values(self, live_posts):
        """Return {(live_post_id, metric): value} from the newest snapshot.

        The snapshots are cumulative counters written on a decay schedule, so
        the value of a metric for the period is the last snapshot taken inside
        the period, never the sum of the snapshots.
        """
        self.ensure_one()
        if not live_posts:
            return {}
        stats = self.env['social_marketing.live_post.stat'].search([
            ('live_post_id', 'in', live_posts.ids),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ], order='date asc, id asc')
        latest = {}
        for stat in stats:
            latest[(stat.live_post_id.id, stat.metric)] = stat.value
        return latest

    def _engagement_lines(self, latest_values):
        """One line per metric, each either a measured total or unmeasured."""
        lines = []
        for metric, label in ENGAGEMENT_METRICS:
            values = [
                value for (dummy, stat_metric), value in latest_values.items()
                if stat_metric == metric
            ]
            lines.append({
                'label': label,
                'measured': bool(values),
                'value': int(round(sum(values))) if values else 0,
            })
        return lines

    def _post_engagement(self, post, latest_values):
        total = 0.0
        for live_post in post.live_post_ids:
            total += latest_values.get((live_post.id, 'engagement'), 0.0)
        return int(round(total))

    def _top_post_lines(self, posts, latest_values):
        if not posts or self.top_post_count <= 0:
            return []
        lines = []
        for post in posts:
            media_names = sorted(set(
                live_post.social_account_id.media_id.name or _("Unknown platform")
                for live_post in post.live_post_ids
            ))
            lines.append({
                'message': self._short_message(post),
                'published_date': format_datetime(self.env, post.published_date),
                'platforms': ', '.join(media_names),
                'engagement': self._post_engagement(post, latest_values),
                'clicks': post.click_count,
            })
        lines.sort(key=lambda line: (-line['engagement'], -line['clicks']))
        return lines[:self.top_post_count]

    def _short_message(self, post):
        message = (post.message or '').strip()
        if not message:
            return _("(no text)")
        message = ' '.join(message.split())
        if len(message) > 120:
            return message[:117] + '...'
        return message

    def _attribution(self, posts):
        """Attributed leads and revenue, only where they can be measured.

        Every block is None when its bridge is missing or its fields are not
        readable. The template prints nothing at all for a None block and the
        measurement notes name it instead, so a customer never reads an absent
        integration as a campaign that produced nothing.
        """
        self.ensure_one()
        campaigns = posts.utm_campaign_id
        result = {
            'currency': self.env.company.currency_id,
            'crm': None,
            'sale': None,
            'mailing': None,
        }

        crm_fields = ('crm_lead_count', 'crm_lead_won_count', 'crm_expected_revenue')
        if self._readable_fields('social_marketing.post', crm_fields):
            result['crm'] = {
                'lead_count': sum(posts.mapped('crm_lead_count')),
                'lead_won_count': sum(posts.mapped('crm_lead_won_count')),
                'expected_revenue': sum(posts.mapped('crm_expected_revenue')),
            }

        sale_fields = ('sale_quotation_count', 'sale_order_count', 'sale_order_revenue')
        if self._readable_fields('social_marketing.post', sale_fields):
            result['sale'] = {
                'quotation_count': sum(posts.mapped('sale_quotation_count')),
                'order_count': sum(posts.mapped('sale_order_count')),
                'order_revenue': sum(posts.mapped('sale_order_revenue')),
            }

        mailing_fields = (
            'mailing_sent_total', 'mailing_delivered_total',
            'mailing_opened_total', 'mailing_clicked_total',
        )
        if self._readable_fields('utm.campaign', mailing_fields):
            result['mailing'] = {
                'campaign_count': len(campaigns),
                'sent': sum(campaigns.mapped('mailing_sent_total')),
                'delivered': sum(campaigns.mapped('mailing_delivered_total')),
                'opened': sum(campaigns.mapped('mailing_opened_total')),
                'clicked': sum(campaigns.mapped('mailing_clicked_total')),
            }

        result['available'] = any(
            result[key] for key in ('crm', 'sale', 'mailing'))
        return result

    def _activity(self, brand):
        """The review trail: pipeline steps recorded during the period."""
        self.ensure_one()
        start, end = self._period_bounds()
        steps = self.env['social.publish.pipeline.step'].search([
            ('post_id.brand_id', '=', brand.id),
            ('stage', 'in', list(REVIEW_STAGES)),
            ('create_date', '>=', start),
            ('create_date', '<=', end),
        ], order='create_date asc, id asc')

        stage_labels = dict(
            self.env['social.publish.pipeline.step']
            ._fields['stage']._description_selection(self.env))
        by_stage = {}
        for step in steps:
            by_stage[step.stage] = by_stage.get(step.stage, 0) + 1
        stage_lines = [
            {'label': stage_labels.get(stage, stage), 'count': count}
            for stage, count in sorted(by_stage.items(), key=lambda item: -item[1])
        ]

        approvals = steps.filtered(lambda step: step.stage == 'approved')
        approval_lines = [{
            'date': format_datetime(self.env, step.create_date),
            'post': self._short_message(step.post_id),
            'actor': step.user_id.name or _("Unknown"),
        } for step in approvals[:MAX_ACTIVITY_LINES]]

        return {
            'step_count': len(steps),
            'approval_count': len(approvals),
            'stage_lines': stage_lines,
            'approval_lines': approval_lines,
            'approval_lines_hidden': max(0, len(approvals) - MAX_ACTIVITY_LINES),
        }

    def _measurement_notes(self, engagement_lines, attribution):
        """Name everything the report could not measure, in plain words."""
        notes = []
        unmeasured = [
            line['label'].lower() for line in engagement_lines
            if not line['measured']
        ]
        if unmeasured:
            notes.append(_(
                "No measurements were collected for %s in this period. The "
                "figure is missing, it is not a zero.",
                ', '.join(unmeasured)))
        if attribution['crm'] is None:
            notes.append(_(
                "Leads and pipeline value are not measured for this brand. The "
                "report cannot say whether the posts produced leads."))
        if attribution['sale'] is None:
            notes.append(_(
                "Orders and order revenue are not measured for this brand. The "
                "report cannot say whether the posts produced sales."))
        if attribution['mailing'] is None:
            notes.append(_(
                "Newsletter figures are not measured for the campaigns in this "
                "period."))
        return notes

    def _report_data(self):
        """Everything the template prints, gathered as the current user."""
        self.ensure_one()
        brand = self._checked_brand()
        posts = self._period_posts(brand)
        live_posts = posts.live_post_ids.filtered(
            lambda live_post: live_post.state == 'posted')
        latest_values = self._latest_stat_values(live_posts)
        engagement_lines = self._engagement_lines(latest_values)
        attribution = self._attribution(posts)

        return {
            'wizard': self,
            'brand': brand,
            'partner': brand.partner_id,
            'date_from': format_date(self.env, self.date_from),
            'date_to': format_date(self.env, self.date_to),
            'post_count': len(posts),
            'publication_count': len(live_posts),
            'platform_lines': self._platform_lines(live_posts),
            'engagement_lines': engagement_lines,
            'click_count': sum(posts.mapped('click_count')),
            'attribution': attribution,
            'top_post_lines': self._top_post_lines(posts, latest_values),
            'activity': self._activity(brand),
            'notes': self._measurement_notes(engagement_lines, attribution),
        }

    # ------------------------------------------------------------------
    # Action
    # ------------------------------------------------------------------

    def action_print_report(self):
        self.ensure_one()
        self._checked_brand()
        return self.env.ref(
            'social_marketing_agency.action_report_social_brand_performance'
        ).report_action(self)
