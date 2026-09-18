# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

import base64
import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SocialImageTemplate(models.Model):
    """A Fabric.js image template — a reusable scene for creating social
    and Open Graph images inside Odoo.

    `scene_json` stores the output of Fabric's ``canvas.toJSON()`` plus
    custom metadata (placeholder bindings on text/image objects, etc.).
    `svg_master` holds the last exported SVG representation of the scene,
    and `png_master` the last server-side rendered PNG (generated on
    demand through the render service).
    """

    _name = 'social.image.template'
    _description = 'Social Image Template'
    _order = 'name asc'

    name = fields.Char('Name', required=True)
    width = fields.Integer('Width (px)', default=1200, required=True)
    height = fields.Integer('Height (px)', default=630, required=True)
    platform = fields.Selection([
        ('og', 'Open Graph (1200×630)'),
        ('linkedin_post', 'LinkedIn Post (1200×627)'),
        ('instagram_square', 'Instagram Square (1080×1080)'),
        ('instagram_story', 'Instagram Story (1080×1920)'),
        ('custom', 'Custom'),
    ], string='Platform', default='og', required=True)
    scene_json = fields.Text('Scene (Fabric JSON)', default='{}')
    svg_master = fields.Binary('SVG Master', attachment=True)
    png_master = fields.Binary('PNG Master', attachment=True)
    placeholder_ids = fields.One2many(
        'social.image.template.placeholder', 'template_id', string='Placeholders')
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company)

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
        if format not in ('png', 'svg'):
            raise UserError(_("Unsupported render format: %s") % format)
        url, token = self._get_render_service_config()
        if not url:
            raise UserError(_(
                "Render service is not configured. Set the render service URL "
                "in Settings (Social Marketing)."))
        try:
            scene = json.loads(self.scene_json or '{}')
        except ValueError:
            raise UserError(_("Template scene is not valid JSON."))
        payload = json.dumps({
            'scene_json': scene,
            'width': self.width or 1200,
            'height': self.height or 630,
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
