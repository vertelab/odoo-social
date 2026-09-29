# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3
{
    'name': 'Social: Marketing Blog',
    'summary': 'Publish social marketing posts to an Odoo website blog.',
    'description': '''
Social Marketing Blog
=====================

    Publish social marketing posts to an Odoo website blog as a first-class
    channel, on equal terms with the social networks. A blog post travels the
    same pipeline as a LinkedIn post: choose the blog channel, approve the
    post, and the article appears in the chosen blog.

    The blog channel
    ----------------

    A blog channel is an ordinary ``social_marketing.account`` whose medium is
    the blog medium (``media_type = 'blog'``). It carries two extra fields,
    both required for blog channels and rejected on every other kind:

        - ``blog_id``: the website blog the channel publishes to.
        - ``author_id``: the author the articles are published under,
          defaulting to the current user's partner.

    The channel is what selects the blog, not the brand. One brand may hold
    several blog channels, and a shared (brand-less) channel is available to
    every brand, exactly as for the network channels.

    The article
    -----------

    The article is taken from the post itself:

        - ``name`` is the post title. ``title`` is a field on
          ``social_marketing.post.template``, inherited by
          ``social_marketing.post``, and is required only when the post
          targets a blog channel. A post that publishes to networks alone is
          accepted without a title, as before.
        - ``content`` is the post message.
        - ``blog_id`` and ``author_id`` come from the channel.

    Publication and scheduling
    --------------------------

    The article is created unpublished and published in the same transaction,
    carrying the post's scheduled moment as its ``published_date``.
    The website gates visibility on ``website_published AND post_date <=
    now()``, so a post scheduled for the future becomes readable at that
    moment and not before. Publishing through the second step rather than in
    the create values is deliberate: it announces the article to the blog's
    followers once, at the moment it is sent, instead of announcing it for the
    whole delay.

    Failures are permanent and visible: a blog channel that is missing its
    blog or its author blocks the live post with a reason through the core
    ``_block_publishing`` rather than hanging or retrying forever.

    Re-publishing is safe. The article is matched to its live post through
    ``blog.post.social_live_post_id``, which is unique, so a retried or
    double-triggered dispatch reports the existing article instead of adding a
    second one.

    Extends Odoo
    ------------

        - ``social_marketing.media``: adds the blog media type.
        - ``social_marketing.account``: adds ``blog_id`` and ``author_id``.
        - ``social_marketing.post.template``: adds ``title``.
        - ``social_marketing.live.post``: publishes to the blog.
        - ``blog.post``: adds the ``social_live_post_id`` marker.
    ''',
    'category': 'Marketing/Social Marketing',
    'version': '18.0.1.0.0',
    'depends': ['social_marketing', 'website_blog'],
    'data': [
        'data/social_media_data.xml',
        'views/social_marketing_account_views.xml',
        'views/social_marketing_post_views.xml',
    ],
    'auto_install': True,
    'license': 'AGPL-3',
}
