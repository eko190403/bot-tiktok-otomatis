import types
import time

import firebase_connector


def test_cleanup_old_drafts_executes_deletes(monkeypatch):
    # Prepare mock DB that returns two draft docs to be deleted
    ids = ["old1", "old2"]

    class BatchCollector:
        def __init__(self):
            self.deleted = []

        def delete(self, ref):
            # ref is expected to have an 'id' attribute
            self.deleted.append(ref.id)

        def commit(self):
            pass

    class MockDraftsCollection:
        def __init__(self, ids):
            self._ids = ids

        def where(self, *args, **kwargs):
            # ignore filter args for test
            return self

        def stream(self):
            for i in self._ids:
                yield types.SimpleNamespace(reference=types.SimpleNamespace(id=i))

    class MockDB:
        def __init__(self, ids):
            self._drafts = MockDraftsCollection(ids)
            self._batch = BatchCollector()

        def collection(self, name):
            if name == "drafts":
                return self._drafts
            raise KeyError(name)

        def batch(self):
            return self._batch

    mock_db = MockDB(ids)
    monkeypatch.setattr(firebase_connector, 'is_firebase_enabled', True)
    monkeypatch.setattr(firebase_connector, 'db', mock_db)

    # Call cleanup; days value ignored by mock where()
    firebase_connector.cleanup_old_drafts(days=1)

    assert sorted(mock_db._batch.deleted) == sorted(ids)


def test_get_top_themes_aggregates_views(monkeypatch):
    # Create some theme_stats docs
    docs = [
        {"theme": "A", "views": 10, "likes": 1},
        {"theme": "A", "views": 5, "likes": 0},
        {"theme": "B", "views": 20, "likes": 2},
    ]

    class MockThemeCollection:
        def __init__(self, docs):
            self._docs = docs

        def stream(self):
            for d in self._docs:
                yield types.SimpleNamespace(to_dict=lambda d=d: d)

    class MockDB:
        def __init__(self, docs):
            self._theme = MockThemeCollection(docs)

        def collection(self, name):
            if name == 'theme_stats':
                return self._theme
            raise KeyError(name)

    mock_db = MockDB(docs)
    monkeypatch.setattr(firebase_connector, 'is_firebase_enabled', True)
    monkeypatch.setattr(firebase_connector, 'db', mock_db)

    top = firebase_connector.get_top_themes(limit=2)
    assert isinstance(top, list)
    # Top first should be theme B with 20 views
    assert top[0]['theme'] == 'B' and top[0]['views'] == 20
    # Theme A aggregated views should be 15
    assert any(t['theme'] == 'A' and t['views'] == 15 for t in top)
