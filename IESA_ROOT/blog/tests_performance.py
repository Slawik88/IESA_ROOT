"""Query budgets and counter correctness for the public blog."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase

from .models import BlogSubscription, Comment, CommentLike, Like, Post, PostView
from .utils.querysets import comments_for_post
from .views.posts import PostDetailView, PostListView


class BlogQueryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = get_user_model().objects.create_user(username='perf-author')
        cls.reader = get_user_model().objects.create_user(username='perf-reader')
        cls.post = Post.objects.create(author=cls.author, title='Busy post', text='Text', status='published')
        cls.empty = Post.objects.create(author=cls.author, title='Empty post', text='Text', status='published')
        Like.objects.bulk_create([Like(post=cls.post, user=u) for u in (cls.author, cls.reader)])
        PostView.objects.bulk_create([PostView(post=cls.post, ip_address=f'192.0.2.{i}') for i in range(1, 8)])
        BlogSubscription.objects.create(author=cls.author, user=cls.reader)
        for i in range(5):
            comment = Comment.objects.create(post=cls.post, author=cls.reader, text=f'Comment {i}')
            CommentLike.objects.create(comment=comment, user=cls.author)
            Comment.objects.create(post=cls.post, author=cls.author, text='Reply', parent=comment)

    def view(self, cls, user=None):
        view = cls()
        request = RequestFactory().get('/')
        request.user = user or AnonymousUser()
        view.setup(request)
        return view

    def test_list_counts_are_exact_without_loading_all_likes(self):
        with self.assertNumQueries(1):
            posts = {p.pk: p for p in self.view(PostListView).get_queryset()}
            self.assertEqual(posts[self.post.pk].author.username, self.author.username)
        busy = posts[self.post.pk]
        self.assertEqual((busy.likes_count, busy.comments_count, busy.views_count_cached), (2, 10, 7))
        empty = posts[self.empty.pk]
        self.assertEqual((empty.likes_count, empty.comments_count, empty.views_count_cached), (0, 0, 0))

    def test_detail_does_not_prefetch_unused_comments(self):
        with self.assertNumQueries(1):
            post = self.view(PostDetailView).get_queryset().get(pk=self.post.pk)
        self.assertEqual((post.likes_count, post.subscriber_count, post.views_count_cached), (2, 1, 7))

    def test_comment_authors_likes_and_replies_have_a_fixed_query_budget(self):
        with self.assertNumQueries(2):
            comments = list(comments_for_post(self.post))
            for comment in comments:
                self.assertEqual(comment.author.username, self.reader.username)
                self.assertEqual(comment.likes_count, 1)
                self.assertEqual(list(comment.replies.all())[0].author.username, self.author.username)
        self.assertEqual(len(comments), 5)

    def test_recommendation_counters_do_not_query_per_card(self):
        with self.assertNumQueries(2):
            recommendations = self.empty.get_recommended_posts()
            self.assertEqual(len(recommendations), 1)
            self.assertEqual(recommendations[0].likes_count, 2)
            self.assertEqual(recommendations[0].comments_count, 10)

    def test_search_counts_and_sorting_do_not_multiply_relations(self):
        from .utils.search import search_posts
        from .constants import LIKE_WEIGHT, COMMENT_WEIGHT
        from django.template.loader import render_to_string
        with self.assertNumQueries(1):
            posts = list(search_posts('', status='published', sort='popular'))
            self.assertEqual(posts[0].pk, self.post.pk)
            self.assertEqual(posts[0].engagement, 2 * LIKE_WEIGHT + 10 * COMMENT_WEIGHT)
            self.assertEqual(posts[1].engagement, 0)
            render_to_string('blog/htmx/posts_list_fragment.html', {'posts': posts})
