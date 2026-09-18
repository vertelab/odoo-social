# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SocialAgencyDocument(models.Model):
    """Underlag — a customer deliverable scoped to a brand.

    The agency stores strategy documents, briefs, brand guidelines and reports
    as underlag. Documents carry a type, attachments and a reviewable status;
    chatter provides the dialog between agency and customer.
    """

    _name = 'social.agency.document'
    _description = 'Underlag Document'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'social.brand.focus.mixin']
    _order = 'create_date desc'

    name = fields.Char('Title', required=True)
    type_id = fields.Many2one(
        'social.agency.document.type', string='Type', required=True)
    brand_id = fields.Many2one(
        'social.brand', string='Brand', required=True,
        default=lambda self: self._get_default_brand())
    partner_id = fields.Many2one(
        related='brand_id.partner_id', string='Customer', store=True,
        help="Invoiced customer of the brand.")
    description = fields.Text('Description')
    status = fields.Selection([
        ('draft', 'Draft'),
        ('in_review', 'In Review'),
        ('approved', 'Approved'),
        ('archived', 'Archived'),
    ], string='Status', default='draft', required=True, tracking=True)
    attachment_ids = fields.Many2many('ir.attachment', string='Attachments')
    attachment_count = fields.Integer(
        'Attachments', compute='_compute_attachment_count')

    _sql_constraints = [
        ('name_brand_uniq', 'UNIQUE(name, brand_id)',
         'An underlag with this title already exists for this brand.'),
    ]

    @api.depends('attachment_ids')
    def _compute_attachment_count(self):
        for doc in self:
            doc.attachment_count = len(doc.attachment_ids)

    @api.constrains('brand_id')
    def _check_brand(self):
        for doc in self:
            if not doc.brand_id:
                raise UserError(_('An underlag must belong to a brand.'))

    def action_draft(self):
        self.write({'status': 'draft'})

    def action_in_review(self):
        self.write({'status': 'in_review'})

    def action_approve(self):
        self.write({'status': 'approved'})

    def action_archive(self):
        self.write({'status': 'archived'})
