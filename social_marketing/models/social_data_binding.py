# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, MissingError, ValidationError
from odoo.tools import format_date, format_datetime
from odoo.tools.misc import formatLang

from .social_data_binding_core import (
    collect_tokens,
    substitute_tokens,
    web_image_source,
)

_logger = logging.getLogger(__name__)

# Tokens stay simple and unambiguous: an identifier, nothing dotted, no
# punctuation. A dotted token would suggest traversal, and traversal is
# exactly what this feature refuses to offer.
NAME_RE = re.compile(r'^[a-zA-Z][a-zA-Z0-9_]*$')


class SocialDataBinding(models.Model):
    """A named link between a template token and one field of one model.

    A binding is the *whole* vocabulary a template has. Rendering looks a
    token up among the bindings registered on the template being rendered
    and reads that one field off the source record. It never evaluates the
    template body, so a template is data and stays data: whoever can write
    a template body gains nothing beyond the fields an administrator chose
    to expose here.
    """

    _name = 'social.data.binding'
    _description = 'Social Data Binding'
    _order = 'sequence asc, id asc'

    name = fields.Char(
        'Token', required=True,
        help="Name used in the template, written as {{ token }}.")
    sequence = fields.Integer('Sequence', default=10)
    model_id = fields.Many2one(
        'ir.model', string='Model', required=True, ondelete='cascade',
        help="The model the source record must belong to.")
    field_id = fields.Many2one(
        'ir.model.fields', string='Field', required=True, ondelete='cascade',
        domain="[('model_id', '=', model_id)]",
        help="The field read off the source record. Picked, never typed.")
    model_name = fields.Char(
        'Model Name', related='model_id.model', readonly=True)
    field_name = fields.Char(
        'Field Name', related='field_id.name', readonly=True)
    template_id = fields.Many2one(
        'social.image.template', string='Image Template', ondelete='cascade')
    post_template_id = fields.Many2one(
        'social_marketing.post.template', string='Post Template',
        ondelete='cascade')

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------

    @api.constrains('name')
    def _check_name_format(self):
        for binding in self:
            if not NAME_RE.match(binding.name or ''):
                raise ValidationError(_(
                    "Binding token %s is not a valid name. Use a letter "
                    "followed by letters, digits or underscores.",
                    binding.name))

    @api.constrains('template_id', 'post_template_id')
    def _check_single_owner(self):
        for binding in self:
            owners = bool(binding.template_id) + bool(binding.post_template_id)
            if owners != 1:
                raise ValidationError(_(
                    "A data binding must belong to exactly one template, "
                    "either an image template or a post template."))

    @api.constrains('model_id', 'field_id')
    def _check_field_belongs_to_model(self):
        for binding in self:
            if binding.field_id.model_id != binding.model_id:
                raise ValidationError(_(
                    "Field %(field)s does not belong to model %(model)s.",
                    field=binding.field_id.name,
                    model=binding.model_id.model))

    @api.constrains('name', 'template_id', 'post_template_id')
    def _check_name_unique_per_template(self):
        for binding in self:
            domain = [
                ('id', '!=', binding.id),
                ('name', '=', binding.name),
                ('template_id', '=', binding.template_id.id),
                ('post_template_id', '=', binding.post_template_id.id),
            ]
            if self.search_count(domain):
                raise ValidationError(_(
                    "Token %s is already bound on this template.",
                    binding.name))

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def _matches(self, record):
        """True when `record` is a single record of this binding's model."""
        self.ensure_one()
        if not record or len(record) != 1:
            return False
        return record._name == self.model_id.model

    def _read_raw_value(self, record):
        """Return the raw ORM value, or ``None`` when it cannot be read.

        The read is a plain ``record[field_name]`` subscript. There is no
        ``eval``, no ``safe_eval`` and no ``getattr`` on a dotted path
        anywhere in this call chain, by design.
        """
        self.ensure_one()
        field_name = self.field_id.name
        if not field_name or field_name not in record._fields:
            return None
        try:
            return record[field_name]
        except (AccessError, MissingError, KeyError, ValueError):
            _logger.warning(
                'data binding %s could not read %s.%s',
                self.name, record._name, field_name)
            return None

    def _resolve_value(self, record):
        """Return the human readable string this binding resolves to.

        A mismatched record, an unreadable field or a falsy value all give
        an empty string: nothing is inserted, there is no placeholder text
        and no fallback. Binary fields are handled by
        :meth:`_resolve_image_source` instead of being stringified.
        """
        self.ensure_one()
        if not self._matches(record):
            return ''
        value = self._read_raw_value(record)
        if not value:
            return ''
        field = record._fields[self.field_id.name]
        if field.type == 'binary':
            return ''
        if field.type == 'many2one':
            return value.display_name or ''
        if field.type in ('one2many', 'many2many'):
            return ', '.join(v.display_name or '' for v in value)
        if field.type in ('float', 'monetary'):
            return self._format_number(record, field, value)
        if field.type == 'date':
            return format_date(record.env, value)
        if field.type == 'datetime':
            return format_datetime(record.env, value)
        if field.type == 'selection':
            labels = dict(field._description_selection(record.env))
            return str(labels.get(value, value))
        if field.type == 'boolean':
            return _("Yes") if value else ''
        return str(value)

    def _format_number(self, record, field, value):
        """Format a float or monetary value for humans.

        A price renders as ``199.00`` (or the user's locale equivalent),
        never as the bare Python float ``199.0``.
        """
        digits = None
        get_digits = getattr(field, 'get_digits', None)
        precision = get_digits(record.env) if get_digits else field.digits
        if isinstance(precision, (list, tuple)) and len(precision) == 2:
            digits = precision[1]
        elif isinstance(precision, int):
            digits = precision
        currency = None
        if field.type == 'monetary':
            currency_field = getattr(field, 'currency_field', None) or 'currency_id'
            if currency_field in record._fields:
                currency = record[currency_field] or None
        return formatLang(
            record.env, value, digits=digits, currency_obj=currency or False)

    def _resolve_image_source(self, record):
        """Return a ``/web/image/...`` source for a binary image binding.

        Empty when the binding is not a binary field, the record does not
        match, or the field holds nothing. The path shape is the one
        ``render_core.mjs`` already absolutizes for image layers.
        """
        self.ensure_one()
        if not self._matches(record):
            return ''
        field = record._fields.get(self.field_id.name)
        if not field or field.type != 'binary':
            return ''
        if not self._read_raw_value(record):
            return ''
        return web_image_source(record._name, record.id, self.field_id.name)

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    def get_values(self, record):
        """Return ``{token: string}`` for this recordset against `record`.

        Binary bindings contribute their ``/web/image/...`` source, every
        other binding its formatted value. This dict is what gets handed to
        the render service as ``bindings``.
        """
        values = {}
        for binding in self:
            field = record._fields.get(binding.field_id.name) if binding._matches(record) else None
            if field is not None and field.type == 'binary':
                values[binding.name] = binding._resolve_image_source(record)
            else:
                values[binding.name] = binding._resolve_value(record)
        return values

    def render_text(self, text, record):
        """Substitute every token in `text` using this recordset.

        Unknown tokens render as an empty string and are logged by name.
        The raw token is never left visible, and it is never evaluated.
        """
        values = self.get_values(record)
        known = set(values)
        for token in collect_tokens(text):
            if token not in known:
                _logger.warning(
                    'unknown data binding token %r, rendered as empty string',
                    token)
        return substitute_tokens(text, values)


