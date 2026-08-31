# -*- coding: utf-8 -*-
# Vertel AB AGPL-3

from odoo import _, fields, models


class SocialMarketingPlatform(models.Model):
    """A social marketing platform (LinkedIn, Facebook, Instagram, Twitter,
    YouTube, Blog, ...). Templates target one or more platforms via
    ``platform_ids`` (many2many_tags); platform-specific settings live in the
    respective bridge modules (social_marketing_linkedin, ...)."""

    _name = 'social_marketing.platform'
    _description = 'Social Marketing Platform'
    _order = 'sequence, name'

    name = fields.Char('Name', required=True, translate=True)
    code = fields.Char(
        'Code', required=True,
        help="Technical code, e.g. 'linkedin', 'facebook', 'blog'.")
    sequence = fields.Integer('Sequence', default=10)
    active = fields.Boolean('Active', default=True)
    color = fields.Integer('Color')
    icon = fields.Char('Icon')

    # ------------------------------------------------------------------
    # Pre-flight publishing rules
    # ------------------------------------------------------------------
    # The limits live here as data rather than hardcoded in the validation
    # code, so a platform changing its rules is a data fix and not a patch.

    max_text_length = fields.Integer(
        'Max Text Length', default=0,
        help="Maximum number of characters allowed in the post message. "
             "0 means no limit.")
    max_image_count = fields.Integer(
        'Max Images', default=0,
        help="Maximum number of images allowed on a single post. "
             "0 means no limit.")
    allowed_media_types = fields.Char(
        'Allowed Media Types',
        help="Comma separated list of top-level media types accepted by this "
             "platform, e.g. 'image,video'. Empty means everything is allowed.")

    def _get_allowed_media_types(self):
        """Return the allowed media types as a set of lowercase strings."""
        self.ensure_one()
        raw = self.allowed_media_types or ''
        return {part.strip().lower() for part in raw.split(',') if part.strip()}

    def _validate_post(self, post):
        """Return the list of rule violations of ``post`` for this platform.

        Each violation is a ready-to-show string naming the platform and the
        rule that was broken. An empty list means the post is publishable.
        """
        self.ensure_one()
        violations = []

        if self.max_text_length:
            length = post.message_length
            if length > self.max_text_length:
                violations.append(_(
                    "%(platform)s: the message is %(length)s characters, "
                    "the maximum is %(maximum)s.",
                    platform=self.name, length=length,
                    maximum=self.max_text_length))

        images = post.image_ids
        if self.max_image_count and len(images) > self.max_image_count:
            violations.append(_(
                "%(platform)s: the post has %(count)s images, "
                "the maximum is %(maximum)s.",
                platform=self.name, count=len(images),
                maximum=self.max_image_count))

        allowed = self._get_allowed_media_types()
        if allowed:
            for attachment in images:
                media_type = (attachment.mimetype or '').split('/')[0].lower()
                if media_type and media_type not in allowed:
                    violations.append(_(
                        "%(platform)s: media type '%(media_type)s' "
                        "(%(filename)s) is not allowed, accepted types are "
                        "%(allowed)s.",
                        platform=self.name, media_type=media_type,
                        filename=attachment.name or attachment.id,
                        allowed=', '.join(sorted(allowed))))

        return violations
