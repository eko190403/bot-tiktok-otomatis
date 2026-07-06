import types
import time

import pytest

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import firebase_connector


class DummyDoc:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return self._data


class DummyCollection:
    def __init__(self, docs=None):
        self._docs = docs or []

    def add(self, data):
        # simulate Firestore add
        self._docs.append(data)

    def document(self, _id):
        # return a simple object with set and update
        coll = self

        class DocRef:
            def __init__(self, cid):
                self.id = cid

            def set(self, data):
                coll._docs.append({"id": self.id, **data})

            def update(self, data):
                # naive: search and update first match
                for d in coll._docs:
                    if isinstance(d, dict) and d.get("id") == self.id:
                        d.update(data)
                        return

            def get(self):
                for d in coll._docs:
                    if isinstance(d, dict) and d.get("id") == self.id:
                        return types.SimpleNamespace(exists=True, to_dict=lambda: d)
                return types.SimpleNamespace(exists=False)

        return DocRef(_id)

    def order_by(self, *args, **kwargs):
        # return an iterable of DummyDoc wrappers for testing
        return [DummyDoc(d) for d in self._docs]

    def limit(self, n):
        return self

    def stream(self):
        for d in self._docs:
            yield DummyDoc(d)


def test_get_recent_history_when_firestore_disabled(monkeypatch):
    # Force Firestore disabled
    monkeypatch.setattr(firebase_connector, 'is_firebase_enabled', False)
    monkeypatch.setattr(firebase_connector, 'db', None)
    res = firebase_connector.get_recent_history(limit=5)
    assert res == []


def test_save_and_get_history_with_mock_firestore(monkeypatch):
    # Prepare mock db and collection
    docs = [
        {"timestamp": int(time.time()), "hook": "h1", "story": "s1", "cta": "c1", "caption": "cap1"}
    ]
    mock_coll = DummyCollection(docs=list(docs))

    class MockDB:
        def collection(self, name):
            return mock_coll

    monkeypatch.setattr(firebase_connector, 'is_firebase_enabled', True)
    monkeypatch.setattr(firebase_connector, 'db', MockDB())

    # Save a new history item
    firebase_connector.save_to_history('hookX', 'storyX', 'ctaX', 'captionX')

    # Now get recent history
    recent = firebase_connector.get_recent_history(limit=5)
    assert isinstance(recent, list)
    # Should contain at least one item with keys
    assert all('hook' in r and 'story' in r and 'cta' in r for r in recent)
