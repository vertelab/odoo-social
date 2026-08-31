# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from datetime import datetime, timedelta
import json

from odoo import api, models, fields
from odoo.tools.misc import format_date, _format_time_ago

from odoo.addons.social_marketing.models.social_marketing_stream_type import (
    SOCIAL_INTERACTION_TYPES,
)

# Retention period for private items (direct messages). Configurable through
# ir.config_parameter so it can be set per database without a code change.
DM_RETENTION_PARAM = 'social_marketing.dm_retention_days'
DM_RETENTION_DEFAULT_DAYS = 90


class SocialStreamPost(models.Model):
    """ A 'stream' post, as opposed to a regular social_marketing.post, references a post that
    actually exists on a social_marketing.media external database (a Facebook post, a Tweet, ...).

    Stream posts are created by fetching data from the related social media third party API.
    They should not be directly created/modified.

    social.stream.posts are used to fill the 'Feed' view that allows users to follow the social_marketing.media activity
    based on their interest (a Facebook Page, a Twitter hashtag, ...).
    They are directly created by their related social_marketing.stream. """

    _name = 'social_marketing.stream.post'
    _description = 'Social Stream Post'
    _order = 'published_date desc'

    message = fields.Text("Message")
    author_name = fields.Char('Author Name',
        help="The post author name based on third party information (ex: 'John Doe').")
    author_link = fields.Char('Author Link', compute='_compute_author_link',
        help="Author link to the external social_marketing.media (ex: link to the Twitter Account).")
    post_link = fields.Char('Post Link', compute='_compute_post_link',
        help="Post link to the external social_marketing.media (ex: link to the actual Facebook Post).")
    stream_id = fields.Many2one('social_marketing.stream', string="Social Stream", ondelete="cascade")
    media_type = fields.Selection(related='stream_id.media_id.media_type', string="Related Social Media")
    published_date = fields.Datetime('Published date', help="The post published date based on third party information.")
    formatted_published_date = fields.Char('Formatted Published Date', compute='_compute_formatted_published_date')
    social_account_id = fields.Many2one(related='stream_id.social_account_id', string='Related social Account', oldname='account_id')
    company_id = fields.Many2one('res.company', 'Company', related='social_account_id.company_id')
    is_author = fields.Boolean('Is Author', compute='_compute_is_author')

    stream_post_image_ids = fields.One2many('social_marketing.stream.post.image', 'stream_post_id', string="Stream Post Images",
        help="Images that were shared with this post.")
    # JSON array capturing the URLs of the images to make it easy to display them in the kanban view
    stream_post_image_urls = fields.Text("Stream Post Images URLs",
        compute='_compute_stream_post_image_urls')

    # Some social_marketing.medias (ex: Facebook) provide information on the link shared with the post.
    # We store those information to render a nice block on the kanban view with the title, image and description.
    link_title = fields.Text("Link Title")
    link_description = fields.Text("Link Description")
    link_image_url = fields.Char("Link Image URL")
    link_url = fields.Char("Link URL")

    # ------------------------------------------------------------------
    # Inbox
    #
    # A stream post is the incoming item: a comment, a like, a mention or a
    # direct message that arrived from the outside world. The fields below
    # turn the feed (something you look at) into a queue (something you work
    # through) without introducing a second model to hold the same data.
    # ------------------------------------------------------------------
    inbox_state = fields.Selection([
        ('new', 'New'),
        ('assigned', 'Assigned'),
        ('answered', 'Answered'),
        ('closed', 'Closed'),
        ('ignored', 'Ignored'),
    ], string="Inbox State", default='new', required=True, index=True,
        help="Where this item stands in the inbox workflow.")
    assigned_user_id = fields.Many2one(
        'res.users', string="Assigned To", index=True,
        help="The person who picked this item up.")
    answered_by_user_id = fields.Many2one(
        'res.users', string="Answered By", readonly=True,
        help="The person who marked this item answered.")
    answered_date = fields.Datetime(
        "Answered On", readonly=True,
        help="When this item was marked answered.")
    interaction_type = fields.Selection(
        SOCIAL_INTERACTION_TYPES, string="Interaction Type",
        compute='_compute_interaction_type', store=True, readonly=False,
        index=True,
        help="Derived from the stream type, which is what the platform "
             "fetcher used to pull this item. Unknown stream types give "
             "'other'; a fetcher that knows better may write it directly.")
    is_private = fields.Boolean(
        "Private", compute='_compute_is_private', store=True, readonly=False,
        index=True,
        help="True for direct messages. Private items are personal data and "
             "are removed by the retention cron once they pass the "
             "configured retention period.")

    @api.depends('stream_id.stream_type_id.interaction_type')
    def _compute_interaction_type(self):
        for post in self:
            post.interaction_type = (
                post.stream_id.stream_type_id.interaction_type or 'other')

    @api.depends('interaction_type')
    def _compute_is_private(self):
        for post in self:
            post.is_private = post.interaction_type == 'direct_message'

    # ------------------------------------------------------------------
    # Inbox actions
    # ------------------------------------------------------------------
    def action_inbox_assign(self, user_id=None):
        """Assign the items to a user, the current one when none is given."""
        self.write({
            'assigned_user_id': user_id or self.env.user.id,
            'inbox_state': 'assigned',
        })
        return True

    def action_inbox_answered(self):
        """Mark the items answered, recording who did it and when."""
        self.write({
            'inbox_state': 'answered',
            'answered_by_user_id': self.env.user.id,
            'answered_date': fields.Datetime.now(),
        })
        return True

    def action_inbox_close(self):
        """Mark the items handled and out of the queue."""
        self.write({'inbox_state': 'closed'})
        return True

    def action_inbox_ignore(self):
        """Take the items out of the queue without answering them."""
        self.write({'inbox_state': 'ignored'})
        return True

    def action_inbox_reopen(self):
        """Put the items back into the unhandled queue."""
        self.write({'inbox_state': 'new'})
        return True

    # ------------------------------------------------------------------
    # Retention of private items (GDPR)
    # ------------------------------------------------------------------
    @api.model
    def _get_dm_retention_days(self):
        """Retention period in days for private items.

        Zero or less disables the deletion entirely, which is what an
        unparseable value falls back to rather than guessing a period and
        deleting data on a typo.
        """
        # sudo() on this one call only: ir.config_parameter is not readable by
        # ordinary users and the value is a plain integer, not brand data.
        raw = self.env['ir.config_parameter'].sudo().get_param(
            DM_RETENTION_PARAM, DM_RETENTION_DEFAULT_DAYS)
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 0

    @api.model
    def _cron_delete_expired_private_posts(self):
        """Delete private items past the retention period.

        Only private items are touched: a public comment on a public post is
        not the same category of data as a direct message and is kept.

        Safe to run repeatedly. A second run simply finds nothing left to
        delete and returns 0.
        """
        days = self._get_dm_retention_days()
        if days <= 0:
            return 0
        cutoff = fields.Datetime.now() - timedelta(days=days)
        # Age is the published date when the platform gave us one, and the
        # creation date otherwise, so an item without a published date can
        # still expire instead of living forever.
        expired = self.search([
            ('is_private', '=', True),
            '|',
            '&', ('published_date', '!=', False),
            ('published_date', '<', cutoff),
            '&', ('published_date', '=', False),
            ('create_date', '<', cutoff),
        ])
        count = len(expired)
        if count:
            expired.unlink()
        return count

    def _compute_stream_post_image_urls(self):
        """ See field 'help' for more information. """
        for stream_post in self:
            stream_post.stream_post_image_urls = json.dumps([image.image_url for image in stream_post.stream_post_image_ids])

    def _compute_author_link(self):
        """ Every social module should override this method and handle its own
        records, then call super() on remaining subset. See field 'help' for
        more information. """
        for post in self:
            post.author_link = False

    def _compute_post_link(self):
        """ Every social module should override this method and handle its own
        records, then call super() on remaining subset. See field 'help' for
        more information. """
        for post in self:
            post.post_link = False

    @api.depends('published_date')
    def _compute_formatted_published_date(self):
        for post in self:
            post.formatted_published_date = self._format_published_date(post.published_date) if post.published_date else False

    def _compute_is_author(self):
        self.is_author = False

    def _filter_by_media_types(self, media_types):
        return self.filtered(lambda post: post.media_type in media_types)

    @api.model
    def _format_published_date(self, published_date):
        """ Formats to '5 minutes' instead of date if not older than 12 hours. """
        if (datetime.now() - published_date) < timedelta(hours=12):
            return _format_time_ago(self.env, (datetime.now() - published_date), add_direction=False)
        else:
            return format_date(self.env, published_date)

    def _fetch_matching_post(self):
        """ This method is meant to be overridden by underlying social implementations.
        It returns the social_marketing.post linked to this social.stream.post if any, by matching
        the social media specific ID of the social.stream.post to its social.live.post counterpart.

        This can't be easily built dinamically since all social media implementations have their own
        specific IDs, that we don't want to mix. """

        self.ensure_one()
        return self.env['social_marketing.post']
