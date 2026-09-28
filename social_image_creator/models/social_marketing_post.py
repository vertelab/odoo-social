# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SocialMarketingPost(models.Model):
    """Extend social posts with template image rendering at publish time.

    When the render wizard stores a pending render on a post
    (``image_render_pending``), the template image is rendered inside
    ``_action_post()`` before any live post is created. ``_action_post``
    is the single choke point of the publish pipeline: it is reached both
    from the "Post now" button (``action_post``) and from the scheduled
    publishing cron (``_cron_publish_scheduled``), so one hook covers
    both flows.

    A failed render blocks that post: the error message is stored on
    ``image_render_error`` and the post is removed from the publish batch,
    so no live post is created for it. Rendered PNGs attach to the post
    (``image_ids``) before publishing, whatever the render timing.
    """

    _inherit = 'social_marketing.post'

    image_template_id = fields.Many2one(
        'social.image.template', string='Image Template',
        help="Template rendered for this post's image.")
    image_template_record_model = fields.Char('Image Record Model')
    image_template_record_id = fields.Integer('Image Record ID')
    image_variant_index = fields.Integer(
        'Image Variant Index', default=0,
        help="Variant of the template to render; 0 is the primary variant.")
    image_render_pending = fields.Boolean(
        'Image Render Pending',
        help="Render the template image when the post is published. "
             "Cleared once the image has been rendered.")
    image_render_error = fields.Char(
        'Image Render Error', readonly=True,
        help="Last render failure. Publishing is blocked while a render "
             "is pending and failing.")

    def _action_post(self):
        publishable = self
        for post in self.filtered('image_render_pending'):
            try:
                post._render_pending_image()
            except UserError as e:
                _logger.warning(
                    'Template image render failed for post %s: %s',
                    post.id, e)
                post.write({'image_render_error': str(e)})
                publishable -= post
        return super(SocialMarketingPost, publishable)._action_post()

    def _render_pending_image(self):
        """Render the configured template for the configured record and
        attach the PNG to the post. Raises UserError on every failure so
        the caller can block publishing."""
        self.ensure_one()
        template = self.image_template_id
        if not template:
            raise UserError(_("No image template configured on the post."))
        if not self.image_template_record_model or not self.image_template_record_id:
            raise UserError(_(
                "No record chosen for the image template on post %s.") %
                self.display_name)
        record = self.env[self.image_template_record_model].browse(
            self.image_template_record_id).exists()
        if not record:
            raise UserError(_(
                "Record %(model)s,%(id)s for the image template no longer "
                "exists.") % {
                'model': self.image_template_record_model,
                'id': self.image_template_record_id,
            })
        attachment = template.render_for_record(
            record, variant_index=self.image_variant_index)
        self.write({
            'image_ids': [(4, attachment.id)],
            'image_render_pending': False,
            'image_render_error': False,
        })