class SocialImageTemplateBindings(models.Model):
    """Bindings on an image template, plus the record driven render path."""

    _inherit = 'social.image.template'

    binding_ids = fields.One2many(
        'social.data.binding', 'template_id', string='Data Bindings')

    def get_binding_values(self, record):
        """Return the ``bindings`` dict for `record` from this template."""
        self.ensure_one()
        return self.binding_ids.get_values(record)

    def render_bound_text(self, text, record):
        """Substitute `text` using this template's registered bindings."""
        self.ensure_one()
        return self.binding_ids.render_text(text, record)

    def render_template_for_record(self, record, format='png'):
        """Render this template with values pulled off `record`.

        Saves the caller from hand assembling the bindings dict: pass a
        ``product.template`` (or anything else the bindings point at) and
        the registered bindings supply the values.
        """
        self.ensure_one()
        return self.render_template(
            bindings=self.get_binding_values(record), format=format)


class SocialPostTemplateBindings(models.Model):
    """Bindings on a post template."""

    _inherit = 'social_marketing.post.template'

    binding_ids = fields.One2many(
        'social.data.binding', 'post_template_id', string='Data Bindings')

    def get_binding_values(self, record):
        """Return ``{token: string}`` for `record` from this template."""
        self.ensure_one()
        return self.binding_ids.get_values(record)

    def render_bound_text(self, text, record):
        """Substitute `text` using this template's registered bindings."""
        self.ensure_one()
        return self.binding_ids.render_text(text, record)

    def render_bound_message(self, record):
        """Return this template's message with its tokens substituted."""
        self.ensure_one()
        return self.render_bound_text(self.message or '', record)
