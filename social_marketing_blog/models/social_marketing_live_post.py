# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

import logging

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class SocialLivePostBlog(models.Model):
    """Publishes a live post to an Odoo website blog as a blog article."""

    _inherit = 'social_marketing.live.post'

    def _post(self):
        """Claim the blog live posts and delegate the rest to the pipeline.

        Same split as the LinkedIn bridge: consume our own media type and
        hand the remainder to ``super()``, so a cross-post to a network and
        the blog produces two live posts that are each handled by the right
        bridge and the post completes only when both are terminal.
        """
        blog_live_posts = self._filter_by_media_types(['blog'])
        super(SocialLivePostBlog, (self - blog_live_posts))._post()
        blog_live_posts._post_blog()

    def _post_blog(self):
        """Create the website article for each blog live post.

        Idempotent through the ``social_live_post_id`` marker on
        ``blog.post``: the article is searched for before it is created, so
        a retried or double-triggered dispatch reports the existing article
        instead of publishing a second one.
        """
        for live_post in self:
            account = live_post.social_account_id

            if not account.blog_id or not account.author_id:
                # Permanent: retrying cannot fix a channel that was never
                # configured. Recorded so the failure is visible and the
                # post can complete rather than hang.
                live_post._block_publishing(_(
                    "Blog channel %(channel)s has no website blog or author "
                    "configured, so no article can be published.",
                    channel=account.display_name))
                continue

            blog_post = self.env['blog.post'].search(
                [('social_live_post_id', '=', live_post.id)], limit=1)

            if not blog_post:
                blog_post = self._create_blog_post(live_post, account)

            live_post.write({
                'platform_post_id': str(blog_post.id),
                'permalink': blog_post.website_url,
                'state': 'posted',
            })
            live_post.post_id._check_post_completion()

    def _create_blog_post(self, live_post, account):
        """Create the article that mirrors ``live_post``.

        The article is created unpublished and published immediately after,
        carrying the post's scheduled moment as its ``published_date``.

        The two-step create is deliberate. ``blog.post.create`` announces the
        article to the blog's followers as soon as ``is_published`` is set in
        the create values, and it does so without consulting
        ``published_date``: the announcement would go out for the whole delay
        before the article became readable. Publishing through ``write`` in
        the same transaction announces it once, at the moment it is actually
        sent, which is when the delay is over.

        ``website_blog`` gates visibility on ``website_published AND
        post_date <= now()`` (``post_date`` follows ``published_date``), so a
        future ``published_date`` keeps the article hidden until its moment
        arrives, with no further step needed.

        Note that ``website_published`` is the field to set, not
        ``is_published`` together with it: both are accepted by ``create``,
        but passing both is read as two publications and announces the
        article twice.
        """
        self.ensure_one()
        blog_post = self.env['blog.post'].create({
            'name': live_post.post_id.title,
            'content': live_post.message,
            'blog_id': account.blog_id.id,
            'author_id': account.author_id.id,
            'social_live_post_id': live_post.id,
            'website_published': False,
        })
        blog_post.write({
            'website_published': True,
            'published_date': live_post.post_id.scheduled_date or
                              fields.Datetime.now(),
        })
        return blog_post
