"""Unit tests for ``get_policy_limits``, called directly (SCOPE Part 3).

Covers acceptance criteria AC-05 to AC-07 in docs/REQUIREMENTS.md.
"""

import pytest

from it_equipment.errors import UnknownRoleError

# REQUIREMENTS section 3: role -> item -> (max_quantity, replacement_years).
POLICY_TABLE = {
    "standard": {"laptop": (1, 4), "monitor": (1, 3), "headset": (1, 2), "keyboard": (1, 2)},
    "engineer": {"laptop": (1, 3), "monitor": (2, 3), "headset": (1, 2), "keyboard": (1, 2)},
    "manager": {"laptop": (1, 2), "monitor": (2, 3), "headset": (1, 2), "keyboard": (1, 2)},
    "contractor": {
        "laptop": (0, None),
        "monitor": (0, None),
        "headset": (1, 2),
        "keyboard": (1, 2),
    },
}


def _as_table(limits):
    return {row.item: (row.max_quantity, row.replacement_years) for row in limits.items}


def test_manager_column_matches_requirements(tools):
    """AC-05."""
    limits = tools.get_policy_limits("Manager")

    assert limits.role == "manager"
    assert _as_table(limits) == POLICY_TABLE["manager"]


def test_contractor_is_not_eligible_for_laptop_or_monitor(tools):
    """AC-06."""
    eligible = {row.item: row.eligible for row in tools.get_policy_limits("contractor").items}

    assert eligible == {"laptop": False, "monitor": False, "headset": True, "keyboard": True}


@pytest.mark.parametrize("role", ["intern", "", "   ", "managers"])
def test_unknown_role_raises(tools, role):
    """AC-07."""
    with pytest.raises(UnknownRoleError, match=r"^UNKNOWN_ROLE: "):
        tools.get_policy_limits(role)


@pytest.mark.parametrize("role", sorted(POLICY_TABLE))
def test_every_role_matches_the_policy_table(tools, role):
    assert _as_table(tools.get_policy_limits(role)) == POLICY_TABLE[role]


def test_items_follow_catalog_order(tools):
    items = [row.item for row in tools.get_policy_limits("engineer").items]

    assert items == ["laptop", "monitor", "headset", "keyboard"]


@pytest.mark.parametrize("raw", ["  ENGINEER ", "engineer\n", "Engineer"])
def test_role_case_and_surrounding_spaces_are_ignored(tools, raw):
    assert tools.get_policy_limits(raw).role == "engineer"
