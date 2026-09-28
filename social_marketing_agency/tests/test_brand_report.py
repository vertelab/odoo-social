# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

""" The customer facing brand report.

The report is the document a customer judges the retainer by, so the tests
cover the three ways it could lie: wrong totals, a brand shown to someone who
must not see it, and an attribution section that reports zero leads when the
truth is that leads were never measured at all.
"""

from datetime import datetime, timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestBrandReport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # wkhtmltopdf resolves the stylesheet links in the report through
        # this url. The http server cannot answer while the tests are running,
        # so it is pointed at a closed port: the fetch fails at once instead of
        # blocking, and the pdf is produced unstyled but real.
        cls.env['ir.config_parameter'].sudo().set_param(
            'report.url', 'http://127.0.0.1:1')
        cls.today = fields.Date.context_today(cls.env['social.brand'])
        cls.date_from = cls.today - timedelta(days=10)
        cls.date_to = cls.today + timedelta(days=1)

        cls.media_a = cls.env['social_marketing.media'].create({'name': 'Reportbook'})
        cls.media_b = cls.env['social_marketing.media'].create({'name': 'Reportagram'})

        cls.customer_a = cls.env['res.partner'].create({
            'name': 'Report Customer A', 'is_company': True,
        })
        cls.customer_b = cls.env['res.partner'].create({
            'name': 'Report Customer B', 'is_company': True,
        })
        cls.brand_a = cls.env['social.brand'].create({
            'name': 'Report Brand A', 'partner_id': cls.customer_a.id,
        })
        cls.brand_b = cls.env['social.brand'].create({
            'name': 'Report Brand B', 'partner_id': cls.customer_b.id,
        })

        cls.account_a = cls._make_account('Report Account A', cls.media_a)
        cls.account_b = cls._make_account('Report Account B', cls.media_b)

        # Two posts inside the period, one on both platforms and one on a
        # single platform, plus one older post that must stay out of it.
        cls.post_one = cls._make_post(
            cls.brand_a, cls.account_a + cls.account_b, 'Post one in the period',
            cls.today - timedelta(days=5))
        cls.post_two = cls._make_post(
            cls.brand_a, cls.account_a, 'Post two in the period',
            cls.today - timedelta(days=2))
        cls.post_old = cls._make_post(
            cls.brand_a, cls.account_a, 'Post from long before the period',
            cls.today - timedelta(days=400))
        cls.post_other_brand = cls._make_post(
            cls.brand_b, cls.account_a, 'Post of the other brand',
            cls.today - timedelta(days=3))

        # Engagement snapshots. The newest snapshot inside the period is the
        # value for the period, so the earlier 10 must not be added to it.
        stat_date = cls.today - timedelta(days=4)
        for live_post in cls.post_one.live_post_ids:
            cls._make_stat(live_post, 'engagement', 10.0, stat_date - timedelta(days=1))
            cls._make_stat(live_post, 'engagement', 50.0, stat_date)
            cls._make_stat(live_post, 'likes', 7.0, stat_date)
        for live_post in cls.post_two.live_post_ids:
            cls._make_stat(live_post, 'engagement', 30.0, stat_date)
            cls._make_stat(live_post, 'likes', 3.0, stat_date)

        cls.env['social.publish.pipeline.step'].create([{
            'post_id': cls.post_one.id, 'stage': 'submitted', 'state': 'done',
        }, {
            'post_id': cls.post_one.id, 'stage': 'approved', 'state': 'done',
        }, {
            'post_id': cls.post_two.id, 'stage': 'approved', 'state': 'done',
        }])

    @classmethod
    def _make_account(cls, name, media):
        return cls.env['social_marketing.account'].create({
            'name': name,
            'media_id': media.id,
            'utm_medium_id': cls.env['utm.medium'].create({'name': 'Medium ' + name}).id,
        })

    @classmethod
    def _make_post(cls, brand, accounts, message, published_day):
        post = cls.env['social_marketing.post'].create({
            'message': message,
            'brand_id': brand.id,
            'account_ids': [(6, 0, accounts.ids)],
        })
        for account in accounts:
            cls.env['social_marketing.live.post'].create({
                'post_id': post.id,
                'social_account_id': account.id,
                'state': 'posted',
            })
        post.write({
            'state': 'posted',
            'published_date': datetime.combine(
                published_day, datetime.min.time()) + timedelta(hours=12),
        })
        return post

    @classmethod
    def _make_stat(cls, live_post, metric, value, date):
        return cls.env['social_marketing.live_post.stat'].create({
            'live_post_id': live_post.id,
            'metric': metric,
            'value': value,
            'date': date,
        })

    def _wizard(self, brand, date_from=None, date_to=None, user=None):
        model = self.env['social.brand.report.wizard']
        if user is not None:
            model = model.with_user(user)
        return model.create({
            'brand_id': brand.id,
            'date_from': date_from or self.date_from,
            'date_to': date_to or self.date_to,
        })

    # ------------------------------------------------------------------
    # Totals
    # ------------------------------------------------------------------

    def test_totals_for_a_brand_with_posts_stats_and_approvals(self):
        data = self._wizard(self.brand_a)._report_data()

        self.assertEqual(data['post_count'], 2)
        self.assertEqual(data['publication_count'], 3)
        self.assertEqual(
            {line['name']: line['count'] for line in data['platform_lines']},
            {'Reportbook': 2, 'Reportagram': 1})

        engagement = {line['label']: line for line in data['engagement_lines']}
        # 50 on each of the two publications of post one, 30 on post two.
        self.assertTrue(engagement['Engagements']['measured'])
        self.assertEqual(engagement['Engagements']['value'], 130)
        self.assertTrue(engagement['Likes']['measured'])
        self.assertEqual(engagement['Likes']['value'], 17)
        self.assertFalse(engagement['Comments']['measured'])
        self.assertFalse(engagement['Shares']['measured'])

        self.assertEqual(len(data['top_post_lines']), 2)
        self.assertEqual(data['top_post_lines'][0]['engagement'], 100)
        self.assertEqual(data['top_post_lines'][0]['platforms'],
                         'Reportagram, Reportbook')
        self.assertEqual(data['top_post_lines'][1]['engagement'], 30)

        self.assertEqual(data['activity']['step_count'], 3)
        self.assertEqual(data['activity']['approval_count'], 2)
        self.assertEqual(len(data['activity']['approval_lines']), 2)

    def test_other_brands_and_other_periods_stay_out(self):
        data = self._wizard(self.brand_b)._report_data()
        self.assertEqual(data['post_count'], 1)
        self.assertEqual(data['activity']['step_count'], 0)

    def test_top_post_count_limits_the_list(self):
        wizard = self._wizard(self.brand_a)
        wizard.top_post_count = 1
        self.assertEqual(len(wizard._report_data()['top_post_lines']), 1)

    # ------------------------------------------------------------------
    # Empty period
    # ------------------------------------------------------------------

    def test_empty_period_reports_the_emptiness_instead_of_crashing(self):
        wizard = self._wizard(
            self.brand_a,
            date_from=self.today - timedelta(days=800),
            date_to=self.today - timedelta(days=700))
        data = wizard._report_data()

        self.assertEqual(data['post_count'], 0)
        self.assertEqual(data['platform_lines'], [])
        self.assertEqual(data['top_post_lines'], [])
        self.assertEqual(data['activity']['step_count'], 0)
        self.assertTrue(
            all(not line['measured'] for line in data['engagement_lines']),
            "An empty period measured nothing, so no metric may claim a value.")
        self.assertTrue(data['notes'])

        pdf, report_type = self.env['ir.actions.report'].with_context(
            force_report_rendering=True)._render_qweb_pdf(
            'social_marketing_agency.action_report_social_brand_performance',
            wizard.ids)
        self.assertEqual(report_type, 'pdf')
        self.assertTrue(pdf.startswith(b'%PDF'))

    # ------------------------------------------------------------------
    # Optional bridges
    # ------------------------------------------------------------------

    def test_attribution_follows_the_installed_bridges(self):
        """Present with the bridges installed, absent without them."""
        data = self._wizard(self.brand_a)._report_data()
        attribution = data['attribution']
        notes = ' '.join(data['notes'])
        post_fields = self.env['social_marketing.post']._fields

        if 'crm_lead_count' in post_fields:
            self.assertIsNotNone(attribution['crm'])
            self.assertNotIn('Leads and pipeline value are not measured', notes)
        else:
            self.assertIsNone(attribution['crm'])
            self.assertIn('Leads and pipeline value are not measured', notes)

        if 'sale_order_count' in post_fields:
            self.assertIsNotNone(attribution['sale'])
            self.assertNotIn('Orders and order revenue are not measured', notes)
        else:
            self.assertIsNone(attribution['sale'])
            self.assertIn('Orders and order revenue are not measured', notes)

        expected = any(
            attribution[key] is not None for key in ('crm', 'sale', 'mailing'))
        self.assertEqual(attribution['available'], expected)

    def test_attribution_is_absent_when_the_figures_cannot_be_read(self):
        """A user without the sales rights gets no attribution and a note.

        This is the same absent direction as an uninstalled bridge, and it is
        exercised whether or not the bridges are installed: unreadable and
        uninstalled must both read as unmeasured, never as zero.
        """
        user = self._make_internal_user('report.marketer@example.com', [
            'social_marketing.group_social_marketing_user',
        ])
        data = self._wizard(self.brand_a, user=user)._report_data()

        self.assertIsNone(data['attribution']['crm'])
        self.assertIsNone(data['attribution']['sale'])
        notes = ' '.join(data['notes'])
        self.assertIn('Leads and pipeline value are not measured', notes)
        self.assertIn('Orders and order revenue are not measured', notes)

    def _make_internal_user(self, login, group_xmlids):
        groups = self.env['res.groups'].browse(
            [self.env.ref(xmlid).id for xmlid in group_xmlids])
        return self.env['res.users'].create({
            'name': login,
            'login': login,
            'groups_id': [(6, 0, (groups | self.env.ref('base.group_user')).ids)],
        })

    # ------------------------------------------------------------------
    # Brand isolation
    # ------------------------------------------------------------------

    def test_agency_user_of_brand_a_cannot_report_brand_b(self):
        user = self._make_internal_user('report.agency@example.com', [
            'social_marketing.group_social_marketing_user',
            'social_marketing_agency.group_social_agency_brand_user',
        ])
        user.brand_ids = [(6, 0, [self.brand_a.id])]

        self._wizard(self.brand_a, user=user)._report_data()

        with self.assertRaises(AccessError):
            self._wizard(self.brand_b, user=user)._report_data()

    def test_customer_of_brand_a_cannot_report_brand_b(self):
        contact = self.env['res.partner'].create({
            'name': 'Report Alice', 'parent_id': self.customer_a.id,
            'email': 'report.alice@example.com',
        })
        user = self.env['res.users'].create({
            'name': 'Report Alice',
            'partner_id': contact.id,
            'login': 'report.alice@example.com',
            'groups_id': [(6, 0, [
                self.env.ref('base.group_portal').id,
                self.env.ref(
                    'social_marketing_agency.group_social_customer_approver').id,
            ])],
        })
        with self.assertRaises(AccessError):
            self._wizard(self.brand_b, user=user)._report_data()

    def test_printing_checks_the_brand_before_rendering(self):
        user = self._make_internal_user('report.agency2@example.com', [
            'social_marketing.group_social_marketing_user',
            'social_marketing_agency.group_social_agency_brand_user',
        ])
        user.brand_ids = [(6, 0, [self.brand_a.id])]
        with self.assertRaises(AccessError):
            self._wizard(self.brand_b, user=user).action_print_report()

    # ------------------------------------------------------------------
    # The document itself
    # ------------------------------------------------------------------

    def test_report_renders_actual_pdf_bytes(self):
        wizard = self._wizard(self.brand_a)
        pdf, report_type = self.env['ir.actions.report'].with_context(
            force_report_rendering=True)._render_qweb_pdf(
            'social_marketing_agency.action_report_social_brand_performance',
            wizard.ids)
        self.assertEqual(report_type, 'pdf')
        self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertGreater(len(pdf), 1000)

    def test_report_html_names_the_brand_and_the_customer(self):
        wizard = self._wizard(self.brand_a)
        html = self.env['ir.actions.report']._render_qweb_html(
            'social_marketing_agency.action_report_social_brand_performance',
            wizard.ids)[0].decode()
        self.assertIn('Report Brand A', html)
        self.assertIn('Report Customer A', html)
        self.assertIn('Not measured', html)
