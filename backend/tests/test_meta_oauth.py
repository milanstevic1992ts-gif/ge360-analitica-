import unittest
from unittest.mock import patch

from app import meta_oauth


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeAsyncClient:
    responses = []
    calls = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, params=None):
        self.__class__.calls.append((url, params))
        if not self.__class__.responses:
            raise AssertionError("Chiamata Graph API inattesa")
        return FakeResponse(self.__class__.responses.pop(0))


def fake_get(key, default=""):
    if key == "META_USER_ACCESS_TOKEN":
        return "user-token-for-tests"
    if key == "META_GRAPH_VERSION":
        return "v26.0"
    return default


class MetaPagesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        FakeAsyncClient.responses = []
        FakeAsyncClient.calls = []

    async def _list_pages(self):
        with patch.object(meta_oauth, "get", side_effect=fake_get), patch.object(
            meta_oauth.httpx, "AsyncClient", FakeAsyncClient
        ):
            return await meta_oauth.list_pages()

    async def test_paginates_me_accounts_and_never_exposes_access_token(self):
        FakeAsyncClient.responses = [
            {
                "data": [
                    {
                        "id": "2",
                        "name": "Beta",
                        "category": "Impresa",
                        "access_token": "page-secret-2",
                        "instagram_business_account": {
                            "id": "ig-2",
                            "username": "beta_ig",
                            "followers_count": 10,
                            "media_count": 4,
                        },
                    }
                ],
                "paging": {
                    "next": "https://graph.facebook.com/v26.0/me/accounts?after=cursor-1"
                },
            },
            {
                "data": [
                    {
                        "id": "1",
                        "name": "Alpha",
                        "category": "Servizi",
                        "access_token": "page-secret-1",
                    }
                ]
            },
        ]

        pages = await self._list_pages()

        self.assertEqual([page["id"] for page in pages], ["1", "2"])
        self.assertEqual(len(FakeAsyncClient.calls), 2)
        self.assertTrue(pages[1]["instagram_business_account"]["id"], "ig-2")
        self.assertTrue(pages[1]["instagram"]["connected"])
        for page in pages:
            self.assertNotIn("access_token", page)
            self.assertNotIn("page-secret", repr(page))

    async def test_uses_cursor_after_when_next_is_missing(self):
        FakeAsyncClient.responses = [
            {
                "data": [{"id": "1", "name": "Alpha"}],
                "paging": {"cursors": {"after": "cursor-after"}},
            },
            {
                "data": [{"id": "2", "name": "Beta"}],
            },
        ]

        pages = await self._list_pages()

        self.assertEqual(len(pages), 2)
        self.assertEqual(
            FakeAsyncClient.calls[1][1]["after"],
            "cursor-after",
        )

    async def test_deduplicates_pages_by_page_id(self):
        FakeAsyncClient.responses = [
            {
                "data": [{"id": "7", "name": "Pagina Originale"}],
                "paging": {"next": "https://graph.facebook.com/v26.0/me/accounts?after=next"},
            },
            {
                "data": [
                    {"id": "7", "name": "Duplicato da ignorare"},
                    {"id": "8", "name": "Seconda Pagina"},
                ]
            },
        ]

        pages = await self._list_pages()

        self.assertEqual(len(pages), 2)
        by_id = {page["id"]: page for page in pages}
        self.assertEqual(by_id["7"]["name"], "Pagina Originale")

    async def test_sorts_pages_alphabetically_by_name(self):
        FakeAsyncClient.responses = [
            {
                "data": [
                    {"id": "3", "name": "zeta"},
                    {"id": "1", "name": "Alpha"},
                    {"id": "2", "name": "beta"},
                ]
            }
        ]

        pages = await self._list_pages()

        self.assertEqual(
            [page["name"] for page in pages],
            ["Alpha", "beta", "zeta"],
        )


if __name__ == "__main__":
    unittest.main()
