from src.price_watch import CatalogObservation, price_decision


def test_changed_catalog_price_requires_review():
    observation = CatalogObservation("Acme CLI", 29.0, 25.0)

    assert price_decision(observation) == "review"
    assert price_decision(CatalogObservation("Acme CLI", 25.0, 25.0)) == "unchanged"
    assert price_decision(CatalogObservation("Acme CLI", 25.0, None)) == "baseline"
