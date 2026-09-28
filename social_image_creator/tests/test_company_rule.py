# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestTemplateCompanyRule(TransactionCase):
    """Multi-company scoping of image templates (spec: image-templates).

    A marketing user only sees templates of their companies or with no
    company; the marketing manager group sees all templates."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env['res.company'].create({'name': 'RuleCo A'})
        cls.company_b = cls.env['res.company'].create({'name': 'RuleCo B'})
        cls.template_a = cls.env['social.image.template'].create({
            'name': 'Rule Template A',
            'model_id': cls.env['ir.model']._get('res.partner').id,
            'company_id': cls.company_a.id,
        })
        cls.template_b = cls.env['social.image.template'].create({
            'name': 'Rule Template B',
            'model_id': cls.env['ir.model']._get('res.partner').id,
            'company_id': cls.company_b.id,
        })
        cls.template_shared = cls.env['social.image.template'].create({
            'name': 'Rule Template Shared',
            'model_id': cls.env['ir.model']._get('res.partner').id,
            'company_id': False,
        })
        cls.user = cls.env['res.users'].create({
            'name': 'RuleCo User',
            'login': 'ruleco_user',
            'company_id': cls.company_a.id,
            'company_ids': [(6, 0, [cls.company_a.id])],
            'groups_id': [(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.env.ref('social_marketing.group_social_marketing_user').id,
            ])],
        })
        cls.manager = cls.env['res.users'].create({
            'name': 'RuleCo Manager',
            'login': 'ruleco_manager',
            'company_id': cls.company_a.id,
            'company_ids': [(6, 0, [cls.company_a.id])],
            'groups_id': [(6, 0, [
                cls.env.ref('social_marketing.group_social_marketing_manager').id,
            ])],
        })

    def _search_ids(self, user):
        return set(self.env['social.image.template'].with_user(
            user).search([]).ids)

    def test_user_sees_own_company_and_shared(self):
        visible = self._search_ids(self.user)
        self.assertIn(self.template_a.id, visible)
        self.assertIn(self.template_shared.id, visible)
        self.assertNotIn(self.template_b.id, visible)

    def test_user_cannot_read_other_company_template(self):
        template_b = self.template_b.with_user(self.user)
        with self.assertRaises(AccessError):
            template_b.read(['name'])

    def test_manager_sees_all_companies(self):
        visible = self._search_ids(self.manager)
        self.assertIn(self.template_a.id, visible)
        self.assertIn(self.template_shared.id, visible)
        self.assertIn(self.template_b.id, visible)

    def test_manager_can_read_other_company_template(self):
        template_b = self.template_b.with_user(self.manager)
        self.assertEqual(template_b.name, 'Rule Template B')
