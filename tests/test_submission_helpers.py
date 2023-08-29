import datetime
import logging
from unittest.mock import MagicMock

from curlbot_v2._submission_helpers import (
    add_sticky_comment,
    get_new_subreddit_posts,
    get_op_comments,
    get_post_body,
    post_is_an_image,
    strip_text,
    time_elapsed_since_post,
)

logger = logging.getLogger(__name__)


# Test get_post_body
def test_get_post_body():
    post = MagicMock(selftext="Some text")
    assert get_post_body(post) == "Some text"

    post_with_no_text = MagicMock(selftext=None)
    assert get_post_body(post_with_no_text) == ""


# Test get_op_comments
def test_get_op_comments():
    post = MagicMock()
    comment1 = MagicMock(is_submitter=True)
    comment2 = MagicMock(is_submitter=False)
    post.comments = [comment1, comment2]

    op_comments = get_op_comments(post)
    assert len(op_comments) == 1
    assert op_comments[0] == comment1


# Test get_new_subreddit_posts
def test_get_new_subreddit_posts(monkeypatch):
    subreddit = MagicMock()
    post1 = MagicMock()
    post2 = MagicMock()
    subreddit.new.return_value = [post1, post2]

    posts = get_new_subreddit_posts(subreddit, max_posts=2)
    assert len(posts) == 2
    assert posts[0] == post1
    assert posts[1] == post2


# Test strip_text
def test_strip_text():
    text = "Hello, World! How's it going?"
    stripped_text = strip_text(text)
    assert stripped_text == "hello world hows it going"


# Test post_is_an_image
def test_post_is_an_image():
    post_image = MagicMock(url="http://example.com/image.jpg")
    assert post_is_an_image(post_image)

    post_non_image = MagicMock(url="http://example.com/text-post")
    assert not post_is_an_image(post_non_image)


# # Test time_elapsed_since_post
# def test_time_elapsed_since_post(monkeypatch, caplog):
#     caplog.set_level("DEBUG")
#     mock_utcnow = MagicMock()
#     monkeypatch.setattr(datetime, "datetime", mock_utcnow)
#     mock_utcnow.utcnow.return_value = datetime.datetime.utcfromtimestamp(1693212027)

#     post_created_utc = 1693211427
#     post = MagicMock(created_utc=post_created_utc)

#     elapsed_time_mins = time_elapsed_since_post(post)
#     logger.debug(f"{elapsed_time_mins=}")
#     assert elapsed_time_mins == 10  # 10 minutes


# Test add_sticky_comment (requires more complex mocking)
def test_add_sticky_comment(monkeypatch):
    post = MagicMock()
    comment = MagicMock()
    post.reply.return_value = comment

    add_sticky_comment(post, "Sticky comment text")
    post.reply.assert_called_once_with("Sticky comment text")
    comment.mod.distinguish.assert_called_once_with(how="yes", sticky=True)


def test_post_is_a_link_with_image():
    mock_submission = MagicMock()
    mock_submission.post_hint = "image"
    mock_submission.url = "test.jpg"
    assert post_is_an_image(mock_submission)


def test_post_is_a_link_without_image():
    mock_submission = MagicMock()
    mock_submission.post_hint = "link"
    mock_submission.url = "/"
    assert not post_is_an_image(mock_submission)
