# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SocialImageBulkWizard(models.TransientModel):
    """Create one draft ``social_marketing.post`` per selected record,
    each with the template image rendered from that record's data.

    Opened from the "Create Posts from Image Template" server action,
    which is bound to every model and passes ``active_model`` /
    ``active_ids`` through the context. The wizard refuses a template
    whose binding model does not match the source model before creating
    anything. Each record is processed inside its own savepoint, so one
    failing record never rolls back the posts already created; failures
    are collected and reported at the end (see design decision D7).
    """

    _name = 'social.image.bulk.wizard'
    _description = 'Create Posts from Image Template'

    template_id = fields.Many2one(
        'social.image.template', string='Template', required=True,
        domain="[('model_id', '!=', False)]",
        help="Template bound to the model of the selected records.")
    variant_index = fields.Integer(
        'Variant Index', default=0,
        help="Variant of the template to render; 0 is the primary variant.")
    state = fields.Selection([
        ('setup', 'Setup'),
        ('done', 'Done'),
    ], string='Status', default='setup', readonly=True)
    source_model_name = fields.Char(
        'Source Model', compute='_compute_source_info', readonly=True)
    source_record_count = fields.Integer(
        'Selected Records', compute='_compute_source_info', readonly=True)
    created_post_ids = fields.Many2many(
        'social_marketing.post', string='Created Posts', readonly=True)
    created_count = fields.Integer('Created', readonly=True)
    failure_details = fields.Text(
        'Failures', readonly=True,
        help="Records whose post or render failed, with the reason.")

    @api.depends('template_id')
    def _compute_source_info(self):
        """Describe what the wizard was opened on (context, read once)."""
        for wizard in self:
            active_model = self.env.context.get('active_model')
            active_ids = self.env.context.get('active_ids') or []
            wizard.source_model_name = (
                self.env[active_model]._description
                if active_model and active_model in self.env else '')
            wizard.source_record_count = len(active_ids)

    def action_open(self):
        """Open the wizard form; called from the server action code."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create Posts from Image Template'),
            'res_model': self._name,
            'view_mode': 'form',
            'target': 'new',
            'context': dict(self.env.context),
        }

    def _get_source_records(self):
        """Return the records the action was invoked on. Raises before
        anything is created when the selection is missing."""
        active_model = self.env.context.get('active_model')
        active_ids = self.env.context.get('active_ids') or []
        if not active_model or active_model not in self.env:
            raise UserError(_(
                "The source model is missing. Open this action from a list "
                "view with selected records."))
        if not active_ids:
            raise UserError(_(
                "Select at least one record to create posts from."))
        return self.env[active_model].browse(active_ids)

    def _validate_template(self, records):
        """Refuse the combination before creating anything when the
        template's binding model does not match the source model."""
        template = self.template_id
        if not template.model_id:
            raise UserError(_(
                "Template %(template)s has no binding model. Bulk creation "
                "renders one image per record, so the template must be "
                "bound to the model of the selected records.",
                template=template.name))
        if template.model_id.model != records._name:
            raise UserError(_(
                "Template %(template)s is bound to model %(model)s, but "
                "the selected records are %(source)s. Nothing was created; "
                "pick a template bound to %(source)s or run the action on "
                "%(model)s records instead.",
                template=template.name,
                model=template.model_id.model,
                source=records._name))

    def action_create_posts(self):
        """Create one draft post per record, rendering each record's
        image inside a per-record savepoint. Partial failures are kept
        and reported; when every record fails nothing exists to keep,
        so the whole list is raised."""
        self.ensure_one()
        records = self._get_source_records()
        self._validate_template(records)
        template = self.template_id
        Post = self.env['social_marketing.post']
        created = self.env['social_marketing.post']
        failures = []
        for record in records:
            try:
                with self.env.cr.savepoint():
                    post = Post.create({
                        'message': record.display_name,
                        'image_template_id': template.id,
                        'image_template_record_model': record._name,
                        'image_template_record_id': record.id,
                        'image_variant_index': self.variant_index,
                    })
                    attachment = template.render_for_record(
                        record, format='png',
                        variant_index=self.variant_index)
                    post.write({'image_ids': [(4, attachment.id)]})
            except Exception as e:
                failures.append((record.display_name or str(record.id),
                                 str(e)))
                continue
            created |= post
        if not created:
            details = '\n'.join(
                '- %s: %s' % (name, error) for name, error in failures)
            raise UserError(_(
                "No posts could be created. Failures:\n%s") % details)
        self.write({
            'state': 'done',
            'created_post_ids': [(6, 0, created.ids)],
            'created_count': len(created),
            'failure_details': '\n'.join(
                '- %s: %s' % (name, error)
                for name, error in failures) or False,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create Posts from Image Template'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_view_posts(self):
        """Open the created posts in a list, for the success report."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Created Posts'),
            'res_model': 'social_marketing.post',
            'domain': [('id', 'in', self.created_post_ids.ids)],
            'view_mode': 'list,form',
            'target': 'current',
        }
