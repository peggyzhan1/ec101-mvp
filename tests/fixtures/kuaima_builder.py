from html import escape
from pathlib import Path

from ec101.converters.common import ConversionRequest


def write_table(path: Path, headers, rows):
    table_rows = [headers, *rows]
    html = "<html><body><table>" + "".join(
        "<tr>" + "".join(f"<td>{escape(str(value))}</td>" for value in row) + "</tr>"
        for row in table_rows
    ) + "</table></body></html>"
    path.write_bytes(html.encode("gb18030"))
    return path


def build_kuaima_request(tmp_path, *, fallback=False, duplicate_order_file=False):
    customer_no = "C-MISSING" if fallback else "C1"
    product_no = "P-MISSING" if fallback else "P1"
    customers = write_table(
        tmp_path / "customers.xls",
        ["客户编号", "客户名称", "客户类型", "客户区域", "详细地址", "联系电话", "添加时间", "所属业务员"],
        [] if fallback else [["C1", "客户一", "门店", "华东", "地址", "13800000000", "2026-01-01", "业务员"]],
    )
    products = write_table(
        tmp_path / "products.xls",
        ["商品编号", "商品名称", "品牌", "一级目录", "条形码", "规格值1", "单位", "包装规格"],
        [] if fallback else [["P1", "商品一", "品牌", "饮料", "690000000001", "1箱", "箱", "12瓶"]],
    )
    orders = write_table(
        tmp_path / "orders.xls",
        [
            "订单编号", "下单时间", "客户编号", "客户名称", "商品编号", "商品名称", "商品目录",
            "规格", "商品条码", "订货数量单位", "订货数量", "优惠前金额", "优惠金额", "订货金额",
            "所属业务员", "订单来源", "订单类型", "订单状态", "支付方式", "订货单价",
        ],
        [[
            "O1", "2026-09-19 23:59:59", customer_no, "客户一", product_no, "商品一", "饮料",
            "1箱", "690000000001", "箱", "2", "200", "15", "185", "业务员", "小程序",
            "普通订单", "已完成", "在线", "100",
        ]],
    )
    activities = write_table(
        tmp_path / "activities.xls",
        ["订单号", "客户", "商品总金额", "促销优惠金额", "享受促销政策"],
        [
            ["O1", "客户一", "200", "6", "参与[满300减15]组合金额满¥300，立减¥15活动"],
            ["O1", "客户一", "200", "4", "参与[满300减15]组合金额满¥300，立减¥15活动"],
        ],
    )
    coupons = write_table(
        tmp_path / "coupons.xls",
        ["优惠券名称", "优惠券编号", "领取客户", "客户编号", "所属业务员", "领取时间", "使用期限", "状态", "使用时间", "使用单号", "优惠金额"],
        [
            ["测试券", "CP1", "客户一", customer_no, "业务员", "2026-09-01", "2026-09-30", "已使用", "2026-09-19", "O1", "5"],
            ["测试券", "CP2", "客户一", customer_no, "业务员", "2026-09-01", "2026-09-30", "已使用", "2026-09-19", "", "3"],
        ],
    )
    order_paths = [orders, orders] if duplicate_order_file else [orders]
    return ConversionRequest(
        platform="快马",
        dealer_name="测试经销商",
        source_paths={
            "customer": [customers],
            "product": [products],
            "order_detail": order_paths,
            "activity_detail": [activities],
            "coupon_detail": [coupons],
        },
        activity_inputs=[],
        coupon_inputs=[],
        output_dir=tmp_path / "output",
    )
