import datetime
import logging
from unittest.mock import MagicMock, patch

import praw
import pytest
from pytest import LogCaptureFixture, MonkeyPatch

from curlbot_v2 import __version__
from curlbot_v2.actions import RoutineChecker
from curlbot_v2.actions._routine_checker import PostState, RoutineCheckerParams, RoutineErrors

logger = logging.getLogger(__name__)


def test_version():
    assert __version__ == "0.1.0"


# class MagicMockTime(MagicMock):
#     # utcnow.return_value: datetime.datetime

#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         # self. = now

#     def __le__(self, other):
#         if isinstance(other, datetime.datetime) or isinstance(other, datetime.timedelta):
#             return self.utcnow.return_value <= other
#         return MagicMock.__le__(self.utcnow.return_value, other)

#     def __ge__(self, other):
#         if isinstance(other, datetime.datetime) or isinstance(other, datetime.timedelta):
#             return self.utcnow.return_value >= other
#         return MagicMock.__ge__(self.utcnow.return_value, other)

#     def __gt__(self, other):
#         if isinstance(other, datetime.datetime) or isinstance(other, datetime.timedelta):
#             return self.utcnow.return_value > other
#         return MagicMock.__gt__(self.utcnow.return_value, other)

#     def __lt__(self, other):
#         if isinstance(other, datetime.datetime) or isinstance(other, datetime.timedelta):
#             logger.debug("here")
#             print("here")
#             return self.utcnow.return_value < other
#         return MagicMock.__lt__(self.utcnow.return_value, other)


