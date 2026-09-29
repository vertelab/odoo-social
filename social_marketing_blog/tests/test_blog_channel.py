# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class BlogChannelCommon(TransactionCase):
    """ Shared fixtures for the blog channel tests.

    The blog media record is created by the module's data file, so it is
    looked up rather than created: creating a second one would not exercise
    the record the module actually ships.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].set_param(
            'social_publish_rate_limit_delay_seconds', '0.0')

        Media = cls.env['social_marketing.media']
        cls.blog_media = Media.search([('media_type', '=', 'blog')], limit=1)

        # A vendor-less medium, as in social_marketing's own tests: using a
        # real network medium would make account creation call the provider
        # API, which is neither wanted nor available here.
        cls.plain_media = Media.create({'name': 'Test Network Media'})

        cls.blog = cls.env['blog.blog'].create({'name': 'Test Blog'})
        cls.author = cls.env['res.partner'].create({'name': 'Test Author'})

        cls.blog_account = cls.env['social_marketing.account'].create({
            'name': 'Test Blog Channel',
            'media_id': cls.blog_media.id,
            'blog_id': cls.blog.id,
            'author_id': cls.author.id,
        })
        # A network account with no blog/author set: the blog-only constraint
        # must not touch it.
        cls.network_account = cls.env['social_marketing.account'].create({
            'name': 'Test Network Channel',
            'media_id': cls.plain_media.id,
        })

    def _create_post(self, accounts, message='Hello blog', title=None):
        values = {
            'message': message,
            'account_ids': [(6, 0, [a.id for a in accounts])],
        }
        if title is not None:
            values['title'] = title
        return self.env['social_marketing.post'].create(values)


class TestBlogMedia(BlogChannelCommon):
    """ The blog medium is a first-class media type. """

    def test_blog_media_type_is_available(self):
        self.assertTrue(
            self.blog_media, "the module must ship a blog medium record")
        self.assertEqual(self.blog_media.media_type, 'blog')
        self.assertIn(
            'blog',
            dict(self.env['social_marketing.media']._fields[
                'media_type'].selection),
            "the blog media type must extend the media selection")

    def test_blog_media_does_not_disturb_other_media(self):
        # The pre-existing vendor media types must be untouched by the bridge.
        linkedin_media = self.env['social_marketing.media'].search(
            [('media_type', '=', 'linkedin')], limit=1)
        self.assertEqual(linkedin_media.media_type, 'linkedin')
        self.assertNotEqual(linkedin_media, self.blog_media)


class TestBlogChannelFields(BlogChannelCommon):
    """ blog_id and author_id are required on blog channels, and only there. """

    def test_complete_blog_channel_is_accepted(self):
        account = self.env['social_marketing.account'].create({
            'name': 'Complete Blog Channel',
            'media_id': self.blog_media.id,
            'blog_id': self.blog.id,
            'author_id': self.author.id,
        })
        self.assertEqual(account.blog_id, self.blog)
        self.assertEqual(account.author_id, self.author)

    def test_blog_channel_without_blog_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.env['social_marketing.account'].create({
                'name': 'Blog Channel Without Blog',
                'media_id': self.blog_media.id,
                'author_id': self.author.id,
            })

    def test_blog_channel_without_author_is_rejected(self):
        # author_id has a default (the current user's partner), so it must be
        # cleared explicitly. Passing False is not enough on its own in every
        # path, so the value is cleared after the default is resolved.
        account = self.env['social_marketing.account'].new({
            'media_id': self.blog_media.id,
            'blog_id': self.blog.id,
        })
        account.author_id = False
        self.assertFalse(
            account.author_id, "the default must be clearable")
        with self.assertRaises(ValidationError):
            self.env['social_marketing.account'].create({
                'name': 'Blog Channel Without Author',
                'media_id': self.blog_media.id,
                'blog_id': self.blog.id,
                'author_id': False,
            })

    def test_non_blog_channel_needs_neither(self):
        # setUpClass already created it without either field; assert that it
        # still stands and that the constraint stays silent on a write too.
        self.assertFalse(self.network_account.blog_id)
        self.network_account.write({'name': 'Renamed Network Channel'})
        self.assertEqual(self.network_account.name, 'Renamed Network Channel')

    def test_author_defaults_to_current_user_partner(self):
        account = self.env['social_marketing.account'].create({
            'name': 'Default Author Channel',
            'media_id': self.blog_media.id,
            'blog_id': self.blog.id,
        })
        self.assertEqual(account.author_id, self.env.user.partner_id)


class TestPostTitle(BlogChannelCommon):
    """ The title is required for a blog post, optional for a network post. """

    def test_network_only_post_needs_no_title(self):
        post = self._create_post([self.network_account])
        self.assertFalse(post.title)

    def test_blog_post_requires_a_title(self):
        with self.assertRaises(ValidationError):
            self._create_post([self.blog_account])

    def test_blog_post_with_title_is_accepted(self):
        post = self._create_post([self.blog_account], title='My Article')
        self.assertEqual(post.title, 'My Article')

    def test_title_is_inherited_by_the_post_model(self):
        self.assertIn('title', self.env['social_marketing.post']._fields)

    def test_cross_post_to_network_and_blog_requires_a_title(self):
        # A single network account is fine and a single blog account is not;
        # together the blog requirement must win.
        with self.assertRaises(ValidationError):
            self._create_post([self.network_account, self.blog_account])


class TestBlogPublication(BlogChannelCommon):
    """ The article is created from the post and linked back to it. """

    def _publish(self, post):
        """ Drive the live post through the real dispatch entry point. """
        for live_post in post.live_post_ids:
            live_post._post()

    def test_publishing_creates_the_article(self):
        post = self._create_post(
            [self.blog_account], message='<p>Article body</p>',
            title='Published Article')
        post.action_post()
        self._publish(post)

        article = self.env['blog.post'].search(
            [('social_live_post_id', 'in', post.live_post_ids.ids)])
        self.assertEqual(len(article), 1)
        self.assertEqual(article.name, 'Published Article')
        self.assertEqual(article.blog_id, self.blog)
        self.assertEqual(article.author_id, self.author)
        self.assertEqual(article.content, 'Article body')

    def test_live_post_records_the_platform_identity(self):
        post = self._create_post(
            [self.blog_account], title='Identity Article')
        post.action_post()
        self._publish(post)

        article = self.env['blog.post'].search(
            [('social_live_post_id', 'in', post.live_post_ids.ids)], limit=1)
        live_post = post.live_post_ids
        self.assertEqual(live_post.platform_post_id, str(article.id))
        self.assertEqual(live_post.state, 'posted')

    def test_blogs_publish_as_published(self):
        post = self._create_post([self.blog_account], title='Visible Article')
        post.action_post()
        self._publish(post)
        article = self.env['blog.post'].search(
            [('social_live_post_id', 'in', post.live_post_ids.ids)], limit=1)
        self.assertTrue(article.website_published)


class TestBlogIdempotency(BlogChannelCommon):
    """ Re-dispatching must never publish a second article. """

    def test_second_dispatch_reuses_the_article(self):
        post = self._create_post([self.blog_account], title='Idempotent')
        post.action_post()
        for live_post in post.live_post_ids:
            live_post._post()

        articles = self.env['blog.post'].search(
            [('social_live_post_id', 'in', post.live_post_ids.ids)])
        self.assertEqual(len(articles), 1)

        # Re-dispatch the same live post: the marker turns the second run
        # into a lookup, not an insert.
        live_post = post.live_post_ids
        live_post.write({'state': 'posting'})
        live_post._post()

        articles = self.env['blog.post'].search(
            [('social_live_post_id', 'in', post.live_post_ids.ids)])
        self.assertEqual(len(articles), 1)

    def test_marker_is_unique(self):
        post = self._create_post([self.blog_account], title='Unique Marker')
        post.action_post()
        live_post = post.live_post_ids
        self.env['blog.post'].create({
            'name': 'First',
            'blog_id': self.blog.id,
            'social_live_post_id': live_post.id,
        })
        with self.assertRaises(IntegrityError):
            with self.env.cr.savepoint():
                self.env['blog.post'].create({
                    'name': 'Second',
                    'blog_id': self.blog.id,
                    'social_live_post_id': live_post.id,
                })


class TestBlogFailures(BlogChannelCommon):
    """ A channel that cannot publish blocks the live post with a reason. """

    def test_missing_blog_blocks_the_live_post(self):
        # Bypass the account constraint to build the state the bridge must
        # survive in production: a blog channel whose blog was never set.
        # The constraint is what stops that state through the UI, so it is
        # written away at SQL level rather than through the ORM.
        post = self._create_post([self.blog_account], title='Blocked')
        post.action_post()
        live_post = post.live_post_ids
        self.env.cr.execute(
            "UPDATE social_marketing_account SET blog_id = NULL "
            "WHERE id = %s", (self.blog_account.id,))
        self.blog_account.invalidate_recordset(['blog_id'])
        self.assertFalse(self.blog_account.blog_id)

        live_post._post()

        article = self.env['blog.post'].search(
            [('social_live_post_id', '=', live_post.id)])
        self.assertFalse(article, "no article may be created")
        self.assertEqual(live_post.state, 'failed')
        self.assertTrue(
            post.pipeline_step_ids.filtered(
                lambda s: s.stage == 'failed'))


class TestBlogCrossPosting(BlogChannelCommon):
    """ A cross-post completes only when both channels are terminal. """

    def test_cross_post_creates_one_live_post_per_channel(self):
        post = self._create_post(
            [self.network_account, self.blog_account], title='Cross Post')
        post.action_post()
        self.assertEqual(len(post.live_post_ids), 2)

    def test_blog_half_publishes_while_network_is_left_alone(self):
        # The bridge must claim only its own media type: dispatching the
        # blog live post must not touch the network live post.
        post = self._create_post(
            [self.network_account, self.blog_account], title='Split')
        post.action_post()

        blog_live = post.live_post_ids.filtered(
            lambda lp: lp.social_account_id == self.blog_account)
        network_live = post.live_post_ids.filtered(
            lambda lp: lp.social_account_id == self.network_account)

        blog_live._post()

        self.assertEqual(blog_live.state, 'posted')
        self.assertEqual(network_live.state, 'ready')
        article = self.env['blog.post'].search(
            [('social_live_post_id', '=', blog_live.id)])
        self.assertTrue(article)
        self.assertFalse(self.env['blog.post'].search(
            [('social_live_post_id', '=', network_live.id)]))
