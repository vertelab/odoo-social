# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import date, datetime, timedelta

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.social_marketing_agency.models.content_source_core import (
    compute_next_occurrence,
    float_to_time_parts,
    pick_next_id,
)


@tagged('post_install', '-at_install')
class TestContentSourceCore(TransactionCase):
    """Pure scheduling logic, no database involved."""

    def test_float_to_time_parts(self):
        self.assertEqual(float_to_time_parts(8.0), (8, 0, 0))
        # 08:47 as Odoo float time
        self.assertEqual(float_to_time_parts(8 + 47 / 60.0), (8, 47, 0))

    def test_daily_same_day_when_time_still_ahead(self):
        got = compute_next_occurrence(
            datetime(2026, 3, 4, 6, 0, 0), 'daily', time_of_day=8.0)
        self.assertEqual(got, datetime(2026, 3, 4, 8, 0, 0))

    def test_daily_rolls_to_tomorrow_when_time_has_passed(self):
        got = compute_next_occurrence(
            datetime(2026, 3, 4, 9, 0, 0), 'daily', time_of_day=8.0)
        self.assertEqual(got, datetime(2026, 3, 5, 8, 0, 0))

    def test_daily_exact_boundary_is_strictly_after(self):
        got = compute_next_occurrence(
            datetime(2026, 3, 4, 8, 0, 0), 'daily', time_of_day=8.0)
        self.assertEqual(got, datetime(2026, 3, 5, 8, 0, 0))

    def test_weekly_monday_0847(self):
        """One post every Monday at 08:47, asked on a Thursday."""
        got = compute_next_occurrence(
            datetime(2026, 3, 5, 12, 0, 0),  # Thursday
            'weekly', weekday='mon', time_of_day=8 + 47 / 60.0)
        self.assertEqual(got, datetime(2026, 3, 9, 8, 47, 0))
        self.assertEqual(got.weekday(), 0)

    def test_weekly_same_day_before_time(self):
        got = compute_next_occurrence(
            datetime(2026, 3, 9, 7, 0, 0),  # Monday, before 08:47
            'weekly', weekday='mon', time_of_day=8 + 47 / 60.0)
        self.assertEqual(got, datetime(2026, 3, 9, 8, 47, 0))

    def test_weekly_same_day_after_time_jumps_a_week(self):
        got = compute_next_occurrence(
            datetime(2026, 3, 9, 9, 0, 0),  # Monday, after 08:47
            'weekly', weekday='mon', time_of_day=8 + 47 / 60.0)
        self.assertEqual(got, datetime(2026, 3, 16, 8, 47, 0))

    def test_monthly_this_month_and_next(self):
        got = compute_next_occurrence(
            datetime(2026, 3, 4, 12, 0, 0), 'monthly',
            day_of_month=15, time_of_day=8.0)
        self.assertEqual(got, datetime(2026, 3, 15, 8, 0, 0))

        got = compute_next_occurrence(
            datetime(2026, 3, 20, 12, 0, 0), 'monthly',
            day_of_month=15, time_of_day=8.0)
        self.assertEqual(got, datetime(2026, 4, 15, 8, 0, 0))

    def test_monthly_day_clamped_to_month_length(self):
        got = compute_next_occurrence(
            datetime(2026, 2, 1, 0, 0, 0), 'monthly',
            day_of_month=31, time_of_day=8.0)
        self.assertEqual(got, datetime(2026, 2, 28, 8, 0, 0))

    def test_monthly_year_rollover(self):
        got = compute_next_occurrence(
            datetime(2026, 12, 20, 0, 0, 0), 'monthly',
            day_of_month=5, time_of_day=8.0)
        self.assertEqual(got, datetime(2027, 1, 5, 8, 0, 0))

    def test_unknown_interval_raises(self):
        with self.assertRaises(ValueError):
            compute_next_occurrence(datetime(2026, 1, 1), 'yearly')

    def test_pick_next_id_rotation(self):
        self.assertEqual(pick_next_id([1, 2, 3], []), (1, False))
        self.assertEqual(pick_next_id([1, 2, 3], [1]), (2, False))
        self.assertEqual(pick_next_id([1, 2, 3], [1, 2, 3]), (1, True))
        self.assertEqual(pick_next_id([], [1]), (None, False))

    def test_core_holds_no_second_renderer(self):
        """Substitution lives once, in the data binding core.

        This module used to carry its own token regex and its own
        ``render_message``. Both are gone, and this test exists so that a
        future edit cannot quietly bring a second substitution path back.
        """
        from odoo.addons.social_marketing_agency.models import (
            content_source_core,
        )
        for gone in ('render_message', 'extract_tokens', 'TOKEN_RE'):
            self.assertFalse(
                hasattr(content_source_core, gone),
                '%s must not come back, bindings are the only renderer'
                % gone)

        from odoo.addons.social_marketing.models.social_data_binding_core \
            import substitute_tokens
        self.assertEqual(
            substitute_tokens('<p>{{ name }} rocks</p>', {'name': 'Widget'}),
            '<p>Widget rocks</p>')


