"""Tests for setup_wizard.py helper flows."""

from unittest.mock import patch

from codecks_cli import config, setup_wizard


class TestSetupDiscoverProjects:
    @patch("codecks_cli.setup_wizard.config.save_env_value")
    @patch("codecks_cli.setup_wizard._try_call")
    def test_no_projects_saves_empty_mapping(self, mock_try_call, mock_save):
        mock_try_call.return_value = {"deck": {"d1": {"id": "d1", "title": "Inbox"}}}
        setup_wizard._setup_discover_projects()
        mock_save.assert_called_once_with("CODECKS_PROJECTS", "")


class TestSetupDiscoverUser:
    @patch("codecks_cli.setup_wizard.config.save_env_value")
    @patch("codecks_cli.setup_wizard._try_call")
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
    @patch("codecks_cli.setup_wizard.config.save_env_value")
    @patch("builtins.input", return_value="")
    def test_skip_gdd_url(self, mock_input, mock_save):
        setup_wizard._setup_gdd_optional()
        mock_save.assert_not_called()

    @patch("codecks_cli.setup_wizard.config.save_env_value")
    @patch("builtins.input", return_value="https://docs.google.com/document/d/abc123/edit")
    def test_save_gdd_url(self, mock_input, mock_save):
        setup_wizard._setup_gdd_optional()
        mock_save.assert_called_once_with(
            "GDD_GOOGLE_DOC_URL",
            "https://docs.google.com/document/d/abc123/edit",
        )


class TestCmdSetupFastPath:
    @patch("codecks_cli.setup_wizard._setup_done")
    @patch("codecks_cli.setup_wizard._setup_gdd_optional")
    @patch("codecks_cli.setup_wizard._setup_discover_user")
    @patch("codecks_cli.setup_wizard._setup_discover_milestones")
    @patch("codecks_cli.setup_wizard._setup_discover_projects")
    @patch("builtins.input", return_value="1")
    @patch("codecks_cli.setup_wizard._try_call")
    @patch("codecks_cli.setup_wizard.config.load_env")
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
            "CODECKS_TOKEN": "cdxut_id_secret",
        }
        mock_try_call.return_value = {
            "account": {"a1": {"name": "Acct"}},
            "project": {"p1": {"id": "p1"}},
        }
        setup_wizard.cmd_setup()
        mock_projects.assert_called_once()
        mock_milestones.assert_called_once()
        mock_user.assert_called_once()
        mock_gdd.assert_called_once()
        mock_done.assert_called_once()


class TestSetupDefaultDeck:
    DECKS = {
        "deck": {
            "d1": {"id": "d1", "title": "Backlog", "projectId": "p1"},
            "d2": {"id": "d2", "title": "Backlog", "projectId": "p2"},
            "d3": {"id": "d3", "title": "Inbox", "projectId": "p1"},
        }
    }

    @patch("codecks_cli.setup_wizard.config.save_env_value")
    @patch("codecks_cli.setup_wizard.load_project_names", return_value={"p1": "Game", "p2": "Web"})
    @patch("codecks_cli.setup_wizard._try_call")
    def test_same_named_decks_are_distinct_and_id_is_saved(
        self, mock_try_call, _mock_projects, mock_save, monkeypatch
    ):
        mock_try_call.return_value = self.DECKS
        labels = [label for label, _ in setup_wizard._deck_choices()]
        assert labels == ["Backlog (Game)", "Backlog (Web)", "Inbox (Game)"]
        monkeypatch.setattr("builtins.input", lambda _prompt: "2")
        setup_wizard._setup_default_deck()
        mock_save.assert_called_once_with("CODECKS_DEFAULT_DECK", "d2")
        assert config.DEFAULT_DECK == "d2"

    @patch("codecks_cli.setup_wizard.config.save_env_value")
    @patch("codecks_cli.setup_wizard.load_project_names", return_value={})
    @patch("codecks_cli.setup_wizard._try_call")
    def test_enter_picks_inbox(self, mock_try_call, _mock_projects, mock_save, monkeypatch):
        mock_try_call.return_value = self.DECKS
        monkeypatch.setattr("builtins.input", lambda _prompt: "")
        setup_wizard._setup_default_deck()
        mock_save.assert_called_once_with("CODECKS_DEFAULT_DECK", "d3")

    @patch("codecks_cli.setup_wizard._setup_done")
    @patch("codecks_cli.setup_wizard._setup_default_deck")
    @patch("builtins.input", return_value="4")
    @patch("codecks_cli.setup_wizard._try_call")
    @patch("codecks_cli.setup_wizard.config.load_env")
    def test_menu_option_4_changes_default_deck(
        self, mock_load_env, mock_try_call, _mock_input, mock_deck, mock_done
    ):
        mock_load_env.return_value = {"CODECKS_ACCOUNT": "acct", "CODECKS_TOKEN": "cdxut_a_b"}
        mock_try_call.return_value = {"account": {"a1": {"name": "Acct"}}}
        setup_wizard.cmd_setup()
        mock_deck.assert_called_once()
        mock_done.assert_called_once()
