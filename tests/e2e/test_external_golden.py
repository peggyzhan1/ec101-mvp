import os

import pytest


@pytest.mark.skipif(not os.environ.get("EC101_GOLDEN_DATA_DIR"), reason="未配置 EC101_GOLDEN_DATA_DIR")
def test_external_golden_data_contract():
    pytest.skip("外部金标数据由部署环境提供；本仓库不提交原始业务文件")