@tagged('post_install', '-at_install')
class TestContentSource(TransactionCase):
    """Spec: social-content-sources."""

    def setUp(self):
        super().setUp()
        self.customer_a = self.env['res.partner'].create({
            'name': 'Content Customer A', 'is_company': True,
        })
        self.customer_b = self.env['res.partner'].create({
            'name': 'Content Customer B', 'is_company': True,
        })
        self.brand_a = self.env['social.brand'].create({
            'name': 'Content Brand A', 'partner_id': self.customer_a.id,
        })
        self.brand_b = self.env['social.brand'].create({
            'name': 'Content Brand B', 'partner_id': self.customer_b.id,
        })
        # social.agency.document is brand scoped, which makes it a convenient
        # stand-in for "any Odoo model with a brand_id" without pulling the
        # sale/stock chain into the test.
        self.doc_model = self.env['ir.model']._get('social.agency.document')
        self.doc_name_field = self.env['ir.model.fields']._get(
            'social.agency.document', 'name')
        self.template = self.env['social_marketing.post.template'].create({
            'message': '<p>Look at {{ name }}</p>',
        })
        # {{ name }} is only a token because a binding registers it. Without
        # this record the token resolves to nothing, and a source using the
        # template refuses to be saved.
        self.binding = self.env['social.data.binding'].create({
            'name': 'name',
            'post_template_id': self.template.id,
            'model_id': self.doc_model.id,
            'field_id': self.doc_name_field.id,
        })
        self.doc_type = self.env['social.agency.document.type'].create({
            'name': 'Content Source Test Type',
        })

    def _make_doc(self, name, brand):
        return self.env['social.agency.document'].create({
            'name': name,
            'brand_id': brand.id,
            'type_id': self.doc_type.id,
        })

    def _make_source(self, brand, **kw):
        vals = {
            'name': 'Source for %s' % brand.name,
            'brand_id': brand.id,
            'model_id': self.doc_model.id,
            'domain': '[]',
            'post_template_id': self.template.id,
            'interval_type': 'weekly',
            'weekday': 'mon',
            'time_of_day': 8 + 47 / 60.0,
        }
        vals.update(kw)
        return self.env['social.content.source'].create(vals)

    # ── Scheduling through the model ─────────────────────────────────────

    def test_next_occurrence_monday_0847(self):
        source = self._make_source(self.brand_a)
        got = source._next_occurrence(datetime(2026, 3, 5, 12, 0, 0))
        self.assertEqual(got, datetime(2026, 3, 9, 8, 47, 0))

    def test_next_run_is_computed_on_create(self):
        source = self._make_source(self.brand_a)
        self.assertTrue(source.next_run)
        self.assertEqual(source.next_run.hour, 8)
        self.assertEqual(source.next_run.minute, 47)
        self.assertEqual(source.next_run.weekday(), 0)

    def test_next_run_daily_and_monthly(self):
        daily = self._make_source(
            self.brand_a, interval_type='daily', time_of_day=6.5)
        self.assertEqual((daily.next_run.hour, daily.next_run.minute), (6, 30))

        monthly = self._make_source(
            self.brand_a, interval_type='monthly', day_of_month=15,
            time_of_day=9.0)
        self.assertEqual(monthly.next_run.day, 15)
        self.assertEqual(monthly.next_run.hour, 9)

    # ── Rotation ─────────────────────────────────────────────────────────

    def test_rotation_does_not_repeat_until_pool_exhausted(self):
        docs = [self._make_doc('Doc %s' % i, self.brand_a) for i in range(3)]
        source = self._make_source(self.brand_a)

        picked = []
        for _i in range(3):
            post = source._generate_post()
            self.assertTrue(post)
            log = source.log_ids.filtered(lambda entry: entry.post_id == post)
            self.assertEqual(len(log), 1)
            picked.append(log.res_id)

        self.assertEqual(sorted(picked), sorted(d.id for d in docs))
        self.assertEqual(len(set(picked)), 3, 'a record was repeated')
        self.assertEqual(picked, sorted(d.id for d in docs),
                         'rotation must be stable, ascending id')

    def test_rotation_starts_over_when_pool_exhausted(self):
        docs = [self._make_doc('Doc %s' % i, self.brand_a) for i in range(2)]
        source = self._make_source(self.brand_a)

        for _i in range(2):
            source._generate_post()
        self.assertEqual(source.cycle, 1)

        post = source._generate_post()
        self.assertEqual(source.cycle, 2, 'a new cycle must have started')
        restart_log = source.log_ids.filtered(
            lambda entry: entry.post_id == post)
        self.assertEqual(restart_log.res_id, docs[0].id)
        self.assertEqual(restart_log.cycle, 2)
        self.assertEqual(len(source.log_ids), 3)

    def test_no_qualifying_record_generates_nothing(self):
        source = self._make_source(self.brand_a)
        self.assertFalse(source._generate_post())
        self.assertFalse(source.log_ids)

    # ── Generated posts ──────────────────────────────────────────────────

    def test_generated_post_lands_in_draft(self):
        self._make_doc('Doc', self.brand_a)
        source = self._make_source(self.brand_a)
        post = source._generate_post()
        self.assertEqual(post.state, 'draft')
        self.assertFalse(post.published_date)
        self.assertFalse(post.live_post_ids)

    def test_generated_post_renders_template_and_carries_brand(self):
        """End to end: registered binding, generated draft, resolved value."""
        doc = self._make_doc('Blue Widget', self.brand_a)
        source = self._make_source(self.brand_a)
        post = source._generate_post()
        self.assertEqual(post.message, '<p>Look at Blue Widget</p>')
        self.assertIn(doc.name, post.message)
        self.assertEqual(post.state, 'draft')
        self.assertEqual(post.brand_id, self.brand_a)

    def test_binding_formatting_is_the_one_used_by_generation(self):
        """Generation gets the binding model's formatting, not str()."""
        template = self.env['social_marketing.post.template'].create({
            'message': '<p>{{ kind }}</p>',
        })
        self.env['social.data.binding'].create({
            'name': 'kind',
            'post_template_id': template.id,
            'model_id': self.doc_model.id,
            'field_id': self.env['ir.model.fields']._get(
                'social.agency.document', 'type_id').id,
        })
        self._make_doc('Doc', self.brand_a)
        source = self._make_source(self.brand_a, post_template_id=template.id)
        post = source._generate_post()
        # A many2one renders as its display name, never as a raw recordset.
        self.assertEqual(
            post.message, '<p>%s</p>' % self.doc_type.display_name)

    def test_unregistered_token_is_refused_at_save_time(self):
        """A source whose template has an unbound token cannot be saved.

        System 2 accepted any field name implicitly. That is exactly what
        made the field picker pointless, so the implicit path is gone and
        the misconfiguration is reported where it is fixable instead of
        producing empty posts forever.
        """
        loose = self.env['social_marketing.post.template'].create({
            'message': '<p>Look at {{ name }} for {{ nobody_bound_this }}</p>',
        })
        self.env['social.data.binding'].create({
            'name': 'name',
            'post_template_id': loose.id,
            'model_id': self.doc_model.id,
            'field_id': self.doc_name_field.id,
        })
        with self.assertRaises(ValidationError) as caught:
            self._make_source(self.brand_a, post_template_id=loose.id)
        self.assertIn('nobody_bound_this', str(caught.exception))

    def test_binding_for_another_model_does_not_count_as_bound(self):
        """A token bound to the wrong model resolves to nothing."""
        wrong = self.env['social_marketing.post.template'].create({
            'message': '<p>{{ name }}</p>',
        })
        partner_model = self.env['ir.model']._get('res.partner')
        self.env['social.data.binding'].create({
            'name': 'name',
            'post_template_id': wrong.id,
            'model_id': partner_model.id,
            'field_id': self.env['ir.model.fields']._get(
                'res.partner', 'name').id,
        })
        with self.assertRaises(ValidationError):
            self._make_source(self.brand_a, post_template_id=wrong.id)

    def test_warning_field_reports_drift_after_the_template_changes(self):
        """The template can drift after the source was saved."""
        source = self._make_source(self.brand_a)
        self.assertFalse(source.unbound_token_warning)
        self.template.message = '<p>Look at {{ name }} and {{ price }}</p>'
        source.invalidate_recordset()
        self.assertEqual(source.unbound_token_warning, 'price')

    def test_empty_render_falls_back_to_display_name(self):
        """A render that comes out empty still yields the record name.

        Deliberate, and it survives the consolidation: an empty message is
        worse than a plain one.
        """
        # A template made of one token bound to a field the record leaves
        # blank renders to nothing at all.
        blank = self.env['social_marketing.post.template'].create({
            'message': '{{ description }}',
        })
        self.env['social.data.binding'].create({
            'name': 'description',
            'post_template_id': blank.id,
            'model_id': self.doc_model.id,
            'field_id': self.env['ir.model.fields']._get(
                'social.agency.document', 'description').id,
        })
        doc = self._make_doc('Fallback Doc', self.brand_a)
        self.assertFalse(doc.description)
        source = self._make_source(self.brand_a, post_template_id=blank.id)
        post = source._generate_post()
        self.assertEqual(post.message, '<p>%s</p>' % doc.display_name)

    def test_source_without_a_template_falls_back_to_display_name(self):
        doc = self._make_doc('No Template Doc', self.brand_a)
        source = self._make_source(self.brand_a, post_template_id=False)
        post = source._generate_post()
        self.assertEqual(post.message, '<p>%s</p>' % doc.display_name)

    def test_generated_post_is_stamped_with_the_campaign(self):
        self._make_doc('Doc', self.brand_a)
        campaign = self.env['utm.campaign'].create({'name': 'Autumn 2026'})
        source = self._make_source(self.brand_a, utm_campaign_id=campaign.id)
        post = source._generate_post()
        self.assertEqual(post.utm_campaign_id, campaign)

    def test_generation_stamps_last_run_and_log(self):
        doc = self._make_doc('Doc', self.brand_a)
        source = self._make_source(self.brand_a)
        post = source._generate_post()
        self.assertTrue(source.last_run)
        self.assertEqual(len(source.log_ids), 1)
        log = source.log_ids
        self.assertEqual(log.res_id, doc.id)
        self.assertEqual(log.post_id, post)
        self.assertEqual(log.brand_id, self.brand_a)
        self.assertEqual(log.res_model, 'social.agency.document')

    def test_cron_only_runs_due_sources(self):
        self._make_doc('Doc A', self.brand_a)
        source = self._make_source(self.brand_a)
        # An old last_run pushes next_run into the past, making it due.
        source.last_run = datetime(2020, 1, 1, 8, 0, 0)
        self.assertLess(source.next_run, datetime(2021, 1, 1))
        self.env['social.content.source']._cron_generate_posts()
        self.assertEqual(len(source.log_ids), 1)
        self.assertEqual(source.log_ids.post_id.state, 'draft')

    # ── Brand isolation ──────────────────────────────────────────────────

    def test_source_never_picks_up_another_brands_data(self):
        doc_b = self._make_doc('B only', self.brand_b)
        source_a = self._make_source(self.brand_a)

        self.assertFalse(source_a._pick_next_record())
        self.assertFalse(source_a._generate_post())

        doc_a = self._make_doc('A only', self.brand_a)
        picked = source_a._pick_next_record()
        self.assertEqual(picked, doc_a)
        self.assertNotEqual(picked, doc_b)

        # And the other way around.
        source_b = self._make_source(self.brand_b)
        self.assertEqual(source_b._pick_next_record(), doc_b)

    def test_brand_scope_survives_a_wide_open_domain(self):
        self._make_doc('B only', self.brand_b)
        doc_a = self._make_doc('A only', self.brand_a)
        source = self._make_source(self.brand_a, domain="[(1, '=', 1)]")
        self.assertEqual(source._candidate_records(), doc_a)


