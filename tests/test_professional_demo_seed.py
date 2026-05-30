from scripts.seed_professional_demo import build_professional_demo_sql


def test_professional_demo_seed_is_curated_and_non_destructive():
    sql = build_professional_demo_sql()

    assert "Curated professional demo data" in sql
    assert "INSERT IGNORE INTO Airline" in sql
    assert "'United'" in sql
    assert "'P0206'" not in sql
    assert "900000" in sql
    assert "synthetic00000@demo.local" in sql