class TestRoutineChecker:
    @pytest.fixture
    def mock_reddit(self):
        return MagicMock()

    @pytest.fixture
    def mock_subreddit(self):
        subreddit = MagicMock()
        subreddit.flair.link_templates = [{"type": "LINK_FLAIR", "text": "help"}]

        yaml_content = """
        flair_to_check: ["help"]
        remind_after_mins: 10
        remove_after_mins: 60
        report_after_mins: 60
        keywords: ["routine", "s2c", "sotc", "I used", "prayer hands", "praying hands", "air dry", "diffuse", "plop", "shampoo with", "condition with"]
        min_routine_characters: 25
        sidestepping_phrases: ["don't have a routine", "no routine", "dont have a routine"]
        max_posts: 100
        reminder_messages_by_flair: {"help": "temp",}
        """
        subreddit.wiki.__getitem__().content_md = yaml_content

        return subreddit

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.fixture
    def mock_submission(self):
        submission = MagicMock()
        submission.id = "dummy_post_id"
        submission.link_flair_text = "help"
        submission.url = "dummy_url.jpg"
        return submission

    @pytest.fixture
    def routine_checker(self, mock_subreddit: MagicMock, mock_db: MagicMock):
        return RoutineChecker(mock_subreddit, mock_db)

    def test_correct_init_for_routine_checker(
        self, caplog: LogCaptureFixture, routine_checker: RoutineChecker
    ):
        caplog.set_level(logging.DEBUG)
        print(routine_checker._subreddit)

    def test_post_needs_routine_with_flair(
        self,
        caplog: LogCaptureFixture,
        routine_checker: RoutineChecker,
        mock_submission: MagicMock,
    ):
        caplog.set_level(logging.DEBUG)
        assert routine_checker._post_needs_routine(mock_submission)

    def test_post_needs_routine_without_flair(
        self, routine_checker: RoutineChecker, mock_submission: MagicMock
    ):
        mock_submission.link_flair_text = "Other Flair"
        assert not routine_checker._post_needs_routine(mock_submission)

    # def test_time_elapsed_since_post(self):
    #     mock_submission = MagicMock(created_utc=1000)
    #     current_time = 2000
    #     elapsed_time = time_elapsed_since_post(mock_submission, current_time)
    #     assert elapsed_time == timedelta(seconds=1000)

    # def test_post_is_an_image_with_image(self):
    #     mock_submission = MagicMock()
    #     mock_submission.post_hint = "image"
    #     assert post_is_an_image(mock_submission)

    # def test_post_is_an_image_without_image(self):
    #     mock_submission = MagicMock()
    #     mock_submission.post_hint = "link"
    #     assert not post_is_an_image(mock_submission)

    # def test_get_post_state_from_database_post_not_found(
    #     self, routine_checker, mock_submission, mock_db
    # ):
    #     mock_db.execute.return_value.fetchall.return_value = []
    #     post_state = routine_checker._get_post_state_from_database(mock_submission)
    #     assert post_state.post_id == "post_id"
    #     assert not post_state.post_in_database
    #     assert not post_state.needs_routine_per_requirements
    #     assert not post_state.has_routine
    #     assert post_state.case_open
    #     assert post_state.reminded_utc == 0
    #     assert post_state.removed_utc == 0
    #     assert post_state.reported_utc == 0

    # def test_get_post_state_from_database_post_found(
    #     self, routine_checker, mock_submission, mock_db
    # ):
    #     mock_db.execute.return_value.fetchall.return_value = [
    #         (
    #             "post_id",
    #             "post_url",
    #             int((datetime.now() - timedelta(minutes=10)).timestamp()),  # created 10 mins ago
    #             1,  # needs_routine
    #             0,  # has_routine
    #             int(
    #                 (datetime.now() - timedelta(minutes=5)).timestamp()
    #             ),  # reminder sent 5 mins ago
    #             int((datetime.now() - timedelta(minutes=3)).timestamp()),  # removed 3 mins ago
    #             int((datetime.now() - timedelta(minutes=2)).timestamp()),  # reported 2 mins ago
    #             1,  # case_open
    #         )
    #     ]
    #     post_state = routine_checker._get_post_state_from_database(mock_submission)
    #     assert post_state.post_id == "post_id"
    #     assert post_state.post_in_database
    #     assert post_state.needs_routine_per_requirements
    #     assert not post_state.has_routine
    #     assert post_state.case_open
    #     assert post_state.reminded_utc > 0
    #     assert post_state.removed_utc > 0
    #     assert post_state.reported_utc > 0

    # def test_get_post_state_from_database_multiple_posts_found(
    #     self, routine_checker, mock_submission, mock_db
    # ):
    #     mock_db.execute.return_value.fetchall.return_value = [
    #         (
    #             "post_id",
    #             "post_url",
    #             int((datetime.now() - timedelta(minutes=10)).timestamp()),  # created 10 mins ago
    #             1,  # needs_routine
    #             0,  # has_routine
    #             int(
    #                 (datetime.now() - timedelta(minutes=5)).timestamp()
    #             ),  # reminder sent 5 mins ago
    #             int((datetime.now() - timedelta(minutes=3)).timestamp()),  # removed 3 mins ago
    #             int((datetime.now() - timedelta(minutes=2)).timestamp()),  # reported 2 mins ago
    #             1,  # case_open
    #         ),
    #         (
    #             "post_id",
    #             "post_url",
    #             int((datetime.now() - timedelta(minutes=20)).timestamp()),  # created 20 mins ago
    #             0,  # needs_routine
    #             1,  # has_routine
    #             int(
    #                 (datetime.now() - timedelta(minutes=15)).timestamp()
    #             ),  # reminder sent 15 mins ago
    #             int((datetime.now() - timedelta(minutes=12)).timestamp()),  # removed 12 mins ago
    #             int((datetime.now() - timedelta(minutes=10)).timestamp()),  # reported 10 mins ago
    #             0,  # case_open
    #         ),
    #     ]
    #     with pytest.raises(ValueError):
    #         routine_checker._get_post_state_from_database(mock_submission)

    @patch("curlbot_v2.actions._routine_checker.time_elapsed_since_post", return_value=11)
    def test_remind_report_remove_case_reminder_due(
        self,
        monkeypatch: MonkeyPatch,
        routine_checker: RoutineChecker,
        caplog: LogCaptureFixture,
    ):
        caplog.set_level("DEBUG")
        # Set up the state of the db entry of the post before calling _remind_report_remove
        post_state = PostState(
            post_id="123",
            post_in_database=True,
            needs_routine_per_requirements=True,
            has_routine=False,
            stop_checking=False,
            reminded_utc=0,
            removed_utc=0,
            reported_utc=0,
        )
        # Mock utcnow so we can fix what "now" means to the code
        mock_utcnow = MagicMock()
        monkeypatch.setattr(datetime, "datetime", mock_utcnow)
        mock_utcnow.utcnow.return_value = datetime.datetime(2023, 8, 28, 1, 40, 27, 776743)
        post = MagicMock(created_utc=1693211427)

        # Call _remind_report_remove, which should only modify things related to reminding
        updated_post_state = routine_checker._remind_remove_report(post, post_state)
        assert updated_post_state.reminded_utc > 0  # Verify that we updated the reminded time
        assert post.reply.called  # Verify that reply was called

    @patch("curlbot_v2.actions._routine_checker.time_elapsed_since_post", return_value=9)
    def test_remind_report_remove_case_remind_not_due(
        self,
        monkeypatch,
        routine_checker: RoutineChecker,
        caplog: LogCaptureFixture,
    ):
        caplog.set_level("DEBUG")
        # Set up the state of the db entry of the post before calling _remind_report_remove
        post_state = PostState(
            post_id="123",
            post_in_database=True,
            needs_routine_per_requirements=True,
            has_routine=False,
            stop_checking=False,
            reminded_utc=0,
            removed_utc=0,
            reported_utc=0,
        )
        # Mock utcnow so we can fix what "now" means to the code
        mock_utcnow = MagicMock()
        monkeypatch.setattr(datetime, "datetime", mock_utcnow)
        mock_utcnow.utcnow.return_value = datetime.datetime(2023, 8, 28, 1, 40, 27, 776743)
        post = MagicMock(created_utc=1693211427)

        # Call _remind_report_remove, which shouldn't modify anything in this case
        updated_post_state = routine_checker._remind_remove_report(post, post_state)
        assert not post.reply.called  # Verify that reply was not called
        assert updated_post_state.reminded_utc == 0  # Verify that we didn't update the time
        assert post_state == updated_post_state

    @patch("curlbot_v2.actions._routine_checker.time_elapsed_since_post", return_value=61)
    def test_remind_report_remove_case_reporting_due(
        self,
        monkeypatch: MonkeyPatch,
        routine_checker: RoutineChecker,
        caplog: LogCaptureFixture,
    ):
        caplog.set_level("DEBUG")
        # Set up the state of the db entry of the post before calling _remind_report_remove
        post_state = PostState(
            post_id="123",
            post_in_database=True,
            needs_routine_per_requirements=True,
            has_routine=False,
            stop_checking=False,
            reminded_utc=0,
            removed_utc=0,
            reported_utc=0,
        )
        # Mock utcnow so we can fix what "now" means to the code
        mock_utcnow = MagicMock()
        monkeypatch.setattr(datetime, "datetime", mock_utcnow)
        mock_utcnow.utcnow.return_value = datetime.datetime(2023, 8, 28, 1, 40, 27, 776743)
        post = MagicMock(created_utc=1693211427)

        # Call _remind_report_remove, which should only modify things related to reminding
        updated_post_state = routine_checker._remind_remove_report(post, post_state)
        assert updated_post_state.reported_utc > 0  # Verify that we updated the reported time
        assert post.report.called  # Verify that report was called

    @patch("curlbot_v2.actions._routine_checker.time_elapsed_since_post", return_value=9)
    def test_remind_report_remove_case_reporting_not_due(
        self,
        monkeypatch,
        routine_checker: RoutineChecker,
        caplog: LogCaptureFixture,
    ):
        caplog.set_level("DEBUG")
        # Set up the state of the db entry of the post before calling _remind_report_remove
        post_state = PostState(
            post_id="123",
            post_in_database=True,
            needs_routine_per_requirements=True,
            has_routine=False,
            stop_checking=False,
            reminded_utc=0,
            removed_utc=0,
            reported_utc=0,
        )
        # Mock utcnow so we can fix what "now" means to the code
        mock_utcnow = MagicMock()
        monkeypatch.setattr(datetime, "datetime", mock_utcnow)
        mock_utcnow.utcnow.return_value = datetime.datetime(2023, 8, 28, 1, 40, 27, 776743)
        post = MagicMock(created_utc=1693211427)

        updated_post_state = routine_checker._remind_remove_report(post, post_state)
        assert not post.report.called  # Verify that report was not called
        assert updated_post_state.reported_utc == 0  # Verify that we didn't update the time

    @patch("curlbot_v2.actions._routine_checker.time_elapsed_since_post", return_value=61)
    def test_remind_report_remove_case_removal_due_reminder_sent(
        self,
        monkeypatch: MonkeyPatch,
        routine_checker: RoutineChecker,
        caplog: LogCaptureFixture,
    ):
        caplog.set_level("DEBUG")
        # Set up the state of the db entry of the post before calling _remind_report_remove
        post_state = PostState(
            post_id="123",
            post_in_database=True,
            needs_routine_per_requirements=True,
            has_routine=False,
            stop_checking=False,
            reminded_utc=123,  # just has to be > 0 to emulate having already sent a reminder
            removed_utc=0,
            reported_utc=0,
        )
        # Mock utcnow so we can fix what "now" means to the code
        mock_utcnow = MagicMock()
        monkeypatch.setattr(datetime, "datetime", mock_utcnow)
        mock_utcnow.utcnow.return_value = datetime.datetime(2023, 8, 28, 1, 40, 27, 776743)
        post = MagicMock(created_utc=1693211427)

        # Call _remind_report_remove, which should only modify things related to reminding
        updated_post_state = routine_checker._remind_remove_report(post, post_state)
        logger.debug(f"{updated_post_state=}")
        assert updated_post_state.removed_utc > 0  # Verify that we updated the removal time
        assert post.mod.remove.called  # Verify that remove was called

    @patch("curlbot_v2.actions._routine_checker.time_elapsed_since_post", return_value=61)
    def test_remind_report_remove_case_removal_due_reminders_off(
        self,
        monkeypatch: MonkeyPatch,
        routine_checker: RoutineChecker,
        caplog: LogCaptureFixture,
    ):
        caplog.set_level("DEBUG")
        # Set up the state of the db entry of the post before calling _remind_report_remove
        post_state = PostState(
            post_id="123",
            post_in_database=True,
            needs_routine_per_requirements=True,
            has_routine=False,
            stop_checking=False,
            reminded_utc=0,
            removed_utc=0,
            reported_utc=0,
        )
        # Turn off reminder
        params = routine_checker._params.__dict__
        params["remind_after_mins"] = None
        routine_checker._params = RoutineCheckerParams(**params)
        # Mock utcnow so we can fix what "now" means to the code
        mock_utcnow = MagicMock()
        monkeypatch.setattr(datetime, "datetime", mock_utcnow)
        mock_utcnow.utcnow.return_value = datetime.datetime(2023, 8, 28, 1, 40, 27, 776743)
        post = MagicMock(created_utc=1693211427)

        # Call _remind_report_remove, which should only modify things related to reminding
        updated_post_state = routine_checker._remind_remove_report(post, post_state)
        logger.debug(f"{updated_post_state=}")
        assert updated_post_state.removed_utc > 0  # Verify that we updated the removal time
        assert post.mod.remove.called  # Verify that remove was called

    @patch("curlbot_v2.actions._routine_checker.time_elapsed_since_post", return_value=9)
    def test_remind_report_remove_case_removal_not_due(
        self,
        monkeypatch,
        routine_checker: RoutineChecker,
        caplog: LogCaptureFixture,
    ):
        caplog.set_level("DEBUG")
        # Set up the state of the db entry of the post before calling _remind_report_remove
        post_state = PostState(
            post_id="123",
            post_in_database=True,
            needs_routine_per_requirements=True,
            has_routine=False,
            stop_checking=False,
            reminded_utc=0,
            removed_utc=0,
            reported_utc=0,
        )
        # Mock utcnow so we can fix what "now" means to the code
        mock_utcnow = MagicMock()
        monkeypatch.setattr(datetime, "datetime", mock_utcnow)
        mock_utcnow.utcnow.return_value = datetime.datetime(2023, 8, 28, 1, 40, 27, 776743)
        post = MagicMock(created_utc=1693211427)

        updated_post_state = routine_checker._remind_remove_report(post, post_state)
        assert not post.mod.remove.called  # Verify that remove was not called
        assert updated_post_state.removed_utc == 0  # Verify that we didn't update the time

    # Test for no actions when not due
    @patch("curlbot_v2.actions._routine_checker.time_elapsed_since_post", return_value=5)
    def test__remind_report_remove_no_actions_due(
        self, monkeypatch: MonkeyPatch, routine_checker: RoutineChecker
    ):
        mock_utcnow = MagicMock()
        monkeypatch.setattr(datetime, "datetime", mock_utcnow)
        mock_utcnow.utcnow.return_value = datetime.datetime(2023, 8, 28, 1, 40, 27, 776743)
        post = MagicMock(created_utc=1693211427)

        post_state = post_state = PostState(
            post_id="123",
            post_in_database=True,
            needs_routine_per_requirements=True,
            has_routine=False,
            stop_checking=False,
            reminded_utc=0,
            removed_utc=0,
            reported_utc=0,
        )

        updated_post_state = routine_checker._remind_remove_report(post, post_state)

        assert updated_post_state == post_state  # Should remain unchanged
        assert not post.reply.called  # Should not call reply

    # TODO test case where stop_checking is True (doesn't matter what other params are set)


class TestRoutineErrors:
    def test_is_better_than(self):
        # No comment vs. has comment
        assert RoutineErrors(
            comment="comment", avoiding_routine=True, too_short=True
        ).is_better_than(RoutineErrors(comment=None, avoiding_routine=None, too_short=None))

        # Equal number of errors
        assert not RoutineErrors(
            comment="comment", avoiding_routine=True, too_short=False
        ).is_better_than(RoutineErrors(comment="comment", avoiding_routine=False, too_short=True))
        # Equal number of errors, flipped
        assert not RoutineErrors(
            comment="comment", avoiding_routine=False, too_short=True
        ).is_better_than(RoutineErrors(comment="comment", avoiding_routine=True, too_short=False))
        # Self has fewer errors
        assert RoutineErrors(
            comment="comment", avoiding_routine=True, too_short=False
        ).is_better_than(RoutineErrors(comment="comment", avoiding_routine=True, too_short=True))
        # Other has fewer errors
        assert not RoutineErrors(
            comment="comment", avoiding_routine=True, too_short=True
        ).is_better_than(RoutineErrors(comment="comment", avoiding_routine=True, too_short=False))