@tagged('post_install', '-at_install')
class TestPostReusePool(TransactionCase):
    """Spec: social-content-sources, reuse pool level one."""

    def setUp(self):
        super().setUp()
        partner = self.env['res.partner'].create({
            'name': 'Reuse Customer', 'is_company': True,
        })
        self.brand = self.env['social.brand'].create({
            'name': 'Reuse Brand', 'partner_id': partner.id,
        })
        other_partner = self.env['res.partner'].create({
            'name': 'Other Customer', 'is_company': True,
        })
        self.other_brand = self.env['social.brand'].create({
            'name': 'Other Brand', 'partner_id': other_partner.id,
        })
        self.today = date(2026, 6, 1)

    def _make_post(self, message, brand, evergreen=True, state='posted',
                   cooldown=30, last_reused=None):
        post = self.env['social_marketing.post'].create({
            'message': '<p>%s</p>' % message,
            'brand_id': brand.id,
            'is_evergreen': evergreen,
            'reuse_cooldown_days': cooldown,
        })
        vals = {'state': state}
        if last_reused:
            vals['last_reused_date'] = last_reused
        post.write(vals)
        return post

    def _eligible(self):
        return self.env['social_marketing.post']._get_reusable_posts(
            self.brand, reference_date=self.today)

    def test_cooldown_boundary(self):
        exactly = self._make_post(
            'exactly at cooldown', self.brand, cooldown=30,
            last_reused=self.today - timedelta(days=30))
        one_day_short = self._make_post(
            'one day short', self.brand, cooldown=30,
            last_reused=self.today - timedelta(days=29))

        eligible = self._eligible()
        self.assertIn(exactly, eligible)
        self.assertNotIn(one_day_short, eligible)

    def test_non_evergreen_and_unpublished_are_excluded(self):
        not_evergreen = self._make_post(
            'not evergreen', self.brand, evergreen=False,
            last_reused=self.today - timedelta(days=90))
        not_published = self._make_post(
            'still draft', self.brand, state='draft',
            last_reused=self.today - timedelta(days=90))
        good = self._make_post(
            'good', self.brand, last_reused=self.today - timedelta(days=90))

        eligible = self._eligible()
        self.assertEqual(eligible, good)
        self.assertNotIn(not_evergreen, eligible)
        self.assertNotIn(not_published, eligible)

    def test_order_is_oldest_reused_first(self):
        recent = self._make_post(
            'recent', self.brand, last_reused=self.today - timedelta(days=40))
        oldest = self._make_post(
            'oldest', self.brand, last_reused=self.today - timedelta(days=200))
        middle = self._make_post(
            'middle', self.brand, last_reused=self.today - timedelta(days=100))

        self.assertEqual(
            list(self._eligible()), [oldest, middle, recent])

    def test_other_brands_posts_are_never_offered(self):
        mine = self._make_post(
            'mine', self.brand, last_reused=self.today - timedelta(days=90))
        theirs = self._make_post(
            'theirs', self.other_brand,
            last_reused=self.today - timedelta(days=90))

        eligible = self._eligible()
        self.assertIn(mine, eligible)
        self.assertNotIn(theirs, eligible)

    def test_mark_reused_restarts_the_cooldown(self):
        post = self._make_post(
            'post', self.brand, last_reused=self.today - timedelta(days=90))
        self.assertIn(post, self._eligible())
        post._mark_reused(reference_date=self.today)
        self.assertEqual(post.last_reused_date, self.today)
        self.assertNotIn(post, self._eligible())


