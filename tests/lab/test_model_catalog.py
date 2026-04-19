from app.lab.services.model_catalog import CatalogEntry, ModelCatalog


def test_catalog_load_bundled_seed():
    catalog = ModelCatalog.bundled()
    assert len(catalog.entries) > 0
    first = catalog.entries[0]
    assert isinstance(first, CatalogEntry)
    assert first.name
    assert first.params_b > 0
    assert first.best_quant


def test_catalog_filter_use_case():
    catalog = ModelCatalog.bundled()
    coding = catalog.filter(use_case="coding")
    assert all("coding" in entry.use_case.lower() or entry.use_case == "coding" for entry in coding)


def test_catalog_search_name():
    catalog = ModelCatalog.bundled()
    hits = catalog.filter(search="qwen")
    assert any("qwen" in entry.name.lower() for entry in hits)
