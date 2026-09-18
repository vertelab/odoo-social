# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SocialImageRenderWizard(models.TransientModel):
    """Fill-in dialog for rendering a `social.image.template` server-side.

    Choosing a template loads its placeholders as editable lines; on
    "Render" the wizard calls the render service and stores the resulting
    image as an ``ir.attachment`` (linked to the template, and — when
    opened from a social post — added to that post's image_ids).
    """

    _name = 'social.image.render.wizard'
    _description = 'Render Image Template'

    template_id = fields.Many2one(
        'social.image.template', string='Template', required=True)
    line_ids = fields.One2many(
        'social.image.render.wizard.line', 'wizard_id',
        string='Placeholders')
    format = fields.Selection([
        ('png', 'PNG'),
        ('svg', 'SVG'),
    ], string='Format', default='png', required=True)

    @api.onchange('template_id')
    def _onchange_template_id(self):
        """Rebuild placeholder lines from the selected template."""
        lines = [(5, 0, 0)]
        if self.template_id:
            for ph in self.template_id.placeholder_ids:
                lines.append((0, 0, {
                    'name': ph.name,
                    'label': ph.label or ph.name,
                    'value': False,
                }))
        self.line_ids = lines

    def action_render(self):
        self.ensure_one()
        bindings = {line.name: line.value or '' for line in self.line_ids}
        attachment = self.template_id.render_template(bindings, format=self.format)
        post_id = self.env.context.get('active_id')
        post_model = self.env.context.get('active_model')
        if post_model == 'social_marketing.post' and post_id:
            post = self.env[post_model].browse(post_id)
            post.write({'image_ids': [(4, attachment.id)]})
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Image created'),
                    'message': _('The rendered image was added to the post.'),
                    'type': 'success',
                },
            }
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'ir.attachment',
            'res_id': attachment.id,
            'view_mode': 'form',
            'target': 'current',
        }


class SocialImageRenderWizardLine(models.TransientModel):
    _name = 'social.image.render.wizard.line'
    _description = 'Render Wizard Placeholder Line'

    wizard_id = fields.Many2one(
        'social.image.render.wizard', ondelete='cascade')
    name = fields.Char('Name', required=True)
    label = fields.Char('Label')
    value = fields.Char('Value')