class TestContentSourceTimezone(TransactionCase):
    """The schedule is expressed in the source's timezone, not in UTC.

    Odoo stores naive UTC, so a source asking for Monday 08:47 in Stockholm
    must come back as 07:47 UTC in winter and 06:47 UTC in summer. Getting
    this wrong is invisible in tests that only ever use UTC, and shows up in
    production as posts going out an hour late for half the year.
    """

    def setUp(self):
        super().setUp()
        self.brand = self.env['social.brand'].create({
            'name': 'TZ Brand',
            'partner_id': self.env['res.partner'].create({
                'name': 'TZ Customer', 'is_company': True}).id,
        })
        self.doc_model = self.env['ir.model']._get('social.agency.document')

    def _source(self, tz):
        return self.env['social.content.source'].create({
            'name': 'TZ source %s' % tz,
            'brand_id': self.brand.id,
            'model_id': self.doc_model.id,
            'domain': '[]',
            'interval_type': 'weekly',
            'weekday': 'mon',
            'time_of_day': 8 + 47 / 60.0,
            'tz': tz,
        })

    def test_winter_time_converts_to_utc(self):
        source = self._source('Europe/Stockholm')
        got = source._next_occurrence(datetime(2026, 1, 6, 12, 0, 0))
        self.assertEqual(got.hour, 7)
        self.assertEqual(got.minute, 47)

    def test_summer_time_converts_to_utc(self):
        source = self._source('Europe/Stockholm')
        got = source._next_occurrence(datetime(2026, 7, 7, 12, 0, 0))
        self.assertEqual(got.hour, 6)
        self.assertEqual(got.minute, 47)

    def test_utc_source_is_unshifted(self):
        source = self._source('UTC')
        got = source._next_occurrence(datetime(2026, 7, 7, 12, 0, 0))
        self.assertEqual(got.hour, 8)
        self.assertEqual(got.minute, 47)

    def test_result_still_lands_on_the_requested_weekday(self):
        source = self._source('Europe/Stockholm')
        got = source._next_occurrence(datetime(2026, 7, 7, 12, 0, 0))
        self.assertEqual(got.weekday(), 0)
