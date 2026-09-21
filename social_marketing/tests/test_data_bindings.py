# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase, tagged

from ..models.social_data_binding_core import (
    collect_tokens,
    substitute_tokens,
    web_image_source,
)


@tagged('post_install', '-at_install')
class TestDataBindings(TransactionCase):
    """ Data bindings resolve template tokens by lookup, never by
    evaluation. Most of these tests exist to pin that property down: an
    unknown token, a mismatched model or an unreadable field all have to
    produce an empty string rather than reach anything. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.currency_model = cls.env['ir.model']._get('res.currency')
        cls.template = cls.env['social.image.template'].create({
            'name': 'Binding Template',
        })
        cls.partner = cls.env['res.partner'].create({
            'name': 'Acme Industriplast',
            'function': False,
        })

    def _field(self, model_name, field_name):
        return self.env['ir.model.fields']._get(model_name, field_name)

    def _binding(self, token, model_name, field_name, **kw):
        values = {
            'name': token,
            'model_id': self.env['ir.model']._get(model_name).id,
            'field_id': self._field(model_name, field_name).id,
        }
        values.setdefault('template_id', self.template.id)
        values.update(kw)
        return self.env['social.data.binding'].create(values)

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def test_token_resolves_to_field_value(self):
        self._binding('partner_name', 'res.partner', 'name')
        self.assertEqual(
            self.template.render_bound_text('Hello {{ partner_name }}!', self.partner),
            'Hello Acme Industriplast!')

    def test_token_tolerates_internal_whitespace(self):
        self._binding('partner_name', 'res.partner', 'name')
        self.assertEqual(
            self.template.render_bound_text('{{partner_name}}/{{   partner_name   }}', self.partner),
            'Acme Industriplast/Acme Industriplast')

    def test_empty_source_field_inserts_nothing(self):
        self._binding('job', 'res.partner', 'function')
        self.assertEqual(
            self.template.render_bound_text('[{{ job }}]', self.partner), '[]')

    def test_unknown_token_renders_empty(self):
        """ The security property: a token nobody registered is dropped,
        not evaluated and not left visible. """
        self._binding('partner_name', 'res.partner', 'name')
        rendered = self.template.render_bound_text(
            "A{{ res.company.name }}B{{ nope }}C{{ __import__('os') }}D",
            self.partner)
        self.assertEqual(rendered, 'ABCD')

    def test_field_of_other_model_renders_empty(self):
        """ A binding on res.currency handed a res.partner reads nothing. """
        binding = self._binding('rate', 'res.currency', 'rounding')
        self.assertEqual(binding._resolve_value(self.partner), '')
        self.assertEqual(
            self.template.render_bound_text('[{{ rate }}]', self.partner), '[]')

    def test_many2one_resolves_to_display_name(self):
        country = self.env.ref('base.se')
        self.partner.country_id = country
        self._binding('country', 'res.partner', 'country_id')
        self.assertEqual(
            self.template.render_bound_text('{{ country }}', self.partner),
            country.display_name)

    def test_float_is_formatted_not_a_bare_python_float(self):
        currency = self.env.ref('base.EUR')
        currency.rounding = 0.01
        binding = self._binding('rounding', 'res.currency', 'rounding')
        rendered = binding._resolve_value(currency)
        self.assertNotEqual(rendered, str(currency.rounding))
        self.assertNotEqual(rendered, '0.01')
        decimals = rendered.replace(',', '.').split('.')[-1]
        self.assertEqual(
            len(decimals), 6,
            "float must respect the field digits, got %r" % rendered)

    def test_binary_field_resolves_to_web_image_source(self):
        self.partner.image_1920 = (
            b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGP6zwAA'
            b'AgcBApocMXEAAAAASUVORK5CYII=')
        binding = self._binding('logo', 'res.partner', 'image_1920')
        expected = '/web/image/res.partner/%s/image_1920' % self.partner.id
        self.assertEqual(binding._resolve_image_source(self.partner), expected)
        self.assertEqual(binding._resolve_value(self.partner), '')
        self.assertEqual(
            self.template.get_binding_values(self.partner), {'logo': expected})

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------

    def test_exactly_one_owner_required(self):
        post_template = self.env['social_marketing.post.template'].create({
            'message': '<p>Hello</p>',
        })
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._binding('orphan', 'res.partner', 'name', template_id=False)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._binding(
                'both', 'res.partner', 'name',
                post_template_id=post_template.id)

    def test_field_must_belong_to_model(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env['social.data.binding'].create({
                'name': 'mismatch',
                'template_id': self.template.id,
                'model_id': self.partner_model.id,
                'field_id': self._field('res.currency', 'rounding').id,
            })

    def test_name_format_is_enforced(self):
        for bad in ('foo.bar', '1abc', 'has space', 'foo-bar'):
            with self.assertRaises(ValidationError, msg="accepted %r" % bad), \
                    self.cr.savepoint():
                self._binding(bad, 'res.partner', 'name')

    def test_name_unique_per_template(self):
        self._binding('partner_name', 'res.partner', 'name')
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._binding('partner_name', 'res.partner', 'display_name')

    # ------------------------------------------------------------------
    # Post template side
    # ------------------------------------------------------------------

    def test_post_template_bindings(self):
        post_template = self.env['social_marketing.post.template'].create({
            'message': '<p>Buy from {{ partner_name }} today {{ ghost }}</p>',
        })
        self._binding(
            'partner_name', 'res.partner', 'name',
            template_id=False, post_template_id=post_template.id)
        rendered = post_template.render_bound_message(self.partner)
        self.assertIn('Buy from Acme Industriplast today', rendered)
        self.assertNotIn('{{', rendered)

    # ------------------------------------------------------------------
    # Pure core
    # ------------------------------------------------------------------

    def test_core_substitution_is_pure_lookup(self):
        self.assertEqual(substitute_tokens('a{{ x }}b', {'x': 'X'}), 'aXb')
        self.assertEqual(substitute_tokens('a{{ x }}b', {}), 'ab')
        self.assertEqual(substitute_tokens('a{{ 1 + 1 }}b', {}), 'ab')
        self.assertEqual(substitute_tokens('', {'x': 'X'}), '')
        self.assertEqual(substitute_tokens(None, {}), '')

    def test_core_collect_tokens(self):
        self.assertEqual(
            collect_tokens('{{ a }} {{b}} {{ a }}'), ['a', 'b'])

    def test_core_web_image_source(self):
        self.assertEqual(
            web_image_source('res.partner', 7, 'image_1920'),
            '/web/image/res.partner/7/image_1920')
        self.assertEqual(web_image_source('res.partner', False, 'x'), '')


class TestDataBindingAccess(TransactionCase):
    """Creating a binding is a manager action.

    A binding names a model and a field, and the renderer will read that
    field. Whoever can create one therefore chooses what the render pulls out
    of the database. Resolution runs unsudoed, so record rules still apply and
    a user cannot read past their own rights, but choosing the target is a
    configuration act rather than an editing one, and it belongs with the
    people who configure templates.
    """

    def setUp(self):
        super().setUp()
        self.template = self.env['social.image.template'].create({
            'name': 'Access template'})
        self.partner_model = self.env['ir.model']._get('res.partner')
        self.name_field = self.env['ir.model.fields']._get(
            'res.partner', 'name')

    def _vals(self):
        return {
            'name': 'partner_name',
            'model_id': self.partner_model.id,
            'field_id': self.name_field.id,
            'template_id': self.template.id,
        }

    def test_marketing_user_cannot_create_a_binding(self):
        user = self.env['res.users'].create({
            'name': 'Binding User',
            'login': 'binding_user_test',
            'groups_id': [(4, self.env.ref(
                'social_marketing.group_social_marketing_user').id)],
        })
        with self.assertRaises(AccessError):
            self.env['social.data.binding'].with_user(user).create(
                self._vals())

    def test_marketing_manager_can_create_a_binding(self):
        user = self.env['res.users'].create({
            'name': 'Binding Manager',
            'login': 'binding_manager_test',
            'groups_id': [(4, self.env.ref(
                'social_marketing.group_social_marketing_manager').id)],
        })
        binding = self.env['social.data.binding'].with_user(user).create(
            self._vals())
        self.assertTrue(binding.id)
