import datetime
import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

from praw.reddit import Submission, Subreddit  # type:ignore[import]

from curlbot_v2._submission_helpers import (
    add_sticky_comment,
    get_all_op_text,
    get_new_subreddit_posts,
    post_is_an_image,
    time_elapsed_since_post,
)

from ._action import BotAction, BotActionParams

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RoutineCheckerParams(BotActionParams):
    """Holds parameters for the RoutineChecker bot action.

    These get parsed from the wiki and then dumped into this class to be referenced throughout.

    To make a value None from the wiki, type the string "null" with no quotes.

    Args:
        flair_to_check (List[Union[str, None]]): List of flair to check. This uses the flair text
            in the flair configuration, not the css/etc. To check the case where a post has no
            flair, include None in this list ("null" in the wiki).
        remind_after_mins (Optional[int]): If a post is missing a routine, add a sticky reminder to
            the post after this many minutes.
        remove_after_mins (Optional[int]): If a post is missing a routine, silently remove the post
            after this many minutes.
        report_after_mins (Optional[int]): If a post is missing a routine, report it after this
            many minutes
        keywords (List[str]): If the post text has any of these keywords, we will say it has a
            routine. This usually includes "routine", but we also include other words that indicate
            that someone has put thought into a comment, like "shampoo".
        min_routine_characters (int, by default 0): The minimum numbers of letters and spaces that
             must be in someone's routine to call it good enough.
        sidestepping_phrases (List[str], by default ("don't have a routine", "no routine",
            "dont have a routine")): If any of these phrases are in the text (and there's no better
            alternative comment that actually has a routine), we consider the post to be cheating.
        max_posts (int, by default 100): Maximum number of posts to pull at a time to check. Dial
            this way down for smaller subreddits with lower post volume.
        reminder_messages_by_flair (Dict[str, str], by default field(default_factory dict)): Set a
            specific reminder message for each flair. Although it's a little annoying, each flair
            has to be specified separately, for now.
        ignore_posts_over_age_hours (int, by default 8): If the post is over this many hours old,
            we won't take any action on it. This prevents spam if the bot goes down for a bit, etc.
    """

    flair_to_check: List[Union[str, None]]
    remind_after_mins: Optional[int]
    remove_after_mins: Optional[int]
    report_after_mins: Optional[int]
    keywords: List[str]
    min_routine_characters: int = 0
    sidestepping_phrases: List[str] = ("don't have a routine", "no routine", "dont have a routine")
    max_posts: int = 100
    reminder_messages_by_flair: Dict[str, str] = field(default_factory=dict)
    ignore_posts_over_age_hours: int = 8

    def __repr__(self) -> str:
        s = (
            "RoutineCheckerParams:\n"
            f"  flair_to_check: {self.flair_to_check}\n"
            f"  remind_after_mins: {self.remind_after_mins}\n"
            f"  remove_after_mins: {self.remove_after_mins}\n"
            f"  report_after_mins: {self.report_after_mins}\n"
            f"  keywords: {self.keywords}\n"
            f"  min_routine_characters: {self.min_routine_characters}\n"
            f"  sidestepping_phrases: {self.sidestepping_phrases}\n"
            f"  max_posts: {self.max_posts}\n"
            f"  ignore_posts_over_age_hours: {self.ignore_posts_over_age_hours}\n"
            f"  reminder_messages_by_flair:\n"
        )
        for flair, message in self.reminder_messages_by_flair.items():
            s += f"    {flair}:\n      {message}"
        return s


