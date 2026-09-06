import pytest

from tests.postgres import require_disposable_database_name


@pytest.mark.parametrize(
    "name",
    [
        "sot",
        "postgres",
        "template0",
        "template1",
        "sot_test_",
        "sot_test_application",
        "sot_test_" + "a" * 32 + ";DROP DATABASE sot",
    ],
)
def test_database_cleanup_guard_rejects_application_and_unowned_targets(
    name: str,
) -> None:
    with pytest.raises(ValueError, match="disposable"):
        require_disposable_database_name(name)


def test_database_cleanup_guard_accepts_only_generated_name_shape() -> None:
    assert (
        require_disposable_database_name("sot_test_0123456789abcdef0123456789abcdef")
        == "sot_test_0123456789abcdef0123456789abcdef"
    )
