"""A verification command must not silently import into live or another project."""
import pytest

from scripts.verify_demo_import import dedicated_demo_url


PROJECT = "abcdefghijklmnopqrst"
URL = f"postgresql://postgres.{PROJECT}:secret@aws-0-sa-east-1.pooler.supabase.com:5432/postgres?sslmode=require"


def test_dedicated_destination_uses_demo_only():
    assert dedicated_demo_url({"DEMO_DATABASE_URL": URL, "DATABASE_URL": "live"}, PROJECT) == URL


@pytest.mark.parametrize("settings,project", [
    ({"DATABASE_URL": URL}, PROJECT),
    ({"DEMO_DATABASE_URL": URL, "DATABASE_URL": URL}, PROJECT),
    ({"DEMO_DATABASE_URL": URL}, "zyxwvutsrqponmlkjihg"),
    ({"DEMO_DATABASE_URL": URL}, "invalid"),
    ({"DEMO_DATABASE_URL": URL.replace(":5432/", ":6543/")}, PROJECT),
    ({"DEMO_DATABASE_URL": URL.replace("sslmode=require", "sslmode=disable")}, PROJECT),
    ({"DEMO_DATABASE_URL": URL + "&host=other.invalid"}, PROJECT),
    ({"DEMO_DATABASE_URL": URL + "&sslmode=require"}, PROJECT),
    ({"DEMO_DATABASE_URL": URL.replace(".supabase.com", ".supabase.com.invalid")}, PROJECT),
])
def test_dedicated_destination_rejects_misdirection(settings, project):
    with pytest.raises(ValueError):
        dedicated_demo_url(settings, project)
