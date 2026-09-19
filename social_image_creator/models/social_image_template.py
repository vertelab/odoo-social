# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

import base64
import copy
import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .social_image_binding import (
    BindingError,
    build_bindings,
    check_required_layers,
)

_logger = logging.getLogger(__name__)

# Field types a template token may bind against. Image fields are `binary`
# in Odoo, so they are covered by the `binary` entry.
BINDABLE_FIELD_TYPES = (
    'char', 'text', 'html', 'integer', 'float', 'monetary', 'boolean',
    'date', 'datetime', 'selection', 'binary',
)

MIN_VARIANT_SIZE = 50
MAX_VARIANT_SIZE = 8192


def validate_variants_data(variants):
    """Validate a variant list and return a normalized deep copy.

    Normalization rules (documented here because they are deliberate):
    - The list must be non-empty; deleting the last variant is refused.
    - Each variant needs a non-empty ``name`` and integer ``width``/``height``
      within 50..8192.
    - Exactly one variant must be primary. If none is flagged, the first
      variant becomes primary. If several are flagged, the FIRST primary
      wins: later ``is_primary`` flags are reset instead of raising, so a
      batch edit can never wedge a record into an invalid state.
    """
    if not isinstance(variants, list) or not variants:
        raise ValueError("A template must have at least one variant.")
    normalized = []
    seen_primary = False
    for item in variants:
        if not isinstance(item, dict):
            raise ValueError("Each variant must be a mapping.")
        variant = dict(item)
        name = variant.get('name')
        if not name or not isinstance(name, str):
            raise ValueError("Each variant must have a name.")
        for key in ('width', 'height'):
            value = variant.get(key)
            if (not isinstance(value, int) or isinstance(value, bool)
                    or not MIN_VARIANT_SIZE <= value <= MAX_VARIANT_SIZE):
                raise ValueError(
                    "Variant %r: %s must be an integer between %d and %d."
                    % (name, key, MIN_VARIANT_SIZE, MAX_VARIANT_SIZE))
        scene_json = variant.get('scene_json') or '{}'
        if not isinstance(scene_json, str):
            raise ValueError("Variant %r: scene_json must be a string." % name)
        variant['scene_json'] = scene_json
        is_primary = bool(variant.get('is_primary'))
        if is_primary and seen_primary:
            is_primary = False
        seen_primary = seen_primary or is_primary
        variant['is_primary'] = is_primary
        normalized.append(variant)
    if not seen_primary:
        normalized[0]['is_primary'] = True
    return normalized


def scale_scene(scene, sx, sy):
    """Return a deep copy of a Fabric canvas dict with geometry scaled.

    x-position and x-size values (``left``, ``width``, ``scaleX``) are
    multiplied by ``sx``; y-position and y-size values (``top``, ``height``,
    ``scaleY``) by ``sy``; ``fontSize`` by ``min(sx, sy)``. Objects nested
    inside ``group`` objects (their ``objects`` list) are scaled the same
    way. The canvas background itself (``background``) is not touched; only
    the ``objects`` list is walked.
    """
    data = copy.deepcopy(scene)

    def _scale_obj(obj):
        for attr, ratio in (('left', sx), ('width', sx),
                            ('top', sy), ('height', sy),
                            ('scaleX', sx), ('scaleY', sy)):
            value = obj.get(attr)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                obj[attr] = round(value * ratio, 4)
        font_size = obj.get('fontSize')
        if isinstance(font_size, (int, float)) and not isinstance(font_size, bool):
            obj['fontSize'] = round(font_size * min(sx, sy), 2)
        textbox = obj.get('textbox')
        if isinstance(textbox, dict):
            box_width = textbox.get('width')
            if isinstance(box_width, (int, float)) and not isinstance(box_width, bool):
                textbox['width'] = round(box_width * sx, 4)
        for child in obj.get('objects') or []:
            if isinstance(child, dict):
                _scale_obj(child)

    for obj in data.get('objects') or []:
        if isinstance(obj, dict):
            _scale_obj(obj)
    return data


