# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import _, api, fields, models


class SocialPublishPipelineStep(models.Model):
    """ A step in the publishing pipeline of a social post.

    Every stage transition (submitted, compliance checked, approved,
    dispatched, per-channel published, failed, completed) is recorded
    here as a persistent, auditable row — the business audit trail of
    the publishing lifecycle. Execution itself is handled by queue_job
    (technical telemetry); this model is the business audit. """

    _name = 'social.publish.pipeline.step'
    _description = 'Social Publish Pipeline Step'
    _order = 'create_date, id'

    post_id = fields.Many2one(
        'social_marketing.post', string='Post', required=True,
        ondelete='cascade', index=True, auto_join=True)
    live_post_id = fields.Many2one(
        'social_marketing.live.post', string='Live Post', ondelete='set null')
    stage = fields.Selection([
        ('submitted', 'Submitted'),
        ('compliance_checked', 'Compliance Checked'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('awaiting_customer', 'Awaiting Customer'),
        ('dispatched', 'Dispatched'),
        ('published', 'Published'),
        ('failed', 'Failed'),
        ('completed', 'Completed'),
        ('needs_recheck', 'Needs Recheck'),
        ('retracted', 'Retracted'),
    ], string='Stage', required=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('done', 'Done'),
        ('failed', 'Failed'),
    ], string='State', default='done', required=True)
    result = fields.Text('Result')
    user_id = fields.Many2one(
        'res.users', string='Actor',
        default=lambda self: self.env.user, ondelete='set null')
    policy_version = fields.Integer(
        'Policy Version',
        help="Version of the communication policy at the time of this step.")

    @api.depends('stage', 'state', 'create_date')
    def _compute_display_name(self):
        stage_labels = dict(self._fields['stage']._description_selection(self.env))
        state_labels = dict(self._fields['state']._description_selection(self.env))
        for step in self:
            step.display_name = '%s / %s (%s)' % (
                stage_labels.get(step.stage, step.stage),
                state_labels.get(step.state, step.state),
                step.create_date,
            )
