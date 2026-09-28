# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SocialImageRenderWizard(models.TransientModel):
    """Fill-in dialog for rendering a `social.image.template` server-side.

    Choosing a template loads its placeholders as editable lines and
    exposes a record picker for the template's binding model. While the
    user picks template, record and variant the wizard keeps a live PNG
    preview (a temporary attachment named "(preview)"); on "Render" the
    final image is created and, when the wizard was opened from a social
    post, added to that post's image_ids.

    Render timing (per flow):

    - ``on_create`` (default): render immediately. When a record is
      chosen, bindings resolve against that record (``render_for_record``);
      otherwise the placeholder lines supply the values
      (``render_template``).
    - ``on_publish``: store the template, record and variant on the post
      as a pending render; the publish pipeline renders the image right
      before publishing and a failed render blocks that post.
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
    render_timing = fields.Selection([
        ('on_create', 'At post creation'),
        ('on_publish', 'At publish time'),
    ], string='Render Timing', default='on_create', required=True,
        help="At post creation renders now and attaches the image to the "
             "post. At publish time stores the template on the post and "
             "renders right before publishing; a failed render blocks the "
             "post.")
    record_model = fields.Char('Record Model')
    record_id = fields.Many2oneReference(
        'Record', model_field='record_model',
        help="Record the template tokens resolve against. Leave empty to "
             "fill in the placeholders manually below.")
    variant_index = fields.Integer(
        'Variant Index', default=0,
        help="Variant of the template to render; 0 is the primary variant.")
    has_binding_model = fields.Boolean(
        'Has Binding Model', compute='_compute_binding_state')
    binding_mismatch = fields.Boolean(
        'Binding Model Mismatch', compute='_compute_binding_state',
        help="The chosen record belongs to a different model than the "
             "template's binding model.")
    show_render_timing = fields.Boolean(
        'Show Render Timing', compute='_compute_show_render_timing')
    preview_attachment_id = fields.Many2one(
        'ir.attachment', string='Preview', readonly=True)
    preview_datas = fields.Binary(
        related='preview_attachment_id.datas', readonly=True)
    preview_error = fields.Char(
        'Preview Error', readonly=True,
        help="Why the live preview could not be rendered.")

    @api.depends('template_id', 'record_model', 'record_id')
    def _compute_binding_state(self):
        """Expose whether the template has a binding model and whether
        the chosen record belongs to it. The record picker (Many2one-
        Reference) already restricts its search to ``record_model``; the
        mismatch flag covers the case where the template was changed
        after the record was picked, or a record id was passed in from
        the outside."""
        for wizard in self:
            wizard.has_binding_model = bool(wizard.template_id.model_id)
            wizard.binding_mismatch = False
            if not (wizard.record_id and wizard.template_id.model_id):
                continue
            if not wizard.record_model or wizard.record_model not in self.env:
                wizard.binding_mismatch = True
                continue
            record = self.env[wizard.record_model].browse(
                wizard.record_id).exists()
            wizard.binding_mismatch = (
                not record
                or record._name != wizard.template_id.model_id.model)

    @api.depends('template_id')
    def _compute_show_render_timing(self):
        """"At publish time" only makes sense when the wizard was opened
        from a post; hide the choice otherwise."""
        for wizard in self:
            wizard.show_render_timing = bool(wizard._get_target_post())

    @api.onchange('template_id')
    def _onchange_template_id(self):
        """Rebuild placeholder lines from the selected template, reset
        the variant and point the record binding at the template's
        binding model. A record picked for the previous template
        is kept when it resolves in the new binding model; if it no
        longer resolves it is cleared here, and if it resolves to the
        wrong model the mismatch warning on the form tells the user to
        re-pick."""
        self.record_model = self.template_id.model_id.model or False
        self.variant_index = 0
        if self.record_id:
            record = None
            if self.record_model and self.record_model in self.env:
                record = self.env[self.record_model].browse(
                    self.record_id).exists()
            if not record:
                self.record_id = False
        lines = [(5, 0, 0)]
        if self.template_id:
            for ph in self.template_id.placeholder_ids:
                lines.append((0, 0, {
                    'name': ph.name,
                    'label': ph.label or ph.name,
                    'value': False,
                }))
        self.line_ids = lines
        self._refresh_preview()

    @api.onchange('record_id', 'variant_index')
    def _onchange_preview_trigger(self):
        self._refresh_preview()

    def _refresh_preview(self):
        """Render a live PNG preview of the current selection into a
        temporary "(preview)" attachment. Failures land in
        ``preview_error`` so a broken render service or a required
        layer without a value explains itself instead of erroring the
        dialog."""
        self.preview_attachment_id = False
        self.preview_error = False
        if not self.template_id:
            return
        if self.template_id.model_id and not self.record_id:
            # Nothing to resolve against yet; wait for the record.
            return
        try:
            attachment = self._render_attachment(format='png')
        except UserError as e:
            self.preview_error = str(e)
            return
        attachment.write({'name': '%s (preview).png' % self.template_id.name})
        self.preview_attachment_id = attachment.id

    def action_preview(self):
        """Manual preview refresh (the preview also updates on every
        relevant onchange)."""
        self.ensure_one()
        self._refresh_preview()
        return self._reload_action()

    def _reload_action(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Render Image Template'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _get_target_post(self):
        """Return the social post this wizard was opened from, or None."""
        post_id = self.env.context.get('active_id')
        post_model = self.env.context.get('active_model')
        if post_model == 'social_marketing.post' and post_id:
            return self.env[post_model].browse(post_id)
        return None

    def _get_bound_record(self):
        """Return the record chosen in the wizard, validated against the
        template's binding model. Raises UserError on any inconsistency."""
        self.ensure_one()
        if not self.record_id:
            return None
        if not self.record_model or self.record_model not in self.env:
            raise UserError(_(
                "Record model %s is not available.") % self.record_model)
        record = self.env[self.record_model].browse(self.record_id).exists()
        if not record:
            raise UserError(_(
                "Record %s,%s no longer exists.") %
                (self.record_model, self.record_id))
        if (self.template_id.model_id
                and record._name != self.template_id.model_id.model):
            raise UserError(_(
                "Record %(record)s belongs to model %(record_model)s, but "
                "template %(template)s is bound to model %(model)s. Pick a "
                "record of the right model.") % {
                'record': record.display_name,
                'record_model': record._name,
                'template': self.template_id.name,
                'model': self.template_id.model_id.model,
            })
        return record

    def _render_attachment(self, format=None):
        """Render the template for the current wizard state and return
        the attachment. With a bound record the values come from the
        record; without one the placeholder lines supply them."""
        self.ensure_one()
        record = self._get_bound_record()
        if record:
            return self.template_id.render_for_record(
                record, format=format or self.format,
                variant_index=self.variant_index)
        bindings = {line.name: line.value or '' for line in self.line_ids}
        return self.template_id.render_template(
            bindings, format=format or self.format)

    def action_render(self):
        self.ensure_one()
        if self.binding_mismatch:
            raise UserError(_(
                "The chosen record does not match the template's binding "
                "model. Pick a record of model %s or clear the record and "
                "fill in the placeholders manually.") %
                (self.template_id.model_id.model or '?'))
        post = self._get_target_post()
        if self.render_timing == 'on_publish':
            return self._action_schedule_on_publish(post)
        return self._action_render_now(post)

    def _action_schedule_on_publish(self, post):
        """Store a pending render on the post instead of rendering now."""
        if not post:
            raise UserError(_(
                "Render at publish time is only available when the wizard "
                "is opened from a social post."))
        if not self.record_id:
            raise UserError(_(
                "Choose a record to bind the template against; at publish "
                "time the values are read from the record, so the "
                "placeholders cannot be filled in manually."))
        post.write({
            'image_template_id': self.template_id.id,
            'image_template_record_model': self.record_model,
            'image_template_record_id': self.record_id,
            'image_variant_index': self.variant_index,
            'image_render_pending': True,
            'image_render_error': False,
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Image render scheduled'),
                'message': _(
                    'The template image renders when the post is '
                    'published; a failed render blocks the post.'),
                'type': 'success',
            },
        }

    def _action_render_now(self, post):
        """Render immediately and attach the image to the post when the
        wizard was opened from one."""
        attachment = self._render_attachment()
        if post:
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

    @api.onchange('value')
    def _onchange_value(self):
        """Placeholder edits feed the live preview."""
        if self.wizard_id:
            self.wizard_id._refresh_preview()