@dataclass(frozen=True)
class PostState:
    """Helper to record a post's state at the time this object was generated.

    Intentionally can't be updated directly - use the update_x() functions for that. This is to
    control access to these variables (no accidental modification) without having to manually
    recreate a new PostState each time we want to modify something. This helped me keep things
    consistent when doing development and I hope it makes it easier for the future.

    Args:
        post_id (str): Reddit post ID
        post_in_database (bool): Whether the post is found in the database
        needs_routine_per_requirements (bool): Whether the post requires a routine per the rules
        has_routine (bool): Whether the post has a routine already
        stop_checking (bool): Whether or not we've stopped checking this post
        reminded_utc (int): The time at which this post was sent a reminder sticky, as a UTC
            integer timestamp.
        removed_utc (int): The time at which this post was removed, as a UTC integer timestamp.
        reported_utc (int): The time at which this post was reported, as a UTC integer timestamp.
    """

    post_id: str
    post_in_database: bool
    needs_routine_per_requirements: bool
    has_routine: bool
    stop_checking: bool
    reminded_utc: int
    removed_utc: int
    reported_utc: int

    def __post_init__(self) -> None:
        """Provides some validation beyond optional type checking."""
        assert type(self.post_id) is str
        assert type(self.post_in_database) is bool
        assert type(self.needs_routine_per_requirements) is bool
        assert type(self.has_routine) is bool
        assert type(self.stop_checking) is bool
        assert type(self.reminded_utc) is int
        assert type(self.removed_utc) is int
        assert type(self.reported_utc) is int

    def update_needs_routine(self, needs_routine: bool) -> "PostState":
        """Update the field "needs_routine_per_requirements" and return a new copy of this object.

        Args:
            needs_routine (bool): Whether the post requires a routine per the rules

        Returns:
            PostState: Same as self, but with an updated field
        """
        vars = self.__dict__
        vars["needs_routine_per_requirements"] = needs_routine
        return PostState(**vars)

    def update_has_routine(self, has_routine: bool) -> "PostState":
        """Update the field "has_routine" and return a new copy of this object.

        Args:
            has_routine (bool): Whether the post has a routine already

        Returns:
            PostState: Same as self, but with an updated field
        """
        vars = self.__dict__
        vars["has_routine"] = has_routine
        return PostState(**vars)

    def update_stop_checking(self, stop_checking: bool) -> "PostState":
        """Update the field "stop_checking" and return a new copy of this object.

        Args:
            stop_checking (bool): Whether or not we've stopped checking this post

        Returns:
            PostState: Same as self, but with an updated field
        """
        vars = self.__dict__
        vars["stop_checking"] = stop_checking
        return PostState(**vars)

    def update_reminded_utc(self, reminded_utc: int) -> "PostState":
        """Update the field "reminded_utc" and return a new copy of this object.

        Args:
            reminded_utc (int):The time at which this post was sent a reminder sticky, as a UTC
                integer timestamp.

        Returns:
            PostState: Same as self, but with an updated field
        """
        vars = self.__dict__
        vars["reminded_utc"] = reminded_utc
        return PostState(**vars)

    def update_removed_utc(self, removed_utc: int) -> "PostState":
        """Update the field "removed_utc" and return a new copy of this object.

        Args:
            removed_utc (int): The time at which this post was removed, as a UTC integer timestamp.

        Returns:
            PostState: Same as self, but with an updated field
        """
        vars = self.__dict__
        vars["removed_utc"] = removed_utc
        return PostState(**vars)

    def update_reported_utc(self, reported_utc: int) -> "PostState":
        """Update the field "reported_utc" and return a new copy of this object.

        Args:
            reported_utc (int):The time at which this post was reported, as a UTC integer timestamp.

        Returns:
            PostState: Same as self, but with an updated field
        """
        vars = self.__dict__
        vars["reported_utc"] = reported_utc
        return PostState(**vars)


@dataclass
class RoutineErrors:
    """Class to help keep track of issues with someone's typed out routine, compare which errors
    are better/worse, and summarizing the errors for a report message.

    This helps add some structure to passing this info around (no lists of errors, etc.) and let us
    handle different issues separately if needed.

    Args:
        comment (Optional[str]): The comment this error relates to (likely stripped at this point).
        avoiding_routine (Optional[bool]): Whether the comment appears to be avoiding the reqs by
            saying they don't have a routine, etc.
        too_short (Optional[bool]): Whether the comment is too short.
    """

    comment: Optional[str]
    avoiding_routine: Optional[bool]
    too_short: Optional[bool]

    def is_better_than(self, other: "RoutineErrors") -> bool:
        """Return true if the current object (self) is better than the other object.

        Args:
            other (RoutineErrors): another RoutineErrors object

        Returns:
            bool: True if self is better, False if they're tied or other is better
        """
        # If self has a comment and the other doesn't, this one is better by default
        if self.comment and not other.comment:
            return True
        elif other.comment and not self.comment:
            return False
        # Otherwise, check how many errors they have and pick the lower one
        n_errs_self = self.avoiding_routine + self.too_short
        n_errs_other = other.avoiding_routine + other.too_short
        return n_errs_self < n_errs_other

    def summarize_errors(self) -> str:
        """Returh a different error message depending on which errors are set.

        Note that these should be kept short for use as removal reasons.

        Returns:
            str: _description_
        """
        if not self.comment:
            return "Missing routine; no comments from OP at all."
        if self.avoiding_routine and self.too_short:
            return "OP may be saying they have no routine & all comments are too short."
        elif self.avoiding_routine and not self.too_short:
            return "OP may be saying they have no routine. Please check!"
        else:
            return "OP's routine comment is too short. Please check!"


