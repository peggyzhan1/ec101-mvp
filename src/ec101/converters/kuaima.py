from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timedelta
from hashlib import sha1
import re
from typing import Any, Iterable, Mapping

from ec101.contract.schema import STANDARD_SHEETS

from .common import ConversionRequest, ConversionResult, finish_conversion, to_num
from .source_reader import read_table


_ROLE_ALIASES = {
    "customer": {"customer", "customers", "客户", "客户档案"},
    "product": {"product", "products", "商品", "商品档案"},
    "order": {"order", "orders", "order_detail", "订单", "订单明细"},
    "sales": {"sales", "sales_detail", "销售", "销售明细"},
    "activity": {"activity", "activities", "activity_detail", "活动", "活动明细"},
    "coupon": {"coupon", "coupons", "coupon_detail", "优惠券", "优惠券明细"},
}


def parse_policy_activity_name(text: str) -> str:
    value = str(text or "").strip()
    match = re.search(r"[\[【](.*?)[\]】]", value)
    return match.group(1).strip() if match else value


def infer_activity_type(policy_text: str, activity_name: str) -> str:
    text = f"{policy_text} {activity_name}"
    if "赠" in text or "送赠品" in text:
        return "满赠"
    if "返券" in text or "返劵" in text:
        return "返券"
    if "减" in text or "立减" in text:
        return "满减"
    return "其他"


def convert_kuaima(request: ConversionRequest) -> ConversionResult:
    source_paths = _deduplicated_sources(request.source_paths)
    request = replace(request, source_paths=source_paths)
    customers = _customer_rows(_source_rows(request, "customer"))
    products = _product_rows(_source_rows(request, "product"))
    order_source = _source_rows(request, "order") or _source_rows(request, "sales")
    orders = _order_rows(order_source)
    activities, executions, activity_by_order = _activity_rows(
        _source_rows(request, "activity"), orders, request.activity_inputs
    )
    coupon_configs, redemptions, coupons_by_order = _coupon_rows(
        _source_rows(request, "coupon"), request.coupon_inputs
    )
    _add_fallback_masters(customers, products, orders, redemptions)
    _add_trace_fields(orders, activity_by_order, coupons_by_order)

    tables = {sheet: [] for sheet in STANDARD_SHEETS[1:]}
    tables.update({
        "标准客户": list(customers.values()),
        "标准商品": list(products.values()),
        "标准订单明细": orders,
        "标准活动": activities,
        "标准活动核销明细": executions,
        "标准优惠券配置": coupon_configs,
        "标准优惠券核销明细": redemptions,
        "标准履约": _fulfillment_rows(orders),
    })
    report_lines = [
        "平台：快马",
        f"订单明细：{len(orders)}",
        f"活动核销：{len(executions)}",
        f"优惠券核销：{len(redemptions)}",
    ]
    return finish_conversion(request, tables, report_lines)


def _deduplicated_sources(source_paths):
    result = {}
    seen = set()
    for role, paths in source_paths.items():
        unique = []
        for path in paths:
            identity = path.resolve()
            if identity in seen:
                continue
            seen.add(identity)
            unique.append(path)
        result[role] = unique
    return result


def _source_rows(request: ConversionRequest, canonical_role: str) -> list[dict[str, str]]:
    result = []
    seen = set()
    aliases = _ROLE_ALIASES[canonical_role]
    for role, paths in request.source_paths.items():
        if role not in aliases:
            continue
        for path in paths:
            _, _, headers, rows = read_table(path)
            for values in rows:
                row = dict(zip(headers, values))
                identity = tuple(sorted(row.items()))
                if identity not in seen:
                    seen.add(identity)
                    result.append(row)
    return result


def _first(row: Mapping[str, Any], *columns: str) -> str:
    for column in columns:
        value = row.get(column)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}-{sha1(value.encode('utf-8')).hexdigest()[:12]}"


def _number(value: Any) -> str:
    number = to_num(value)
    if number is None:
        return ""
    return str(int(number)) if number.is_integer() else format(number, ".15g")


def _datetime_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    number = to_num(text)
    if number is not None and number > 20000 and re.fullmatch(r"[0-9.]+", text):
        return (datetime(1899, 12, 30) + timedelta(days=number)).strftime("%Y-%m-%d %H:%M:%S")
    normalized = text.replace("/", "-")
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(normalized, pattern)
            return parsed.strftime("%Y-%m-%d %H:%M:%S") if "H" in pattern else parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return text


