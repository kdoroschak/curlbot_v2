import datetime
import logging
import sqlite3
from dataclasses import dataclass
from typing import Optional

import pytz
from praw.reddit import Submission, Subreddit  # type:ignore[import]

from ._action import BotAction, BotActionParams

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SignOfLifeParams(BotActionParams):
    """Holds parameters for the SignOfLife bot action (aka no parameters)."""

    post_id: str = "17olmb2"


class SignOfLife(BotAction):
    """Updates an indicator that the bot is up and running."""

    _params: SignOfLifeParams
    _subreddit: Subreddit
    _subreddit_url: str

    def __init__(
        self,
        subreddit: Subreddit,
        db: Optional[sqlite3.Cursor] = None,
    ) -> None:
        """Updates an indicator that the bot is up and running.

        Args:
            subreddit (Subreddit): Instantiated & authenticated subreddit object. (Note: you can get the reddit object
                from this if needed)
            db (sqlite3.Cursor): In this case, no database is needed, so pass in None. If one is given, it won't be
                used.
        """
        self._subreddit = subreddit
        self._params = SignOfLifeParams()
        self._subreddit_url = f"https://www.reddit.com/r/{self._subreddit.display_name}"
        self._bot_username = self._subreddit._reddit.user.me().name
        self._verify_subreddit_is_self()
        self._send_sign_of_life()  # Send an initial sign upon startup

    def run(self) -> None:
        """Runs the SignOfLife logic -- updates a message in the bot's profile showing the last time this message was
        updated. This helps determine if the bot is still running.

        No args or return value because this is called by a runner/scheduler automatically.
        """
        logger.debug("Running SignOfLife!")
        self._send_sign_of_life()

    def _verify_subreddit_is_self(self) -> None:
        # Check if it's prepended with u_ (user subreddit redirect)
        subreddit_name = self._subreddit.display_name
        if not subreddit_name.startswith("u_"):
            e = f"Subreddit name needs to be prepended with 'u_' in order to be a user subreddit."
            logger.error(e)
            raise ValueError(e)

        # Check if subreddit is self
        self._bot_username
        subreddit_name = subreddit_name.replace("u_", "")
        logger.debug(
            f"Checking if current user ({self._bot_username}) matches subreddit name ({subreddit_name})"
        )
        if self._bot_username != subreddit_name:
            e = (
                "To send a sign of life, the subreddit has to match the bot (i.e. "
                "has to be the bot's profile). Make sure this bot action is "
                "configured with the subreddit equal to the bot's username,"
                f" which is {self._bot_username}."
            )
            logger.error(e)
            raise ValueError(e)

    def _send_sign_of_life(self) -> None:
        logger.info("Sending a sign of life to the bot's profile.")
        west_coast_timezone = pytz.timezone("America/Los_Angeles")
        timestamp = datetime.datetime.now(west_coast_timezone).strftime("%Y-%m-%d %H:%M")
        message = f"Bot last online: {timestamp} (Pacific time).\n\nUpdates ~hourly."
        logger.debug(f"The message will be: {message}")
        logger.debug(f"{vars(self._subreddit.mod)=}")

        # Rewrite the post body to contain the message
        post: Submission = self._subreddit._reddit.submission(id=self._params.post_id)
        post.edit(message)
