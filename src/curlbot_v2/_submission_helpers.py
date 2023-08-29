import datetime
import logging
import string
from typing import List, Optional

from praw.reddit import Comment, Submission, Subreddit
from prawcore.exceptions import RequestException

logger = logging.getLogger(__name__)


def get_post_body(post: Submission) -> str:
    """Get the text from a submission, whether it's a text post or an image+text post.

    Even though this is a one-liner in praw to do both (text post and image/gallery+text), I'm abstracting it here in
    case this implementation changes and to handle the case where the text is None.

    If the post is a link submission, there's no text.

    Args:
        post (Submission): post to retrieve text from

    Returns:
        str: The text from the post. If the post doesn't have text, return an empty string.
    """
    text = post.selftext
    if text is None:
        text = ""
    return text


def get_op_comments(post: Submission) -> List[Comment]:
    """Get all comments on a post that are authored by the OP of the post.

    Args:
        post (Submission): post to check for comments

    Returns:
        List[Comment]: all of OP's comments
    """
    op_comments = []
    for comment in post.comments:
        if comment.is_submitter:
            op_comments.append(comment)
    return op_comments


def get_all_op_text(post: Submission) -> List[str]:
    text_body = get_post_body(post)
    comments = get_op_comments(post)
    comments_text = [strip_text(comment.body) for comment in comments]
    op_text = [strip_text(text_body)] + comments_text
    return op_text


def get_new_subreddit_posts(
    subreddit: Subreddit, max_posts: int = 100, max_attempts: int = 3
) -> List[Submission]:
    """Retrieve the newest posts from the subreddit. Will try max_attempts times to accommodate transient request errors
    when querying reddit.

    max_posts should be tuned based on the frequency of subreddit checks and the submission rate in the subreddit.

    Args:
        subreddit (Subreddit): subreddit instance to pull posts from
        max_posts (int, optional): Number of posts to check. Defaults to 100.

    Returns:
        List[Submission]: List of posts pulled from subreddit
    """
    logger.info(f"Scanning {max_posts} newest posts of " f"{subreddit.display_name}.")
    attempts = 0
    while attempts < max_attempts:
        try:
            posts = list(subreddit.new(limit=max_posts))
            break
        except RequestException:
            attempts += 1
            if attempts >= max_attempts:
                raise
    return posts


def strip_text(text: str) -> str:
    """Make the text lowercase & without any punctuation.

    Args:
        text (str): input text

    Returns:
        str: lowercase variation of the input text without punctuation
    """
    text = text.lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    return text


def post_is_an_image(post: Submission) -> bool:
    """Returns True if the post contains an image as the main post type (doesn't check for image
    links in the post body).

    Args:
        post (Submission): post to check

    Returns:
        bool: True if image, False otherwise
    """
    url = post.url
    url_ending = url.split(".")[-1]

    if (
        url_ending in ["jpg", "jpeg", "png"]
        or "imgur" in url
        or "v.redd.it" in url
        or "gallery" in url
    ):
        return True
    else:
        return False


def time_elapsed_since_post(post: Submission) -> float:
    """Calculate how much time in minutes has elapsed since the post was made.

    Args:
        post (Submission): post to check

    Returns:
        float: elapsed time (in minutes) since post creation
    """
    post_time = datetime.datetime.utcfromtimestamp(post.created_utc)
    now = datetime.datetime.utcnow()

    time_since_post = now - post_time
    logger.debug(f"{time_since_post=}")
    time_since_post_mins = time_since_post.total_seconds() / 60
    return time_since_post_mins


def add_sticky_comment(post: Submission, comment_text: str) -> None:
    """Add a sticky comment to a post

    Args:
        post (Submission): post to add the sticky to
        comment_text (str): text for the sticky
    """
    logger.info(f"Adding sticky comment: {comment_text}")
    comment = post.reply(comment_text)
    comment.mod.distinguish(how="yes", sticky=True)
