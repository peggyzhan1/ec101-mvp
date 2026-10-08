from html import escape

from ec101.converters.common import ConversionRequest


def write_report(path, headers, rows, header_row=4):
    preamble = [[f"说明{index}"] for index in range(1, header_row)]
    table_rows = [*preamble, headers, *rows]
    html = "<html><body><table>" + "".join(
        "<tr>" + "".join(f"<td>{escape(str(value))}</td>" for value in row) + "</tr>"
        for row in table_rows
    ) + "</table></body></html>"
    path.write_bytes(html.encode("gb18030"))
    return path


def build_zhoupu_request(tmp_path, *, multiple_orders=False):
    customers = write_report(
        tmp_path / "customers.xlsx",
        ["客户编码", "客户名称", "老板电话", "客户地址", "片区", "渠道", "专属员工"],
        [["C1", "客户一", "13800000000", "地址", "华东", "门店", "业务员"]],
    )
    products = write_report(
        tmp_path / "products.xlsx",
        ["编号", "商品名称", "类别", "品牌", "单位换算", "小单位条码", "大单位条码"],
        [["P1", "商品一", "饮料", "品牌", "1箱=12瓶", "6901", "6902"]],
    )
    sxd1 = write_report(
        tmp_path / "sxd-1.xlsx",
        ["订单编号", "客户名称", "下单时间", "订单总金额", "优惠金额", "应支付金额", "下游订单编号", "订单状态"],
        [["SXD1", "客户一", "2026-09-19 23:59:59", "200", "10", "190", "XD1", "已完成"]],
    )
    sxd_paths = [sxd1]
    if multiple_orders:
        sxd_paths.append(write_report(
            tmp_path / "sxd-2.xlsx",
            ["订单编号", "客户名称", "下单时间", "订单总金额", "优惠金额", "应支付金额", "下游订单编号", "订单状态"],
            [["SXD2", "客户一", "2026-09-20 00:00:00", "100", "0", "100", "XD2", "处理中"]],
        ))
    xd_rows = [
        ["OUT1", "P1", "商品一", "1箱", "P1", "6901", "饮料", "品牌", "1箱=12瓶", "XD1", "客户一", "C1", "业务员", "2026-09-20", "2026-09-20", "2026-09-21", "2026-09-21", "2026-09-22", "2", "箱", "200", "已完成", "已结款", "0"],
    ]
    if multiple_orders:
        xd_rows.append(
            ["OUT2", "P1", "商品一", "1箱", "P1", "6901", "饮料", "品牌", "1箱=12瓶", "XD2", "客户一", "C1", "业务员", "2026-09-20", "", "", "", "", "1", "箱", "100", "处理中", "未结款", "0"]
        )
    xd = write_report(
        tmp_path / "xd.xlsx",
        ["单据", "商品id", "商品名称", "规格", "商品编号", "条形码", "类别", "品牌", "单位换算", "综合订单号", "客户名称", "客户编码", "业务员", "单据时间", "审核时间", "出(入)库时间", "签收时间", "结算时间", "下单数量", "单位名称", "下单金额", "订单状态", "结款状态", "退货结算数量"],
        xd_rows,
    )
    coupons = write_report(
        tmp_path / "coupons.xls",
        ["券名", "领取客户", "已领取数量", "优惠券面值", "已使用张数", "关联单据编号"],
        [
            ["可口可乐产品288返15元券", "客户一", "1", "5", "1", "SXD1"],
            ["可口可乐产品288返15元券", "客户一", "1", "5", "1", ""],
        ],
        header_row=3,
    )
    return ConversionRequest(
        platform="舟谱",
        dealer_name="测试经销商",
        source_paths={
            "customer": [customers], "product": [products], "sxd": sxd_paths,
            "xd": [xd], "coupon_detail": [coupons],
        },
        activity_inputs=[{
            "活动编号": "ZP-A1", "活动名称": "满赠活动", "活动类型": "满赠",
            "订单号": "SXD1", "商品总金额": "200", "优惠金额": "10",
        }],
        coupon_inputs=[{
            "优惠券配置编号": "ZP-C1", "优惠券名称": "可口可乐产品288返15元券",
            "券类型": "返券", "优惠金额": "5",
        }],
        output_dir=tmp_path / "output",
    )
