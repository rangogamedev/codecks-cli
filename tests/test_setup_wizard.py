"""Tests for setup_wizard.py helper flows."""

from unittest.mock import patch

import config
import setup_wizard


class TestSetupDiscoverProjects:
    @patch("setup_wizard.config.save_env_value")
    @patch("setup_wizard._try_call")
    def test_no_projects_saves_empty_mapping(self, mock_try_call, mock_save):
        mock_try_call.return_value = {"deck": {"d1": {"id": "d1", "title": "Inbox"}}}
        setup_wizard._setup_discover_projects()
        mock_save.assert_called_once_with("CODECKS_PROJECTS", "")


class TestSetupDiscoverUser:
    @patch("setup_wizard.config.save_env_value")
    @patch("setup_wizard._try_call")
    def test_single_user_is_saved(self, mock_try_call, mock_save):
        mock_try_call.return_value = {
            "accountRole": {
                "r1": {"userId": "u1", "role": "owner"},
            },
            "user": {
                "u1": {"name": "Thomas"},
            },
        }
        setup_wizard._setup_discover_user()
        mock_save.assert_called_once_with("CODECKS_USER_ID", "u1")
        assert config.USER_ID == "u1"


class TestSetupGddOptional:
    @patch("setup_wizard.config.save_env_value")
    @patch("builtins.input", return_value="")
    def test_skip_gdd_url(self, mock_input, mock_save):
        setup_wizard._setup_gdd_optional()
        mock_save.assert_not_called()

    @patch("setup_wizard.config.save_env_value")
    @patch("builtins.input", return_value="https://docs.google.com/document/d/abc123/edit")
    def test_save_gdd_url(self, mock_input, mock_save):
        setup_wizard._setup_gdd_optional()
        mock_save.assert_called_once_with(
            "GDD_GOOGLE_DOC_URL",
            "https://docs.google.com/document/d/abc123/edit",
        )


class TestCmdSetupFastPath:
    @patch("setup_wizard._setup_done")
    @patch("setup_wizard._setup_gdd_optional")
    @patch("setup_wizard._setup_discover_user")
    @patch("setup_wizard._setup_discover_milestones")
    @patch("setup_wizard._setup_discover_projects")
    @patch("builtins.input", return_value="1")
    @patch("setup_wizard._try_call")
    @patch("setup_wizard.config.load_env")
    def test_existing_valid_config_refresh_path(
        self,
        mock_load_env,
        mock_try_call,
        mock_input,
        mock_projects,
        mock_milestones,
        mock_user,
        mock_gdd,
        mock_done,
    ):
        mock_load_env.return_value = {
            "CODECKS_ACCOUNT": "acct",
            "CODECKS_TOKEN": "token",
        }
        mock_try_call.return_value = {"account": {"a1": {"name": "Acct"}}}
        setup_wizard.cmd_setup()
        mock_projects.assert_called_once()
        mock_milestones.assert_called_once()
        mock_user.assert_called_once()
        mock_gdd.assert_called_once()
        mock_done.assert_called_once()
