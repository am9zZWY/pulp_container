from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.http import HttpResponseRedirect
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from pulp_container.app.exceptions import BlobNotFound
from pulp_container.app.registry_api import Blobs


@override_settings(TOKEN_AUTH_DISABLED=True)
class TestBlobContentNegotiation(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.digest = "sha256:" + "a" * 64
        self.url = f"/v2/library/image/blobs/{self.digest}"
        self.view = Blobs.as_view({"get": "get", "head": "head"})
        self.enterContext(
            patch(
                "pulp_container.app.registry_api.get_domain",
                return_value=SimpleNamespace(
                    storage_class="pulpcore.app.models.storage.FileSystem"
                ),
            )
        )

    def test_blob_requests_reach_handler_with_empty_missing_or_nonempty_accept(self):
        for method in ("get", "head"):
            for accept in (None, "", "*/*", "application/octet-stream"):
                with self.subTest(method=method, accept=accept):
                    headers = {} if accept is None else {"HTTP_ACCEPT": accept}
                    request = getattr(self.factory, method)(self.url, **headers)
                    force_authenticate(request, user=User(username="reader"))
                    with patch.object(
                        Blobs,
                        "handle_safe_method",
                        return_value=HttpResponseRedirect("/content/blob"),
                    ) as handler:
                        response = self.view(request, path="library/image", pk=self.digest)
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(response["Location"], "/content/blob")
                    handler.assert_called_once()
                    self.assertEqual(request.META.get("HTTP_ACCEPT"), accept)

    def test_empty_accept_preserves_blob_not_found_response(self):
        request = self.factory.get(self.url, HTTP_ACCEPT="")
        force_authenticate(request, user=User(username="reader"))
        with patch.object(
            Blobs, "handle_safe_method", side_effect=BlobNotFound(digest=self.digest)
        ):
            response = self.view(request, path="library/image", pk=self.digest)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["errors"][0]["code"], "BLOB_UNKNOWN")
