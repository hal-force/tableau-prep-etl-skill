"""Tests for _creds_suggestions.suggestions_for.

The suggestion lists themselves are static help text — the interesting
contract is:
- Each platform returns a non-empty list.
- The 'recommended' entry (if any) sorts first.
- Unknown platforms fall back to Linux's list.
- StorageOption round-trips through .to_dict() cleanly (used by the
  orchestrator when serializing to AskUserQuestion payloads).
"""
from __future__ import annotations

from skill.scripts._creds_suggestions import StorageOption, suggestions_for


class TestSuggestionsFor:
    def test_darwin_has_keychain_first(self):
        opts = suggestions_for("Darwin")
        assert opts
        assert opts[0].recommended is True
        assert "Keychain" in opts[0].label

    def test_windows_has_credential_manager_first(self):
        opts = suggestions_for("Windows")
        assert opts
        assert opts[0].recommended is True
        assert "Credential Manager" in opts[0].label

    def test_linux_returns_non_empty(self):
        opts = suggestions_for("Linux")
        assert opts
        # Linux may or may not have secret-tool on the host, so we only
        # assert there IS a recommended entry (either GNOME Keyring or
        # direnv gets that flag depending on binary availability).
        assert any(o.recommended for o in opts)

    def test_unknown_platform_falls_back_to_linux(self):
        linux = suggestions_for("Linux")
        unknown = suggestions_for("Plan9")
        # Same labels in the same order — Linux is the generic fallback.
        assert [o.label for o in unknown] == [o.label for o in linux]

    def test_options_serialize_to_dict(self):
        opts = suggestions_for("Darwin")
        for o in opts:
            d = o.to_dict()
            assert set(d.keys()) == {"label", "description",
                                     "setup_commands", "recommended"}
            assert isinstance(d["setup_commands"], list)

    def test_recommended_sorts_first(self):
        for sysname in ("Darwin", "Linux", "Windows"):
            opts = suggestions_for(sysname)
            recommended_seen = False
            for o in opts:
                if o.recommended:
                    recommended_seen = True
                elif recommended_seen:
                    # Once we've passed the recommended block, no more
                    # recommended entries should appear.
                    assert not any(x.recommended for x in opts[opts.index(o):])
                    break


class TestStorageOption:
    def test_defaults(self):
        o = StorageOption(label="x", description="y")
        assert o.setup_commands == []
        assert o.recommended is False

    def test_to_dict_shape(self):
        o = StorageOption(label="x", description="y",
                          setup_commands=["cmd"], recommended=True)
        assert o.to_dict() == {
            "label": "x", "description": "y",
            "setup_commands": ["cmd"], "recommended": True,
        }
