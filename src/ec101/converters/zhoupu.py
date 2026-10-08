from collections import defaultdict
from typing import Any, Iterable, Mapping

from ec101.contract.schema import STANDARD_SHEETS

from .common import ConversionRequest, ConversionResult, finish_conversion, to_num
from .source_reader import read_table


def convert_zhoupu(request: ConversionRequest) -> ConversionResult:
    customers = _customers(_read_rows(request, {"customer", "customers", "客户", "客户档案"}, 4))
    products = _products(_read_rows(request, {"product", "products", "商品", "商品档案"}, 4))
    sxd_rows = _read_rows(request, {"sxd", "sales", "sales_order", "销售订单"}, 4)
    xd_rows = _read_rows(request, {"xd", "sales_detail", "销售明细"}, 4)
    orders, fulfillment = _orders(sxd_rows, xd_rows, customers)
    activities, executions, activity_by_order = _activities(request.activity_inputs, orders)
    coupon_rows = _read_rows(request, {"coupon", "coupons", "coupon_detail", "优惠券", "优惠券明细"}, 3)
    configs, redemptions, coupon_by_order = _coupons(
        coupon_rows, request.coupon_inputs, customers, orders
    )
    _fallback_masters(customers, products, orders, redemptions)
    for order in orders:
        order_no = order["单据编号"]
        order["活动编号"] = ",".join(dict.fromkeys(activity_by_order.get(order_no, ())))
        order["优惠券编号"] = ",".join(dict.fromkeys(coupon_by_order.get(order_no, ())))

    tables = {sheet: [] for sheet in STANDARD_SHEETS[1:]}
    tables.update({
        "标准客户": list(customers.values()),
        "标准商品": list(products.values()),
        "标准订单明细": orders,
        "标准活动": activities,
        "标准活动核销明细": executions,
        "标准优惠券配置": configs,
        "标准优惠券核销明细": redemptions,
        "标准履约": fulfillment,
    })
    return finish_conversion(request, tables, [
        "平台：舟谱",
        f"SXD 订单：{len({row['单据编号'] for row in orders})}",
        f"订单明细：{len(orders)}",
        f"活动核销：{len(executions)}",
        f"优惠券核销：{len(redemptions)}",
    ])


def _read_rows(request, roles, header_row):
    result = []
    seen_rows = set()
    seen_paths = set()
    for role, paths in request.source_paths.items():
        if role not in roles:
            continue
        for path in paths:
            identity = path.resolve()
            if identity in seen_paths:
                continue
            seen_paths.add(identity)
            _, _, headers, rows = read_table(path, header_row=header_row)
            for values in rows:
                row = dict(zip(headers, values))
                row_identity = tuple(sorted(row.items()))
                if row_identity not in seen_rows:
                    seen_rows.add(row_identity)
                    result.append(row)
    return result


def _first(row: Mapping[str, Any], *columns: str) -> str:
    for column in columns:
        value = row.get(column)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _number(value: Any) -> str:
    number = to_num(value)
    if number is None:
        return ""
    return str(int(number)) if number.is_integer() else format(number, ".15g")


def _customers(rows) -> dict[str, dict[str, str]]:
    result = {}
    for row in rows:
        number = _first(row, "客户编码", "客户唯一序号", "客户编号")
        if not number:
            continue
        result[number] = {
            "客户编号": number,
            "客户名称": _first(row, "客户名称"),
            "客户类型": _first(row, "渠道", "客户类型"),
            "客户区域": _first(row, "片区", "客户区域"),
            "详细地址": _first(row, "客户地址", "详细地址"),
            "联系电话": _first(row, "老板电话", "联系电话"),
            "添加时间": "",
            "所属业务员": _first(row, "专属员工", "业务员"),
        }
    return result