def _customer_rows(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, str]]:
    result = {}
    for row in rows:
        customer_no = _first(row, "客户编号", "登录账号")
        if not customer_no:
            continue
        result[customer_no] = {
            "客户编号": customer_no,
            "客户名称": _first(row, "客户名称", "领取客户"),
            "客户类型": _first(row, "客户类型"),
            "客户区域": _first(row, "客户区域", "省市区"),
            "详细地址": _first(row, "详细地址"),
            "联系电话": _first(row, "联系电话"),
            "添加时间": _datetime_text(_first(row, "添加时间")),
            "所属业务员": _first(row, "所属业务员"),
        }
    return result


def _product_rows(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, str]]:
    result = {}
    for row in rows:
        product_no = _first(row, "商品编号", "货品编号")
        if not product_no:
            continue
        result[product_no] = {
            "商品编号": product_no,
            "商品名称": _first(row, "商品名称"),
            "商品品牌": _first(row, "品牌", "商品品牌"),
            "商品目录": _first(row, "三级目录", "二级目录", "一级目录", "商品目录"),
            "商品条码": _first(row, "条形码", "商品条码"),
            "商品规格": _first(row, "规格值1", "规格", "包装规格"),
            "基本单位": _first(row, "单位", "基本单位"),
            "箱规": _first(row, "包装规格", "换算关系1"),
            "每箱基本单位数量": _number(_first(row, "基本单位数量", "换算关系1")),
        }
    return result


def _order_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    result = []
    seen = set()
    for row in rows:
        order_no = _first(row, "订单编号", "单据编号", "订单号")
        product_no = _first(row, "商品编号")
        identity = (order_no, product_no, _first(row, "规格"), _first(row, "订货数量", "数量"))
        if not order_no or identity in seen:
            continue
        seen.add(identity)
        result.append({
            "单据编号": order_no,
            "下单时间": _datetime_text(_first(row, "下单时间")),
            "客户编号": _first(row, "客户编号"),
            "客户名称": _first(row, "客户名称"),
            "商品编号": product_no,
            "商品名称": _first(row, "商品名称"),
            "商品目录": _first(row, "商品目录"),
            "规格": _first(row, "规格"),
            "商品条码": _first(row, "商品条码", "条形码"),
            "单位": _first(row, "订货数量单位", "单位", "基本单位"),
            "数量": _number(_first(row, "订货数量", "数量")),
            "优惠前金额": _number(_first(row, "优惠前金额")),
            "活动编号": "",
            "优惠券编号": "",
            "优惠金额": _number(_first(row, "优惠金额")),
            "实付金额": _number(_first(row, "订货金额", "销售金额")),
            "业务员": _first(row, "所属业务员", "业务员"),
            "订单来源": _first(row, "订单来源"),
            "订单类型": _first(row, "订单类型"),
            "订单状态": _first(row, "订单状态") or "已完成",
            "支付方式": _first(row, "支付方式"),
            "下游订单编号": _first(row, "下游订单编号"),
            "单价": _number(_first(row, "订货单价", "销售均价")),
            "退货数量": _number(_first(row, "退货数量")) or "0",
        })
    return result


