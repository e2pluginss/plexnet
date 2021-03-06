import py
pytest_plugins = "pytester"
from py.__.execnet.gateway import ExecnetAPI

class TestExecnetEvents:
    def test_popengateway(self, _pytest):
        rec = _pytest.gethookrecorder(ExecnetAPI)
        gw = py.execnet.PopenGateway()
        call = rec.popcall("pyexecnet_gateway_init") 
        assert call.gateway == gw
        gw.exit()
        call = rec.popcall("pyexecnet_gateway_exit")
        assert call.gateway == gw
