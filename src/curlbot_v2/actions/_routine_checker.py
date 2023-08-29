import datetime
import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

from praw.reddit import Submission, Subreddit

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
    # TODO document
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
    # TODO write these messages, develop the format for them in the wiki, and handle reading them


@dataclass(frozen=True)
class PostState:
    """Helper to record a post's state at the time this object was generated.
    Intentionally can't be updated - use the database for that. This is to avoid passing bools around
    and avoid accidentally changing the state of a variable.

    Args:
        post_id (str): Reddit post ID
        post_in_database (bool): Whether the post is found in the database
        needs_routine_per_requirements (bool): Whether the post requires a routine per the rules
        has_routine (bool): Whether the post has a routine already
        case_closed (bool): Whether or not we're still checking this post
        reminded_utc (int): TODO
        removed_utc (int): TODO
        reported_utc (int): TODO
    """

    post_id: str
    post_in_database: bool
    needs_routine_per_requirements: bool
    has_routine: bool
    case_closed: bool
    reminded_utc: int
    removed_utc: int
    reported_utc: int


@dataclass
class RoutineErrors:
    comment: Optional[str]
    avoiding_routine: Optional[bool]
    too_short: Optional[bool]

    def is_better_than(self, other: "RoutineErrors") -> bool:
        """Return true if the current (self) object is better than the other object.

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
        if not self.comment:
            return "Missing routine; no comments from OP at all."
        if self.avoiding_routine and self.too_short:
            return "OP may be saying they have no routine & all comments are too short."
        elif self.avoiding_routine and not self.too_short:
            return "OP may be saying they have no routine. Please check!"
        else:
            return "OP's routine comment is too short. Please check!"


class RoutineChecker(BotAction):
    _params: RoutineCheckerParams
    _subreddit: Subreddit
    _db: sqlite3.Cursor
    _DB_NAME: str = "routine_checker_db"
    _DB_TABLE_NAME: str = "post_history"
    _WIKI_CONFIG_PAGE: str = "routine_checker_config"

    def __init__(
        self,
        subreddit: Subreddit,
        db: sqlite3.Cursor,
    ) -> None:
        self._subreddit = subreddit

        # Set up the db table for this bot action, within the given db
        self._db = self._set_up_db(db, self._DB_TABLE_NAME)
        # db_conn = sqlite3.connect(db_name)  # TODO this is how to get db (input to this method)
        # db = db_conn.cursor()

        # Get the parameters and make sure they're ok to use
        params = self._get_config_from_wiki(self._WIKI_CONFIG_PAGE)
        self._validate_config(params)
        self._params = RoutineCheckerParams(**params)
        self._validate_flair_messages(
            self._params.reminder_messages_by_flair, self._params.flair_to_check
        )
        logger.info(f"Config loaded and parsed: {self._params}")

        # TODO check to make sure we have messages set for all the flairs!
        # Each flair in flair_to_check should have a key in reminder_messages_by_flair
        # This will help catch errors early - AKA at the time you add this action to the bot

    def run(self) -> None:
        logger.debug("Running RoutineChecker!")

        posts = get_new_subreddit_posts(self._subreddit, self._params.max_posts)
        for post in posts:
            post_state = self._check_post(post)

            # Case closed already? keep going
            if post_state.case_closed:
                continue

            # See if we need to remind/report/remove
            new_post_state = self._remind_report_remove(post, post_state)

            # Update the database with new info about whether we took action
            self._update_db(post_state, new_post_state)

    def _validate_config(self, config: Dict[str, Any]) -> None:
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

        # # Example config dictionary
        # config_dict = {
        #     "flair_to_check": ["Routine", None],
        #     "remind_after_mins": 60,
        #     "remove_after_mins": None,
        #     "report_after_mins": 120,
        #     "keywords": ["routine", "skincare"],
        #     "min_routine_characters": 10,
        #     "sidestepping_phrases": ["no routine", "dont have a routine"],
        #     "max_posts": 100,
        #     "reminder_messages_by_flair": {"Routine": "Remember to follow your routine!"}
        # }

        # try:
        #     validate_config(config_dict)
        #     print("Config validation successful.")
        # except (ValueError, TypeError) as e:
        #     print(f"Config validation failed: {e}")

    def _validate_flair_messages(
        self, flair_messages: Dict[str, str], flair_to_check: List[str]
    ) -> None:
        flair_to_check = set(flair_to_check)
        flair_with_messages = set(flair_messages.keys())
        assert flair_with_messages.issuperset(flair_to_check)  # TODO better message

    def _remind_report_remove(self, post: Submission, post_state: PostState) -> PostState:
        time_since_post_mins = time_elapsed_since_post(post)
        time_right_now = int(datetime.datetime.utcnow().timestamp())

        """elif needs_action and remind and reminder_due and sent_reminder_utc < 0 and not removal_due:
            logger.info("REMIND")
            # Send reminder if...
            # * The post needs an action (needs a routine and doesn't have one)
            # * AND the "remind" option is on (kwarg for this function)
            # * AND it's due for a reminder
            # * AND we haven't already sent a reminder
            # * AND it's not yet time to remove it
            print(f"This one gets a reminder: https://www.reddit.com/r/curlyhair/comments/{post.id}")
            if flair == "help":
                add_routine_reminder_comment(post, reminder_msg=reminder_msg_help_flair)
            elif flair in ["hair victory", "update"]:
                add_routine_reminder_comment(post, reminder_msg=reminder_msg_victory_flair)
            else:
                add_routine_reminder_comment(post, reminder_msg=reminder_msg_no_flair)
            sent_reminder_utc = (now - datetime.datetime(1970, 1, 1)).total_seconds()
        elif needs_action and remove and removal_due and removed_utc < 0 and sent_reminder_utc > 0:
            logger.info("REMOVE")
            # Remove post if...
            # * The post needs an action (needs a routine and doesn't have one)
            # * AND the "remove" option is on (kwarg for this function)
            # * AND it hasn't already been removed
            # * AND we already sent a reminder (i.e. don't remove if it bugged out and never sent a reminder)
            removed_utc = (now - datetime.datetime(1970, 1, 1)).total_seconds()
            remove_post_for_routine(post, remove_msg=None)
        elif needs_action and report and removal_due and reported_utc < 0:
            logger.info("REPORT")
            # Report post if...
            # * The post needs an action (needs a routine and doesn't have one)
            # * AND the "report" option is on (kwarg for this function)
            # * AND it's due to be removed
            # * AND it hasn't already been reported
            
            if time_since_post > datetime.timedelta(hours=8):
                # don't report super old stuff
                pass
            else:
                print("I'll report this one!")
                reported_utc = (now - datetime.datetime(1970, 1, 1)).total_seconds()
                if op_comment:
                    msg = ">1hr and *possibly* no routine. (OP commented but there's no \"routine\" keyword.) Please check!"
                else:
                    msg = ">1hr and no routine has been posted. (No comments from OP at all). Please check!"
                report_post_for_routine(post, report_msg=msg)   

        """

        # Remind
        reminded_utc = 0
        if self._params.remind_after_mins is not None:
            remind_time = self._params.remind_after_mins  # TODO handle None
            if post_state.reminded_utc == 0 and time_since_post_mins > remind_time:
                # Send reminder via sticky message
                sticky_msg = self._get_sticky_message_for_flair(post.link_flair_text)
                add_sticky_comment(post, sticky_msg)

                # Mark the time we sent the reminder (utc)
                reminded_utc = time_right_now
                logger.debug(
                    f"Sent reminder for this post {post.id} (elapsed time: {time_since_post_mins})"
                )
            else:
                logger.debug(
                    f"Didn't remind for this post {post.id} (elapsed time: {time_since_post_mins})"
                )

        # Report
        reported_utc = 0
        if self._params.report_after_mins is not None:
            report_time = self._params.report_after_mins
            remove_time = self._params.remove_after_mins
            if post_state.reported_utc == 0 and time_since_post_mins > report_time:
                report_msg = "TODO report message"  # TODO
                post.report(report_msg)
                reported_utc = time_right_now
                # if self._text_has_sidesteppers(post): change report message
                # otherwise look up previous report message and use that here
                # TODO
            # elif post_state.reported_utc == 0 and remove_time is not None and time_since_post_mins > remove_time:

        # Remove
        removed_utc = 0
        if self._params.remove_after_mins is not None:
            remove_time = self._params.remove_after_mins
            if post_state.removed_utc == 0 and time_since_post_mins > remove_time:
                post.mod.remove()
                removed_utc = time_right_now

        post_state = PostState(
            post_id=post_state.post_id,
            post_in_database=post_state.post_in_database,
            needs_routine_per_requirements=post_state.needs_routine_per_requirements,
            has_routine=post_state.has_routine,
            case_closed=post_state.case_closed,
            reminded_utc=reminded_utc,
            removed_utc=removed_utc,
            reported_utc=reported_utc,
        )
        return post_state

    def _get_sticky_message_for_flair(self, flair: Optional[str]) -> str:
        msg = self._params.reminder_messages_by_flair.get(flair)
        return msg

    def _get_post_state_from_database(self, post: Submission) -> PostState:
        db_posts = self._db.execute(
            f"""SELECT * FROM {self._DB_TABLE_NAME} WHERE id=? ORDER BY created_utc DESC""",
            (post.id,),
        ).fetchall()
        if len(db_posts) > 1:
            e = f"More than one post with this id ({post.id}) found in the database (table {self._DB_TABLE_NAME})."
            logger.error(e)
            raise ValueError(e)
        elif len(db_posts) == 0:
            logger.debug(f"Post {post.id} not found in database.")
            post_state = PostState(
                post_id=post.id,
                post_in_database=False,
                needs_routine_per_requirements=False,  # Not meaningful
                has_routine=False,  # Not meaningful
                case_closed=False,
                reminded_utc=0,
                removed_utc=0,
                reported_utc=0,
            )
            return post_state
        else:
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
                needs_routine_per_requirements=needs_routine,
                has_routine=has_routine,
                case_closed=case_closed,
                reminded_utc=reminded_utc,
                removed_utc=removed_utc,
                reported_utc=reported_utc,
            )

    def _check_post(self, post: Submission) -> PostState:
        # Get the previous database state, or initialize it
        db_post_state = self._get_post_state_from_database(post)  # TODO maybe don't return none
        if db_post_state is None:
            db_post_state = PostState(
                post.id,
                post_in_database=False,
                needs_routine_per_requirements=None,
                has_routine=False,
                reminded_utc=-1,
                removed_utc=-1,
                reported_utc=-1,
                case_closed=False,
            )

        # If we've already marked the "case" as closed, don't keep checking, just return
        if db_post_state.case_closed:
            return db_post_state

        # Check if the post is in the database already. If not, we'll add it (below)
        in_db = db_post_state.post_in_database

        # Check if the post needs a routine. Don't use db flag for this - flair could have changed!
        needs_routine = self._post_needs_routine(post)

        # Check if the post has a routine
        post_meets_reqs, errors = self._post_meets_requirements(post)
        has_routine = db_post_state.has_routine or post_meets_reqs
        case_closed = True if has_routine else db_post_state.case_closed

        # If they have the keywords but are trying to cheat, report it and keep checking
        if errors is not None and errors.avoiding_routine:
            post.report(errors.summarize_errors())

        # Check if we should close the case based on time elapsed
        time_window_to_check_post_elapsed = self._post_is_over_time_limit(post)
        case_closed = True if has_routine or time_window_to_check_post_elapsed else False

        # Create the post state and insert this post into the db if we need to
        post_state = PostState(
            post_id=post.id,
            post_in_database=True,
            needs_routine_per_requirements=needs_routine,
            has_routine=has_routine,
            case_closed=case_closed,
            reminded_utc=db_post_state.reminded_utc,
            removed_utc=db_post_state.removed_utc,
            reported_utc=db_post_state.reported_utc,
        )
        if not in_db:
            self._insert_db(post, post_state)
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
        # The post is too old overall
        if time_since_post > self._params.ignore_posts_over_age_hours / 60:
            return True
        else:
            return False

        # # Find the longest time from remind/remove/report
        # time_values = [
        #     time
        #     for time in [
        #         self._params.remind_after_mins,
        #         self._params.remove_after_mins,
        #         self._params.report_after_mins,
        #     ]
        #     if time is not None
        # ]
        # max_time_mins = max(time_values) if time_values else None
        # max_time_delta = datetime.timedelta(max_time_mins)
        # if time_since_post < max_time_delta.total_seconds() / 60:
        #     return False
        # else:
        #     return True

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
        logger.debug("Setting up database connections.")
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
                logger.info("Database already exists, no need to initialize.")
            else:
                logger.warning(f"Unknown OperationalError: {e}")
                raise
        return db

    def _update_db(self, db_post_state: PostState, post_state: PostState) -> None:
        update_table = f"UPDATE {self._DB_NAME}"
        where_id_is = f"WHERE id = {post_state.post_id}"
        if (
            post_state.needs_routine_per_requirements
            != db_post_state.needs_routine_per_requirements
        ):
            self._db.execute(f"""{update_table} SET needs_routine = ? {where_id_is}""")
        elif post_state.has_routine != db_post_state.has_routine:
            self._db.execute(
                f"""{update_table} SET has_routine = {post_state.has_routine} {where_id_is}"""
            )
        elif post_state.reminded_utc != db_post_state.reminded_utc:
            self._db.execute(
                f"""{update_table} SET reminded_utc = {post_state.reminded_utc} {where_id_is}"""
            )
        elif post_state.removed_utc != db_post_state.removed_utc:
            self._db.execute(
                f"""{update_table} SET removed_utc = {post_state.removed_utc} {where_id_is}"""
            )
        elif post_state.reported_utc != db_post_state.reported_utc:
            self._db.execute(
                f"""{update_table} SET reported_utc = {post_state.reported_utc} {where_id_is}"""
            )

    def _insert_db(self, post: Submission, post_state: PostState) -> None:
        row = (
            post_state.post_id,
            post.url,
            post.created,
            post_state.needs_routine_per_requirements,
            post_state.has_routine,
            post_state.reminded_utc,
            post_state.removed_utc,
            post_state.reported_utc,
            post_state.case_closed,
        )
        self._db.execute(
            f"""INSERT INTO {self._DB_TABLE_NAME}
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            row,
        )
        db_conn = self._db.connection
        db_conn.commit()

    def _post_meets_requirements(self, post: Submission) -> Tuple[bool, Optional[RoutineErrors]]:
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
        for k in self._params.keywords:
            if k in text:
                return True
        return False

    def _text_fulfills_min_length(self, text: str) -> bool:
        if (
            self._params.min_routine_characters > 0
            and self._params.min_routine_characters is not None
        ):
            return len(text) >= self._params.min_routine_characters
        else:
            return True

    def _text_has_sidesteppers(self, text: str) -> bool:
        for cheat in self._params.sidestepping_phrases:
            if cheat in text:
                return True
        return False