def _activity_rows(rows, orders, inputs):
    order_map = {}
    for order in orders:
        order_map.setdefault(order["单据编号"], order)
    overrides = {_first(row, "活动名称", "name"): row for row in inputs}
    groups = {}
    policies = {}
    for row in rows:
        order_no = _first(row, "订单号", "订单编号", "单据编号")
        if order_no not in order_map:
            continue
        policy = _first(row, "享受促销政策", "促销政策", "活动名称")
        name = parse_policy_activity_name(policy) or "未命名活动"
        key = (order_no, name)
        group = groups.setdefault(key, {"amount": 0.0, "product_amount": 0.0})
        group["amount"] += to_num(_first(row, "促销优惠金额", "优惠金额")) or 0
        group["product_amount"] = max(
            group["product_amount"], to_num(_first(row, "商品总金额")) or 0
        )
        policies[name] = policy
    activity_by_name = {}
    for name in dict.fromkeys(name for _, name in groups):
        override = overrides.get(name, {})
        activity_by_name[name] = {
            "活动编号": _first(override, "活动编号", "activity_no") or _stable_id("KM-ACT", name),
            "活动名称": name,
            "活动类型": _first(override, "活动类型", "activity_type") or infer_activity_type(policies[name], name),
            "促销方式": _first(override, "促销方式", "promo_method"),
            "开始时间": _datetime_text(_first(override, "开始时间", "start_time")),
            "结束时间": _datetime_text(_first(override, "结束时间", "end_time")),
            "是否允许叠加活动": _first(override, "是否允许叠加活动"),
            "是否允许叠加优惠券": _first(override, "是否允许叠加优惠券"),
            "活动状态": _first(override, "活动状态") or "启用",
        }
    executions = []
    by_order = defaultdict(list)
    for (order_no, name), group in groups.items():
        activity = activity_by_name[name]
        order = order_map[order_no]
        executions.append({
            "活动编号": activity["活动编号"],
            "活动名称": name,
            "客户编号": order["客户编号"],
            "客户": order["客户名称"],
            "所属业务员": order["业务员"],
            "订单号": order_no,
            "商品总金额": _number(group["product_amount"]),
            "优惠金额": _number(group["amount"]),
        })
        by_order[order_no].append(activity["活动编号"])
    return list(activity_by_name.values()), executions, by_order


def _coupon_rows(rows, inputs):
    overrides = {_first(row, "优惠券名称", "name"): row for row in inputs}
    configs = {}
    redemptions = []
    by_order = defaultdict(list)
    for row in rows:
        status = _first(row, "状态")
        if status not in {"已使用", "已核销", "核销"}:
            continue
        name = _first(row, "优惠券名称") or "未命名优惠券"
        override = overrides.get(name, {})
        configs.setdefault(name, {
            "优惠券配置编号": _first(override, "优惠券配置编号", "config_no") or _stable_id("KM-CPN", name),
            "优惠券名称": name,
            "券类型": _first(override, "券类型", "coupon_type") or "优惠券",
            "配置状态": _first(override, "配置状态") or "启用",
        })
        order_no = _first(row, "使用单号", "订单号")
        coupon_no = _first(row, "优惠券编号")
        redemptions.append({
            "优惠券编号": coupon_no,
            "客户编号": _first(row, "客户编号"),
            "客户": _first(row, "领取客户", "客户"),
            "所属业务员": _first(row, "所属业务员"),
            "领取时间": _datetime_text(_first(row, "领取时间")),
            "使用期限": _first(row, "使用期限"),
            "状态": status,
            "使用时间": _datetime_text(_first(row, "使用时间")),
            "订单号": order_no,
            "优惠金额": _number(_first(row, "优惠金额")),
        })
        if order_no:
            by_order[order_no].append(coupon_no)
    return list(configs.values()), redemptions, by_order


def _add_fallback_masters(customers, products, orders, redemptions):
    for order in orders:
        customer_no = order["客户编号"]
        if customer_no and customer_no not in customers:
            customers[customer_no] = {"客户编号": customer_no, "客户名称": order["客户名称"]}
        product_no = order["商品编号"]
        if product_no and product_no not in products:
            products[product_no] = {"商品编号": product_no, "商品名称": order["商品名称"]}
    for redemption in redemptions:
        customer_no = redemption["客户编号"]
        if customer_no and customer_no not in customers:
            customers[customer_no] = {"客户编号": customer_no, "客户名称": redemption["客户"]}


def _add_trace_fields(orders, activity_by_order, coupons_by_order):
    for order in orders:
        order_no = order["单据编号"]
        order["活动编号"] = ",".join(dict.fromkeys(activity_by_order.get(order_no, ())))
        order["优惠券编号"] = ",".join(dict.fromkeys(coupons_by_order.get(order_no, ())))


def _fulfillment_rows(orders):
    result = []
    seen = set()
    for order in orders:
        order_no = order["单据编号"]
        if order_no in seen:
            continue
        seen.add(order_no)
        result.append({
            "单据编号": order_no,
            "下游订单编号": order["下游订单编号"],
            "履约订单状态": order["订单状态"],
            "出库时间": "",
            "完成时间": "",
            "结款状态": "",
            "退货数量": order["退货数量"],
        })
    return result