def _products(rows) -> dict[str, dict[str, str]]:
    result = {}
    for row in rows:
        number = _first(row, "编号", "商品编号", "商品唯一序号")
        if not number:
            continue
        result[number] = {
            "商品编号": number,
            "商品名称": _first(row, "商品名称"),
            "商品品牌": _first(row, "品牌"),
            "商品目录": _first(row, "类别", "全部类别"),
            "商品条码": _first(row, "小单位条码", "大单位条码", "条形码"),
            "商品规格": _first(row, "单位换算", "规格"),
            "基本单位": "",
            "箱规": _first(row, "大单位换算", "单位换算"),
            "每箱基本单位数量": "",
        }
    return result


def _orders(sxd_rows, xd_rows, customers):
    customer_by_name = {row["客户名称"]: number for number, row in customers.items()}
    xd_by_downstream = defaultdict(list)
    for row in xd_rows:
        xd_by_downstream[_first(row, "综合订单号", "下游订单编号")].append(row)
    orders = []
    fulfillments = []
    for sxd in sxd_rows:
        order_no = _first(sxd, "订单编号", "订单号")
        downstream = _first(sxd, "下游订单编号", "综合订单号")
        details = xd_by_downstream.get(downstream, ())
        if not order_no:
            continue
        if not details:
            details = ({},)
        for index, detail in enumerate(details):
            customer_name = _first(sxd, "客户名称") or _first(detail, "客户名称")
            customer_no = _first(detail, "客户编码") or customer_by_name.get(customer_name, "")
            product_no = _first(detail, "商品编号", "商品id")
            orders.append({
                "单据编号": order_no,
                "下单时间": _first(sxd, "下单时间"),
                "客户编号": customer_no,
                "客户名称": customer_name,
                "商品编号": product_no,
                "商品名称": _first(detail, "商品名称"),
                "商品目录": _first(detail, "全部类别", "类别"),
                "规格": _first(detail, "规格", "单位换算"),
                "商品条码": _first(detail, "条形码"),
                "单位": _first(detail, "单位名称", "单位名称（大）", "单位名称（小）"),
                "数量": _number(_first(detail, "下单数量", "下单数量（大）", "下单数量（小）")),
                "优惠前金额": _number(_first(detail, "下单金额", "订单总金额")),
                "活动编号": "",
                "优惠券编号": "",
                "优惠金额": _number(_first(sxd, "优惠金额")) if index == 0 else "0",
                "实付金额": _number(_first(sxd, "应支付金额", "已支付金额")) if index == 0 else "0",
                "业务员": _first(detail, "业务员", "专属员工"),
                "订单来源": "舟谱",
                "订单类型": _first(detail, "业务属性"),
                "订单状态": _first(sxd, "订单状态") or _first(detail, "订单状态"),
                "支付方式": "",
                "下游订单编号": downstream,
                "单价": _number(_first(detail, "小单位价格", "销售结算价")),
                "退货数量": _number(_first(detail, "退货结算数量", "退货结算数量（小）")) or "0",
            })
        detail = details[0]
        fulfillments.append({
            "单据编号": order_no,
            "下游订单编号": downstream,
            "履约订单状态": _first(detail, "订单状态") or _first(sxd, "订单状态"),
            "出库时间": _first(detail, "出(入)库时间"),
            "完成时间": _first(detail, "签收时间"),
            "结款状态": _first(detail, "结款状态"),
            "退货数量": _number(_first(detail, "退货结算数量", "退货结算数量（小）")) or "0",
        })
    return orders, fulfillments


