"""Tests for setup_wizard.py helper flows."""

from unittest.mock import patch

from codecks_cli import config, setup_wizard


class TestSetupDiscoverProjects:
    @patch("codecks_cli.setup_wizard.config.save_env_value")
    @patch("codecks_cli.setup_wizard._try_call", return_value={})
    def test_empty_discovery_preserves_configuration(self, _query, save):
        setup_wizard._setup_discover_projects()
        save.assert_not_called()

    @patch("codecks_cli.setup_wizard.config.save_env_value")
    @patch("builtins.input", return_value="")
    @patch(
        "codecks_cli.setup_wizard._try_call", return_value={"p1": {"id": "p1", "name": "Current"}}
    )
    def test_default_uses_api_name_without_saving_it(self, _query, _input, save, capsys):
        setup_wizard._setup_discover_projects()
        save.assert_not_called()
        assert "Current [p1]" in capsys.readouterr().out

    @patch("codecks_cli.setup_wizard.config.save_env_value")
    @patch("builtins.input", side_effect=["y", "My, Alias=Name"])
    @patch(
        "codecks_cli.setup_wizard._try_call", return_value={"p1": {"id": "p1", "name": "Current"}}
    )
    def test_explicit_alias_is_saved_as_json(self, _query, _input, save):
        setup_wizard._setup_discover_projects()
        save.assert_called_once_with("CODECKS_PROJECT_ALIASES", '{"p1": "My, Alias=Name"}')
        assert setup_wizard._load_project_aliases() == {"p1": "My, Alias=Name"}

    @patch("codecks_cli.setup_wizard.config.save_env_value")
    @patch("builtins.input", side_effect=["y", "-"])
    @patch(
        "codecks_cli.setup_wizard._try_call", return_value={"p1": {"id": "p1", "name": "Renamed"}}
    )
    def test_reset_preserves_other_aliases_and_legacy_mapping(
        self, _query, _input, save, monkeypatch
    ):
        monkeypatch.setattr(
            config,
            "env",
            {
                "CODECKS_PROJECT_ALIASES": '{"p1": "Local", "p2": "Other"}',
                "CODECKS_PROJECTS": "p1=Old",
            },
        )
        setup_wizard._setup_discover_projects()
        save.assert_called_once_with("CODECKS_PROJECT_ALIASES", '{"p2": "Other"}')
        assert config.env["CODECKS_PROJECTS"] == "p1=Old"

    @patch("codecks_cli.setup_wizard.config.save_env_value")
    @patch("builtins.input", side_effect=["y", ""])
    @patch(
        "codecks_cli.setup_wizard._try_call", return_value={"p1": {"id": "p1", "name": "Renamed"}}
    )
    def test_enter_keeps_alias(self, _query, _input, save, monkeypatch):
        monkeypatch.setattr(config, "env", {"CODECKS_PROJECT_ALIASES": '{"p1": "Local"}'})
        setup_wizard._setup_discover_projects()
        save.assert_not_called()


class TestSetupDiscoverUser:
    @patch("codecks_cli.setup_wizard.config.save_env_value")
    @patch("codecks_cli.setup_wizard._try_call")
    def test_personal_token_skips_user_picker(self, mock_try_call, mock_save, monkeypatch):
        # A picker defaulting to "1" saved the first member, maybe a teammate.
        monkeypatch.setattr(config, "SESSION_TOKEN", "cdxut_x")
        setup_wizard._setup_discover_user()
        mock_try_call.assert_not_called()
        mock_save.assert_not_called()

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


@patch("codecks_cli.setup_wizard._setup_done")
@patch("codecks_cli.setup_wizard._setup_discover_projects")
@patch("builtins.input", return_value="5")
@patch("codecks_cli.setup_wizard._try_call", return_value={"account": {"a1": {"name": "Account"}}})
@patch(
    "codecks_cli.setup_wizard.config.load_env",
    return_value={"CODECKS_ACCOUNT": "acct", "CODECKS_TOKEN": "cdxut_a_b"},
)
def test_returning_user_can_edit_only_project_aliases(_load, _query, _input, projects, done):
    setup_wizard.cmd_setup()
    projects.assert_called_once()
    done.assert_called_once()
