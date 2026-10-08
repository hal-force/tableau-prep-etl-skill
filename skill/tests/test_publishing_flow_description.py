"""set_flow_description: TSC 0.38's flows.update() drops description, so
the helper PUTs the REST body itself. Fake the TSC session and inspect it."""
from __future__ import annotations

import xml.etree.ElementTree as ET

from tflb_lib import publishing


class _Resp:
    ok, status_code, text = True, 200, "<tsResponse/>"


class _Session:
    def __init__(self):
        self.calls = []

    def request(self, method, url, data=None, headers=None):
        self.calls.append((method, url, data, headers))
        return _Resp()


class _Server:
    server_address = "https://example.online.tableau.com"
    version = "3.24"
    site_id = "site-luid"
    auth_token = "tok"

    def __init__(self):
        self._session = _Session()


def test_set_flow_description_puts_escaped_body():
    s = _Server()
    publishing.set_flow_description(s, "flow-luid", 'Runs "locally" <prep-cli> & TabPy')
    (method, url, body, headers), = s._session.calls
    assert method == "PUT"
    assert url.endswith("/api/3.24/sites/site-luid/flows/flow-luid")
    assert headers["X-Tableau-Auth"] == "tok"
    flow = ET.fromstring(body).find("flow")
    assert flow.get("description") == 'Runs "locally" <prep-cli> & TabPy'


def test_tsc_flow_update_still_drops_description():
    """Canary: if TSC starts serializing description, the helper can go."""
    import tableauserverclient as TSC
    from tableauserverclient.server.request_factory import RequestFactory
    item = TSC.FlowItem(project_id="p", name="f")
    item.description = "x"
    body = RequestFactory.Flow.update_req(item)
    assert b"description" not in body