def _activities(inputs: Iterable[Mapping[str, Any]], orders):
    order_headers = {}
    for order in orders:
        order_headers.setdefault(order["单据编号"], order)
    definitions = {}
    groups = {}
    by_order = defaultdict(list)
    for row in inputs:
        number = _first(row, "活动编号", "activity_no")
        name = _first(row, "活动名称", "name")
        order_no = _first(row, "订单号", "订单编号", "order_no")
        if not number or order_no not in order_headers:
            continue
        definitions.setdefault(number, {
            "活动编号": number,
            "活动名称": name,
            "活动类型": _first(row, "活动类型", "activity_type"),
            "促销方式": _first(row, "促销方式"),
            "开始时间": _first(row, "开始时间"),
            "结束时间": _first(row, "结束时间"),
            "是否允许叠加活动": _first(row, "是否允许叠加活动"),
            "是否允许叠加优惠券": _first(row, "是否允许叠加优惠券"),
            "活动状态": _first(row, "活动状态") or "启用",
        })
        key = (number, order_no)
        group = groups.setdefault(key, {"discount": 0.0, "product": 0.0})
        group["discount"] += to_num(_first(row, "优惠金额", "discount_amount")) or 0
        group["product"] = max(group["product"], to_num(_first(row, "商品总金额")) or 0)
        by_order[order_no].append(number)
    executions = []
    for (number, order_no), amounts in groups.items():
        order = order_headers[order_no]
        executions.append({
            "活动编号": number,
            "活动名称": definitions[number]["活动名称"],
            "客户编号": order["客户编号"],
            "客户": order["客户名称"],
            "所属业务员": order["业务员"],
            "订单号": order_no,
            "商品总金额": _number(amounts["product"]),
            "优惠金额": _number(amounts["discount"]),
        })
    return list(definitions.values()), executions, by_order


def _coupons(rows, inputs, customers, orders):
    config_inputs = {_first(row, "优惠券名称", "券名", "name"): row for row in inputs}
    customer_by_name = {row["客户名称"]: number for number, row in customers.items()}
    known_orders = {row["单据编号"] for row in orders}
    configs = {}
    redemptions = []
    by_order = defaultdict(list)
    sequence = 0
    for row in rows:
        used = int(to_num(_first(row, "已使用张数", "使用数量")) or 0)
        if used <= 0:
            continue
        name = _first(row, "券名", "优惠券名称")
        configured = config_inputs.get(name, {})
        configs.setdefault(name, {
            "优惠券配置编号": _first(configured, "优惠券配置编号", "config_no") or f"ZP-CFG-{len(configs) + 1}",
            "优惠券名称": name,
            "券类型": _first(configured, "券类型", "coupon_type") or ("返券" if "返" in name else "优惠券"),
            "配置状态": _first(configured, "配置状态") or "启用",
        })
        amount = _first(row, "优惠券面值", "优惠金额") or _first(configured, "优惠金额", "面值")
        order_no = _first(row, "关联单据编号", "订单号")
        customer_name = _first(row, "领取客户", "客户名称")
        customer_no = customer_by_name.get(customer_name, "")
        for _ in range(used):
            sequence += 1
            coupon_no = f"ZP-CPN-{sequence}"
            redemptions.append({
                "优惠券编号": coupon_no,
                "客户编号": customer_no,
                "客户": customer_name,
                "所属业务员": "",
                "领取时间": "",
                "使用期限": "",
                "状态": "已使用",
                "使用时间": "",
                "订单号": order_no,
                "优惠金额": _number(amount),
            })
            if order_no in known_orders:
                by_order[order_no].append(coupon_no)
    return list(configs.values()), redemptions, by_order


def _fallback_masters(customers, products, orders, redemptions):
    for order in orders:
        if order["客户编号"] and order["客户编号"] not in customers:
            customers[order["客户编号"]] = {
                "客户编号": order["客户编号"], "客户名称": order["客户名称"]
            }
        if order["商品编号"] and order["商品编号"] not in products:
            products[order["商品编号"]] = {
                "商品编号": order["商品编号"], "商品名称": order["商品名称"]
            }
    for redemption in redemptions:
        if redemption["客户编号"] and redemption["客户编号"] not in customers:
            customers[redemption["客户编号"]] = {
                "客户编号": redemption["客户编号"], "客户名称": redemption["客户"]
            }