class SocialImageTemplate(models.Model):
    """A Fabric.js image template: a reusable scene for creating social
    and Open Graph images inside Odoo.

    A template holds one or more named size ``variants`` (design decision
    D3), each with its own canvas size and scene JSON; exactly one variant
    is primary. The flat ``width``, ``height`` and ``scene_json`` fields are
    stored legacy mirrors of the primary variant, kept in sync in both
    directions by ``create``/``write`` so old code paths keep working.
    ``model_id`` declares the model that template tokens resolve against.
    """

    _name = 'social.image.template'
    _description = 'Social Image Template'
    _order = 'name asc'

    name = fields.Char('Name', required=True)
    width = fields.Integer('Width (px)', default=1200, required=True)
    height = fields.Integer('Height (px)', default=630, required=True)
    scene_json = fields.Text('Scene (Fabric JSON)', default='{}')
    variants = fields.Json(
        'Variants',
        default=lambda: [{
            'name': 'Primary', 'width': 1200, 'height': 630,
            'scene_json': '{}', 'is_primary': True,
        }],
        help="List of size variants: {name, width, height, scene_json, "
             "is_primary}. Exactly one variant is primary; the primary "
             "mirrors into the width/height/scene_json fields.")
    variants_summary = fields.Char(
        'Variants Summary', compute='_compute_variants_summary')
    model_id = fields.Many2one(
        'ir.model', string='Binding Model',
        domain="[('transient', '=', False)]",
        help="Model that template tokens resolve against")
    svg_master = fields.Binary('SVG Master', attachment=True)
    png_master = fields.Binary('PNG Master', attachment=True)
    placeholder_ids = fields.One2many(
        'social.image.template.placeholder', 'template_id', string='Placeholders')
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company)

    # ------------------------------------------------------------------
    # Variants
    # ------------------------------------------------------------------

    @api.depends('variants')
    def _compute_variants_summary(self):
        for template in self:
            variants = template.variants or []
            if not variants:
                template.variants_summary = ''
                continue
            parts = []
            for variant in variants:
                label = '%s (%s x %s)' % (
                    variant.get('name') or '?', variant.get('width') or '?',
                    variant.get('height') or '?')
                if variant.get('is_primary'):
                    label = '%s *' % label
                parts.append(label)
            template.variants_summary = ', '.join(parts)

    @api.constrains('variants')
    def _check_variants(self):
        """A template must always keep at least one variant; deleting the
        last remaining variant is rejected."""
        for template in self:
            try:
                validate_variants_data(template.variants or [])
            except ValueError as e:
                raise UserError(_(
                    "Invalid variants on template %s: %s") % (template.name, e))

    @staticmethod
    def _validated_variants(variants):
        """Validate ``variants`` and normalize it, raising UserError."""
        try:
            return validate_variants_data(variants)
        except ValueError as e:
            raise UserError(_("Invalid variants: %s") % e)

    @staticmethod
    def _scale_scene_json(scene_json, sx, sy):
        """Scale a scene JSON string by (sx, sy); returns a JSON string.
        Thin wrapper around the module-level :func:`scale_scene` so the math
        stays testable without an Odoo environment."""
        try:
            scene = json.loads(scene_json or '{}')
        except ValueError:
            scene = {}
        return json.dumps(scale_scene(scene, sx, sy))

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [dict(vals) for vals in vals_list]
        for vals in vals_list:
            variants = vals.pop('variants', None)
            if variants is None:
                variants = [{
                    'name': 'Primary',
                    'width': vals.get('width') or 1200,
                    'height': vals.get('height') or 630,
                    'scene_json': vals.get('scene_json') or '{}',
                    'is_primary': True,
                }]
            vals['variants'] = self._validated_variants(variants)
        records = super().create(vals_list)
        records._sync_legacy_from_variants()
        return records

    def write(self, vals):
        vals = dict(vals)
        variants = vals.pop('variants', None)
        if variants is not None:
            variants = self._validated_variants(variants)
        legacy = {}
        for key in ('width', 'height', 'scene_json'):
            if key in vals:
                legacy[key] = vals.pop(key)
        if legacy:
            # Legacy flat fields written directly (old code paths): push the
            # values into the primary variant so both stay in sync.
            merged = []
            for record_index, record in enumerate(self):
                base = ([dict(v) for v in variants]
                        if variants is not None
                        else [dict(v) for v in (record.variants or [])])
                if not base:
                    base = [{
                        'name': 'Primary', 'width': 1200, 'height': 630,
                        'scene_json': '{}', 'is_primary': True,
                    }]
                primary_index = next(
                    (i for i, v in enumerate(base) if v.get('is_primary')), 0)
                primary = dict(base[primary_index])
                primary.update({k: v for k, v in legacy.items() if v is not None})
                base[primary_index] = primary
                merged.append(base)
            if len(self) == 1:
                variants = merged[0]
            else:
                # Multi-record write with differing per-record legacy values
                # is not expressible through one variants value; sync each
                # record individually.
                result = True
                for record, record_variants in zip(self, merged):
                    result = bool(record.write(
                        dict(vals, variants=record_variants))) and result
                return result
        result = super().write(vals)
        if variants is not None:
            super(SocialImageTemplate, self).write({'variants': variants})
        self._sync_legacy_from_variants()
        return result

    def _sync_legacy_from_variants(self):
        """Mirror the primary variant into the legacy flat fields."""
        for template in self:
            primary = template.get_primary_variant()
            if not primary:
                continue
            super(SocialImageTemplate, template).write({
                'width': primary['width'],
                'height': primary['height'],
                'scene_json': primary.get('scene_json') or '{}',
            })

    def get_primary_variant(self):
        """Return the primary variant dict, or None."""
        self.ensure_one()
        for variant in self.variants or []:
            if variant.get('is_primary'):
                return variant
        return None

    def set_variants(self, variants):
        """Replace the variant list after schema validation.

        Refuses an empty list (a template must always keep at least one
        variant). Normalization rules are documented on
        :func:`validate_variants_data`.
        """
        self.ensure_one()
        self.write({'variants': variants})
        return self.variants

    def action_duplicate_variant(self, source, new_name, new_width, new_height):
        """Add a variant deep-copied from ``source`` (variant index or name),
        with the source scene geometry scaled to the new canvas size.

        x-position/x-size values are scaled by new_width/old_width and
        y-position/y-size values by new_height/old_height; font sizes by the
        smaller of the two ratios. Returns the created variant dict.
        """
        self.ensure_one()
        for key, value in (('new_width', new_width), ('new_height', new_height)):
            if (not isinstance(value, int) or isinstance(value, bool)
                    or not MIN_VARIANT_SIZE <= value <= MAX_VARIANT_SIZE):
                raise UserError(_(
                    "%s must be an integer between %d and %d.")
                    % (key, MIN_VARIANT_SIZE, MAX_VARIANT_SIZE))
        variants = [dict(v) for v in (self.variants or [])]
        if not variants:
            raise UserError(_("The template has no variant to duplicate."))
        if isinstance(source, int) and not isinstance(source, bool):
            if not 0 <= source < len(variants):
                raise UserError(_("Variant index %d is out of range.") % source)
            src = variants[source]
        else:
            matches = [v for v in variants if v.get('name') == source]
            if not matches:
                raise UserError(_("No variant named %r.") % source)
            src = matches[0]
        old_width, old_height = int(src['width']), int(src['height'])
        scene_json = self._scale_scene_json(
            src.get('scene_json') or '{}',
            new_width / old_width, new_height / old_height)
        variant = {
            'name': new_name,
            'width': new_width,
            'height': new_height,
            'scene_json': scene_json,
            'is_primary': False,
        }
        variants.append(variant)
        self.set_variants(variants)
        return variant

    # ------------------------------------------------------------------
    # Binding model fields (feeds the future field picker)
    # ------------------------------------------------------------------

    def get_binding_fields(self):
        """Return the bindable fields of the template's binding model as a
        list of ``{name, type, field_description}`` dicts, sorted by name.
        Fields starting with an underscore are excluded. Returns an empty
        list when no binding model is set."""
        self.ensure_one()
        if not self.model_id:
            return []
        model = self.env[self.model_id.model]
        result = []
        for name, field in sorted(model._fields.items()):
            if name.startswith('_') or field.type not in BINDABLE_FIELD_TYPES:
                continue
            result.append({
                'name': name,
                'type': field.type,
                'field_description': field.string or name,
            })
        return result

    # ------------------------------------------------------------------
    # Server-side rendering (render service)
    # ------------------------------------------------------------------

    def _get_render_service_config(self):
        """Return (url, token) for the Node render service from
        ir.config_parameter (set in Settings). Secrets come from pillar via
        the settings fields, never hardcoded."""
        icp = self.env['ir.config_parameter'].sudo()
        url = icp.get_param('social_marketing.render_service_url', '')
        token = icp.get_param('social_marketing.render_service_token', '')
        return (url or '').strip(), token or ''

    def render_template(self, bindings=None, format='png'):
        """Render this template server-side with placeholder `bindings`.

        Returns the resulting ``ir.attachment`` (PNG by default, SVG when
        ``format='svg'``). Placeholder values are supplied as
        ``{'name': value}`` and substituted by the render service; values
        are injected as text only (SVG output is XML-escaped server-side).
        """
        self.ensure_one()
        bindings = dict(bindings or {})
        try:
            scene = json.loads(self.scene_json or '{}')
        except ValueError:
            raise UserError(_("Template scene is not valid JSON."))
        return self._render_scene(
            scene, self.width or 1200, self.height or 630, bindings, format)

    def _variant_for_index(self, variant_index):
        """Return the variant dict at `variant_index`, or the primary
        variant when the index is out of range or variants are missing."""
        variants = self.variants or []
        if not variants:
            return {
                'name': 'Primary',
                'width': self.width or 1200,
                'height': self.height or 630,
                'scene_json': self.scene_json or '{}',
                'is_primary': True,
            }
        if (isinstance(variant_index, int) and not isinstance(variant_index, bool)
                and 0 <= variant_index < len(variants)):
            return variants[variant_index]
        for variant in variants:
            if variant.get('is_primary'):
                return variant
        return variants[0]

    def render_for_record(self, record, format='png', variant_index=0):
        """Render this template for a real record of the binding model.

        Walks the chosen variant's scene, resolves every referenced field
        (text tokens, `_hideIfEmpty`, `_required`, `_dataBinding`) against
        `record` with the dotted-path walker, then renders through the
        render service. Required layers with empty values and unresolvable
        paths raise UserError naming the layer / token. Returns the
        ``ir.attachment``.
        """
        self.ensure_one()
        if not self.model_id:
            raise UserError(_(
                "This template has no binding model. Use render_template() "
                "with explicit bindings instead."))
        if record._name != self.model_id.model:
            raise UserError(_(
                "Record model %s does not match the template binding model "
                "%s.") % (record._name, self.model_id.model))
        variant = self._variant_for_index(variant_index)
        try:
            scene = json.loads(variant.get('scene_json') or '{}')
        except ValueError:
            raise UserError(_("Template scene is not valid JSON."))
        try:
            bindings = build_bindings(record, scene)
            check_required_layers(scene, bindings)
        except BindingError as e:
            raise UserError(str(e))
        return self._render_scene(
            scene, variant['width'], variant['height'], bindings, format)

    def get_preview_bindings(self, record_id, scene_json=None):
        """Resolve the scene's binding fields against a record for the
        editor's live data preview. `scene_json` (a Fabric JSON string)
        may override the stored scene so the preview matches unsaved
        editor state. Returns ``{field_path: value}`` with binary fields
        as data URLs."""
        self.ensure_one()
        if not self.model_id:
            return {}
        record = self.env[self.model_id.model].browse(record_id).exists()
        if not record:
            raise UserError(_(
                "Record %(id)s not found for model %(model)s.") % {
                'id': record_id, 'model': self.model_id.model})
        if scene_json:
            try:
                scene = json.loads(scene_json)
            except ValueError:
                raise UserError(_("Preview scene is not valid JSON."))
        else:
            try:
                scene = json.loads(self.scene_json or '{}')
            except ValueError:
                scene = {}
        try:
            return build_bindings(record, scene)
        except BindingError as e:
            raise UserError(str(e))

    def _render_scene(self, scene, width, height, bindings, format):
        """POST one prepared scene to the render service and store the
        result as an ir.attachment. Shared by render_template() and
        render_for_record()."""
        self.ensure_one()
        if format not in ('png', 'svg'):
            raise UserError(_("Unsupported render format: %s") % format)
        url, token = self._get_render_service_config()
        if not url:
            raise UserError(_(
                "Render service is not configured. Set the render service URL "
                "in Settings (Social Marketing)."))
        payload = json.dumps({
            'scene_json': scene,
            'width': width,
            'height': height,
            'bindings': bindings,
            'format': format,
        }).encode('utf-8')
        req = Request(url.rstrip('/') + '/render', data=payload, method='POST')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Authorization', 'Bearer %s' % token)
        try:
            with urlopen(req, timeout=30) as resp:
                data = resp.read()
        except HTTPError as e:
            _logger.error('render service HTTP %s: %s', e.code, e.read()[:500])
            raise UserError(_(
                "Render service returned HTTP %s. Check the template scene "
                "and the service logs.") % e.code)
        except (URLError, OSError) as e:
            _logger.error('render service unreachable: %s', e)
            raise UserError(_(
                "Render service is unreachable (%s). Check the configured URL "
                "and that the service is running.") % e)
        mimetype = 'image/svg+xml' if format == 'svg' else 'image/png'
        return self.env['ir.attachment'].create({
            'name': '%s.%s' % (self.name, format),
            'datas': base64.b64encode(data),
            'mimetype': mimetype,
            'res_model': self._name,
            'res_id': self.id,
        })


class SocialImageTemplatePlaceholder(models.Model):
    """A named fill-in field of an image template. Values are supplied at
    render time and substituted into the scene's bound layers."""

    _name = 'social.image.template.placeholder'
    _description = 'Social Image Template Placeholder'
    _order = 'id asc'

    template_id = fields.Many2one(
        'social.image.template', string='Template',
        required=True, ondelete='cascade')
    name = fields.Char('Name', required=True)
    label = fields.Char('Label')