class RoutineChecker(BotAction):
    """TODO"""

    _params: RoutineCheckerParams
    _subreddit: Subreddit
    _subreddit_url: str
    _db: sqlite3.Cursor
    _DB_TABLE_NAME: str = "post_history"
    _WIKI_CONFIG_PAGE: str = "routine_checker_config"

    def __init__(
        self,
        subreddit: Subreddit,
        db: sqlite3.Cursor,
    ) -> None:
        """RoutineChecker TODO checks new image posts in a subreddit to see if they fulfill some criteria.

        Args:
            subreddit (Subreddit): Instantiated & authenticated subreddit object. (Note: you can
                get the reddit object from this if needed)
            db (sqlite3.Cursor): Instantiated database. We'll use a table within this database to
                track posts over time.
        """
        self._subreddit = subreddit
        self._subreddit_url = f"https://www.reddit.com/r/{self._subreddit.display_name}"
        self._db = self._set_up_db(db, self._DB_TABLE_NAME)

        # Get the parameters from the wiki and make sure they're valid
        param_dict = self._get_config_from_wiki(self._WIKI_CONFIG_PAGE)
        self._validate_config(param_dict)
        self._params = RoutineCheckerParams(**param_dict)
        self._validate_flair_messages(self._params)
        logger.debug(f"Config loaded and parsed: \n{self._params}")

    def run(self) -> None:
        """Runs the RoutineChecker logic -- pulls the config from the wiki, checks new posts for
        routines, and updates the database accordingly.

        No args or return value because this is called by a runner/scheduler automatically.
        """
        logger.debug("Running RoutineChecker!")

        # Pull the parameters again, so we pick up any changes live
        param_dict = self._get_config_from_wiki(self._WIKI_CONFIG_PAGE)
        try:
            self._validate_config(param_dict)
            params = RoutineCheckerParams(**param_dict)
            self._validate_flair_messages(params)
            self._params = params
            logger.debug(f"Config loaded and parsed: \n{self._params}")
        except AssertionError as e:
            logger.error(f"Issue with the flair messages (not updating params): {e}")
        except ValueError as e:
            logger.error(f"Issue with the parameters (not updated): {e}")

        posts = get_new_subreddit_posts(self._subreddit, self._params.max_posts)
        for post in posts:
            previous_post_state = self._get_post_state_from_database(post)

            # Case closed already - stop checking this post & move on
            if previous_post_state.stop_checking:
                continue

            # Check if the post needs a routine (and if we should continue checking this post)
            new_post_state = self._check_post(post, previous_post_state)

            # Stopped checking this post - update database & move on
            # We could've stopped checking for several reasons - doesn't need a routine, etc.
            if new_post_state.stop_checking:
                self._update_db(previous_post_state, new_post_state)
                continue

            # If the post needs a routine & doesn't have one
            if new_post_state.needs_routine_per_requirements and not new_post_state.has_routine:
                logger.debug(f"{new_post_state=}")
                # Remind/report/remove if it's time to do so
                new_post_state = self._remind_remove_report(post, new_post_state)

            # Update the database with new info about whether we took action
            self._update_db(previous_post_state, new_post_state)

    def _validate_config(self, config: Dict[str, Any]) -> None:
        # TODO maybe make this part of the parameters (making the dict into the object & validating)
        errors = []
        required_params = [
            "flair_to_check",
            "remind_after_mins",
            "remove_after_mins",
            "report_after_mins",
            "keywords",
            "min_routine_characters",
            "sidestepping_phrases",
            "max_posts",
            "reminder_messages_by_flair",
        ]
        missing_params = []
        for param in required_params:
            if param not in config:
                missing_params.append(param)
        if len(missing_params) > 0:
            raise ValueError(f"Parameter(s) '{missing_params=}' are missing from the config.")

        # Check the type of the flair variable
        if not isinstance(config["flair_to_check"], list) or not all(
            isinstance(item, (str, type(None))) for item in config["flair_to_check"]
        ):
            e = "flair_to_check parameter should be a list of strings or None values."
            logger.error(e)
            errors.append(e)

        # Check if all values are valid link flairs
        # First, get the list of valid flairs
        valid_link_flairs = []
        for flair in self._subreddit.flair.link_templates:
            valid_link_flairs.append(flair["text"])
        # Then check the flairs specified here against the valid flairs
        flairs_to_check = config.get("flair_to_check")
        for flair in flairs_to_check:
            if flair not in valid_link_flairs and flair is not None:
                e = f"Flair {flair} not valid. Valid flairs: {valid_link_flairs}"
                logger.error(e)
                errors.append(e)

        for time_param in ["remind_after_mins", "remove_after_mins", "report_after_mins"]:
            if config[time_param] is not None and not isinstance(config[time_param], int):
                e = f"{time_param} should be an integer or None (given {config[time_param]})."
                logger.error(e)
                errors.append(e)
        # TODO add more validation for the timing

        if not isinstance(config["keywords"], list) or not all(
            isinstance(keyword, str) for keyword in config["keywords"]
        ):
            e = "keywords parameter should be a list of strings."
            logger.error(e)
            errors.append(e)

        if (
            not isinstance(config["min_routine_characters"], int)
            or config["min_routine_characters"] < 0
        ):
            e = "min_routine_characters should be a non-negative integer."
            logger.error(e)
            errors.append(e)

        if not isinstance(config["sidestepping_phrases"], list) or not all(
            isinstance(phrase, str) for phrase in config["sidestepping_phrases"]
        ):
            e = "sidestepping_phrases parameter should be a list of strings."
            logger.error(e)
            errors.append(e)

        if not isinstance(config["max_posts"], int) or config["max_posts"] <= 0:
            e = "max_posts should be a positive integer."
            logger.error(e)
            errors.append(e)

        if not isinstance(config["reminder_messages_by_flair"], dict):
            e = "reminder_messages_by_flair should be a dictionary."
            logger.error(e)
            errors.append(e)

    def _validate_flair_messages(self, params: RoutineCheckerParams) -> None:
        """Check that, if reminders are on, each flair we're checking has a canned sticky message
        set for it. Remember to set one for the empty flair (null in wiki, None here) if needed.

        Args:
            params (RoutineCheckerParams): Params object that's already been parsed.

        Raises:
            AssertionError: Raised if not all the flairs in flair_to_check have a message in the dict
        """
        reminders_on = params.remind_after_mins != None and params.remind_after_mins > 0
        if reminders_on:
            flair_messages = params.reminder_messages_by_flair
            flair_to_check = set(params.flair_to_check)
            flair_with_messages = set(flair_messages.keys())
            assert flair_with_messages.issuperset(flair_to_check)  # TODO better message

    def _remind_remove_report(self, post: Submission, post_state: PostState) -> PostState:
        """For the given post, remind, remove, and/or report it if it's due for any of those
        actions. We'll call this on a post if we know it doesn't have a routine yet, and may need
        to take some kind of action.

        Args:
            post (Submission): post that needs reminding/removing/reporting
            post_state (PostState): history of what's happened with the post (we'll read this and
                add to it here)

        Returns:
            PostState: Updated state of the post
        """
        time_since_post_mins = time_elapsed_since_post(post)
        time_right_now_utc = int(datetime.datetime.utcnow().timestamp())
        remind_after_mins = self._params.remind_after_mins
        remove_after_mins = self._params.remove_after_mins
        report_after_mins = self._params.report_after_mins
        remind_mode_on = remind_after_mins != None and remind_after_mins > 0
        remove_mode_on = remove_after_mins != None and remove_after_mins > 0
        report_mode_on = report_after_mins != None and report_after_mins > 0

        assert (
            post_state.stop_checking is False
        ), "Called _remind_remove_report but it says case closed."

        stop_checking = False
        been_too_long = self._post_is_over_time_limit(post)
        logger.debug(
            f"REMIND is {'on' if remind_mode_on else 'off'}; "
            f"REMOVE is {'on' if remove_mode_on else 'off'}; "
            f"REPORT is {'on' if remove_mode_on else 'off'}"
        )
        logger.debug(
            f"REMIND - {remind_after_mins} mins; "
            f"REMOVE - {remove_after_mins} mins; "
            f"REPORT - {report_after_mins} mins"
        )

        # Send reminder if...
        # * the "remind" option is on
        # * AND we haven't sent a reminder yet
        # * AND it's due for a reminder
        # * AND it's not yet time to remove it
        # * AND it hasn't been an unfairly long amount of time (at some point, if we missed it we missed it)
        reminded_utc = post_state.reminded_utc
        if remind_mode_on:
            if (
                reminded_utc <= 0  # We haven't sent a reminder yet
                and time_since_post_mins > remind_after_mins  # Reminder is due
                and time_since_post_mins < remove_after_mins  # Removal is NOT due
                and not been_too_long
            ):
                # Send reminder via sticky message
                sticky_msg = self._get_sticky_message_for_flair(post.link_flair_text)
                add_sticky_comment(post, sticky_msg)

                # Mark the time we sent the reminder (utc)
                reminded_utc = time_right_now_utc
                logger.info(
                    f"Sent reminder: {self._subreddit_url}/comments/{post.id} (elapsed time: "
                    f"{time_since_post_mins:0.1f} mins)"
                )
            elif (
                reminded_utc <= 0  # We haven't sent a reminder yet
                and time_since_post_mins > remind_after_mins  # Reminder is due
                # and time_since_post_mins < remove_after_mins  # Removal is NOT due
            ):
                logger.debug(
                    f"Didn't remind for post {post.id} because removal was due (elapsed time: "
                    f"{time_since_post_mins:0.1f} mins)"
                )
            else:
                logger.debug(
                    f"Didn't remind for post {post.id} (elapsed time: "
                    f"{time_since_post_mins:0.1f} mins)"
                )

        # Remove the post if...
        # * the "remove" option is on
        # * it's due to be removed
        # * it hasn't already been removed
        # * we sent a reminder (i.e. don't remove if it bugged out and didn't send a reminder)
        # * it hasn't been an unfairly long time (if we didn't catch it in X hours, that's on us)
        removed_utc = post_state.removed_utc
        if remove_mode_on:
            if (
                removed_utc <= 0  # We haven't removed it yet
                and time_since_post_mins > remove_after_mins  # Removal is due
                and (
                    reminded_utc > 0 or not remind_mode_on
                )  # We sent a reminder already (if reminders are on)
                and not been_too_long  # It hasn't been an unfairly long time
            ):
                post.mod.remove()
                removed_utc = time_right_now_utc
                logger.info(
                    f"Removed post: {self._subreddit_url}/comments/{post.id} (elapsed time: "
                    f"{time_since_post_mins:0.1f} mins)"
                )
            if been_too_long:
                logger.debug(
                    f"Too much time has passed for post {post.id} ({time_since_post_mins:0.1f} mins), "
                    "but it would've been removed."
                )

        # Report the post if...
        # * the "report" option is on
        # * it hasn't already been reported
        # * it's due to be reported
        # * it hasn't been an unfairly long time
        reported_utc = post_state.reported_utc
        if report_mode_on:
            if (
                reported_utc <= 0  # We haven't reported it yet
                and time_since_post_mins > report_after_mins  # Due to be reported
                and not been_too_long
            ):
                logger.info(
                    f"Reported post: {self._subreddit_url}/comments/{post.id} (elapsed time: "
                    f"{time_since_post_mins:0.1f} mins)"
                )
                op_cms = get_all_op_text(post)
                if len(op_cms) > 0:
                    msg = (
                        f">{time_since_post_mins:0.1f} mins and *possibly* no routine. (OP commented "
                        "but there's no keyword.) Please check!"
                    )
                else:
                    msg = (
                        f">{time_since_post_mins:0.1f} mins and no routine has been posted. (No "
                        "comments from OP at all). Please check!"
                    )
                post.report(msg)
                reported_utc = time_right_now_utc

        # Report the post for manual processing if it's been too long
        # (Meaning it's past time for any action, but not "too long" to check per the parameter)
        time_values = [  # Find the longest time from remind/remove/report
            time
            for time in [remind_after_mins, remove_after_mins, report_after_mins]
            if time is not None
        ]
        max_time_mins = max(time_values) if time_values else None
        if time_since_post_mins > max_time_mins and not been_too_long:
            post.report(f"> {max_time_mins} mins and *possibly* no routine. Please check!")
            reported_utc = time_right_now_utc
            stop_checking = True
        elif time_since_post_mins > max_time_mins:
            stop_checking = True

        post_state = (
            post_state.update_stop_checking(stop_checking)
            .update_reminded_utc(reminded_utc)
            .update_removed_utc(removed_utc)
            .update_reported_utc(reported_utc)
        )

        return post_state

    def _get_sticky_message_for_flair(self, flair: Optional[str]) -> str:
        """Get the formatted text of the message we'll apply as a sticky on a post, by flair.

        Args:
            flair (Optional[str]): flair to retrieve

        Returns:
            str: markdown-formatted string message
        """
        msg = self._params.reminder_messages_by_flair.get(flair)
        return msg

    def _get_post_state_from_database(self, post: Submission) -> PostState:
        """Looks up the post in the database by id. If it's there, it formats the db data into a
        PostState object. If it's not there, we'll initialize some info, write it to the db, and
        return the resulting PostState.

        Args:
            post (Submission): Post to retrieve from the db

        Returns:
            PostState: Current state of the post in the database
        """
        logger.debug(f"Attempting to retrieve post {post.id} from database.")
        db_posts = self._db.execute(
            f"""SELECT * FROM {self._DB_TABLE_NAME} WHERE id=? ORDER BY created_utc DESC""",
            (post.id,),
        ).fetchall()
        if len(db_posts) > 1:
            # Error state: too many posts in db with this ID
            e = f">1 post with this id ({post.id}) found in the db (table {self._DB_TABLE_NAME})."
            logger.error(e)
            raise ValueError(e)
        elif len(db_posts) == 0:
            # Post not in database. Create a PostState object and insert it in the database
            logger.debug(f"Post {post.id} not found in database.")
            post_state = PostState(
                post_id=post.id,
                post_in_database=False,
                needs_routine_per_requirements=False,  # Not meaningful
                has_routine=False,  # Not meaningful
                stop_checking=False,
                reminded_utc=-1,
                removed_utc=-1,
                reported_utc=-1,
            )
            self._insert_db(post, post_state)
            return post_state
        else:
            logger.debug("Found post in database.")
            # Post is in database. Create a PostState object from the database entry and return it
            (
                post_id,
                url,
                created_utc,
                needs_routine,
                has_routine,
                reminded_utc,
                removed_utc,
                reported_utc,
                case_closed,
            ) = db_posts[0]
            post_state = PostState(
                post_id,
                post_in_database=True,
                needs_routine_per_requirements=bool(needs_routine),
                has_routine=bool(has_routine),
                stop_checking=bool(case_closed),
                reminded_utc=reminded_utc,
                removed_utc=removed_utc,
                reported_utc=reported_utc,
            )
            return post_state

    def _check_post(self, post: Submission, previous_post_state: PostState) -> PostState:
        """Check whether the post needs/has a routine. If not needed, we'll stop further checking.
        We'll check whether the routine is required regardless of what the status was before -
        sometimes the flair changes, changing the requirements.

        Args:
            post (Submission): post to check
            previous_post_state (PostState): All the info we already had on this post from the db

        Returns:
            PostState: Post state with updated info, like whether they added their routine since
                the last check or whether it doesn't need a routine.
        """

        # Check if the post NEEDS a routine. Don't use db flag for this - flair could have changed!
        needs_routine = self._post_needs_routine(post)
        post_state = previous_post_state.update_needs_routine(needs_routine)

        if needs_routine:
            # Check if the post HAS a routine / meets requirements
            if post_state.has_routine:
                post_meets_reqs = True
                errors = None
            else:
                post_meets_reqs, errors = self._post_meets_requirements(post)
                post_state = post_state.update_has_routine(post_meets_reqs)

            # Check the errors
            # Special case! Has a routine but trying to cheat - report & keep checking
            # If they add a real routine eventually, great, the bot will find it.
            # If they don't add a real routine, the bot will still remove it (if removal is on)
            if errors is not None and (errors.avoiding_routine or errors.too_short):
                post.report(errors.summarize_errors())

            # If the post has a routine, we can mark it to stop checking in the future
            if post_meets_reqs:
                post_state = post_state.update_stop_checking(True)
        else:
            post_state = post_state.update_stop_checking(True)
        return post_state

    def _post_is_over_time_limit(self, post: Submission) -> bool:
        """Check if we should stop checking for a routine based on how long it's been since the
        post was created.

        Args:
            post (Submission): post to check

        Returns:
            bool: True if we should stop checking the post based on how long it's been since the
                post was created, otherwise false
        """
        time_since_post = time_elapsed_since_post(post)
        ignore_posts_over_age_mins = self._params.ignore_posts_over_age_hours * 60
        logger.debug(f"{time_since_post=:0.2f} >? {ignore_posts_over_age_mins=:0.2f}")
        # The post is too old overall
        if time_since_post > ignore_posts_over_age_mins:
            return True
        else:
            return False

    def _post_needs_routine(self, post: Submission) -> bool:
        """Defines the criteria for whether a post needs a routine. Checks flair against the
        parameters.flair_to_check, and whether the post contains an image as the main post type
        (i.e., doesn't check for image links in the body)

        Args:
            post (Submission): submission to check

        Returns:
            bool: whether the post requires a routine (per the rules)
        """

        # Flair
        flair_to_check = self._params.flair_to_check
        post_flair = post.link_flair_text
        logger.debug(f"Checking post flair {post_flair} in {flair_to_check}")
        has_flair_requiring_routine = True if post_flair in flair_to_check else False
        logger.debug(f"{has_flair_requiring_routine=}")

        # Image post
        image_post = post_is_an_image(post)
        logger.debug(f"Is post an image? {image_post}")

        if image_post and has_flair_requiring_routine:
            return True
        else:
            return False

    def _set_up_db(self, db: sqlite3.Cursor, db_table_name: str) -> sqlite3.Cursor:
        """Create the database table in the given database, or not if it already exists."""
        try:
            logger.debug(f"Creating new table in db, {db_table_name}.")
            db.execute(
                f"""CREATE TABLE {db_table_name}
                    (id text, url text, created_utc int, needs_routine int, has_routine int,
                    reminded_utc int, removed_utc int, reported_utc int, case_closed int)"""
            )
        except sqlite3.OperationalError as e:
            # We don't want to overwrite the db every time we start the bot
            if "already exists" in str(e):
                logger.debug("Database already exists, no need to initialize.")
            else:
                logger.warning(f"Unknown OperationalError: {e}")
                raise
        return db

    def _update_db(self, db_post_state: PostState, post_state: PostState) -> None:
        """Update individual fields in the database. There's probably a better way to do this,
        but it works (was lifted from the old version mostly.)

        Args:
            db_post_state (PostState): Prior database state (for comparison to know if it changed)
            post_state (PostState): Post state with new information to update the db with
        """
        update_table = f"UPDATE {self._DB_TABLE_NAME}"
        where_id_is = f"WHERE id = '{post_state.post_id}'"
        if (
            post_state.needs_routine_per_requirements
            != db_post_state.needs_routine_per_requirements
        ):
            db_cmd = f"{update_table} SET needs_routine = {int(post_state.needs_routine_per_requirements)} {where_id_is}"
            logger.debug(db_cmd)
            self._db.execute(db_cmd)
        elif post_state.has_routine != db_post_state.has_routine:
            db_cmd = (
                f"{update_table} SET has_routine = {int(post_state.has_routine)} {where_id_is}"
            )
            logger.debug(db_cmd)
            self._db.execute(db_cmd)
        elif post_state.reminded_utc != db_post_state.reminded_utc:
            db_cmd = f"{update_table} SET reminded_utc = {post_state.reminded_utc} {where_id_is}"
            logger.debug(db_cmd)
            self._db.execute(db_cmd)
        elif post_state.removed_utc != db_post_state.removed_utc:
            db_cmd = f"{update_table} SET removed_utc = {post_state.removed_utc} {where_id_is}"
            logger.debug(db_cmd)
            self._db.execute(db_cmd)
        elif post_state.reported_utc != db_post_state.reported_utc:
            db_cmd = f"{update_table} SET reported_utc = {post_state.reported_utc} {where_id_is}"
            logger.debug(db_cmd)
            self._db.execute(db_cmd)

    def _insert_db(self, post: Submission, post_state: PostState) -> None:
        # TODO
        row = (
            post_state.post_id,
            post.url,
            post.created,
            int(post_state.needs_routine_per_requirements),
            int(post_state.has_routine),
            post_state.reminded_utc,
            post_state.removed_utc,
            post_state.reported_utc,
            int(post_state.stop_checking),
        )
        logger.debug(f"INSERTING row: {row=}")
        self._db.execute(
            f"""INSERT INTO {self._DB_TABLE_NAME}
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            row,
        )
        db_conn = self._db.connection
        db_conn.commit()

    def _post_meets_requirements(self, post: Submission) -> Tuple[bool, Optional[RoutineErrors]]:
        """Check whether the post meets all the requirements - having a routine, and not cheating
        (including cheater phrases or being too short). Looks through all the comments from OP and
        any body text from the post itself. Returns True for the first comment or post that meets
        the requirements.

        If any comments partly meet the requirements, we'll make a note of the best post so far and
        keep looking.

        Args:
            post (Submission): post to check

        Returns:
            Tuple[bool, Optional[RoutineErrors]]: whether the post meets reqs, and any issues
                that the post has (too short, avoids routine)
        """
        op_text = get_all_op_text(post)
        best_so_far = RoutineErrors(avoiding_routine=None, too_short=None, comment=None)
        for comment in op_text:
            # Evaluate all the requirements
            has_kwd = self._text_has_routine(comment)
            has_min_length = self._text_fulfills_min_length(comment)
            avoiding_routine = self._text_has_sidesteppers(comment)

            # See if the comment meets the requirements
            if has_kwd and has_min_length and not avoiding_routine:  # Meets all requirements
                return True, None
            elif has_kwd:  # Has a routine but is missing something
                err = RoutineErrors(
                    avoiding_routine=avoiding_routine, too_short=~has_min_length, comment=comment
                )
                best_so_far = err if err.is_better_than(best_so_far) else best_so_far
        return False, best_so_far

    def _text_has_routine(self, text: str) -> bool:
        """Whether the given text has a routine. Right now this is implemented as checking for
        keywords, but could be changed to something fancier in the future.

        Args:
            text (str): text to check for keywords

        Returns:
            bool: whether the text has any of the keywords
        """
        for k in self._params.keywords:
            if k in text:
                return True
        return False

    def _text_fulfills_min_length(self, text: str) -> bool:
        """Whether the text fulfills the minimum character count, if there is one.
        Probably doesn't need to be its own function but it makes the code more readable.

        Args:
            text (str): text to check

        Returns:
            bool: whether the text is longer than the minimum.
        """
        if (
            self._params.min_routine_characters > 0
            and self._params.min_routine_characters is not None
        ):
            return len(text) >= self._params.min_routine_characters
        else:
            return True

    def _text_has_sidesteppers(self, text: str) -> bool:
        """Whether the given text has any phrases that indicate that they're avoiding writing their
        routine. Right now this is implemented as checking for keywords, but could be changed to
        something fancier in the future. Example: "I don't have a routine"

        Args:
            text (str): text to check for keywords

        Returns:
            bool: whether the text has any of the sidestepper keywords
        """
        for cheat in self._params.sidestepping_phrases:
            if cheat in text:
                return True
        return False
