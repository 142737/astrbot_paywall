"""
Paywall WebUI 后端 API

通过 AstrBot 的 context.register_web_api 注册路由，
前端 pages/paywall-admin 通过 bridge.apiGet / bridge.apiPost 调用，
Dashboard 会转发到 /api/plug/paywall/<endpoint>。
"""

import json
from datetime import datetime

from quart import jsonify, request

from astrbot.api import logger

PLUGIN_NAME = "paywall"


class PluginAPI:
    def __init__(self, plugin):
        self.plugin = plugin

    def register(self, context):
        """注册所有 WebUI API 路由（带前缀插件名）"""
        routes = [
            ("stats", self.get_stats, ["GET"], "Paywall 统计数据"),
            ("test", self.test, ["GET"], "Paywall API 测试"),
            ("recharge", self.recharge, ["POST"], "Paywall 充值/扣费"),
            ("delist", self.delist, ["POST"], "Paywall 下架商品"),
            ("list_item", self.list_item, ["POST"], "Paywall 上架商品"),
            ("genkey", self.genkey, ["POST"], "Paywall 生成卡密"),
        ]
        for ep, handler, methods, desc in routes:
            try:
                context.register_web_api(
                    f"/{PLUGIN_NAME}/{ep}", handler, methods, desc
                )
            except Exception as e:
                logger.warning(f"[Paywall] 注册 API /{PLUGIN_NAME}/{ep} 失败: {e}")

    # ==================== 工具方法 ====================

    async def _load_index(self, key) -> list:
        """读取索引列表，兼容 str / list / None"""
        raw = await self.plugin.get_kv_data(key, None)
        if raw is None or raw == "" or raw == "null":
            return []
        if isinstance(raw, str):
            try:
                data = json.loads(raw)
                return data if isinstance(data, list) else []
            except Exception:
                return []
        return raw if isinstance(raw, list) else []

    def _fmt_item(self, item: dict) -> dict:
        return {
            "id": item.get("id", ""),
            "name": item.get("name", ""),
            "price": float(item.get("price", 0)),
            "stock": int(item.get("stock", 0)),
            "seller": item.get("seller", ""),
            "seller_name": item.get("seller_name", ""),
            "shop_type": item.get("shop_type", ""),
        }

    # ==================== 接口实现 ====================

    async def test(self):
        return jsonify({"success": True, "message": "Paywall API 正常工作"})

    async def get_stats(self):
        p = self.plugin
        try:
            users = []
            for uid in await self._load_index(p._user_index_key()):
                d = await p._get_data("user", uid)
                users.append({
                    "id": uid,
                    "balance": float(d.get("balance", 0)),
                    "total_used": float(d.get("total_used", 0)),
                    "total_calls": int(d.get("total_calls", 0)),
                })

            groups = []
            for gid in await self._load_index(p._group_index_key()):
                d = await p._get_data("group", gid)
                groups.append({
                    "id": gid,
                    "balance": float(d.get("balance", 0)),
                    "total_used": float(d.get("total_used", 0)),
                    "total_calls": int(d.get("total_calls", 0)),
                })

            shop = []
            for item_id in await self._load_index(p._shop_index_key()):
                item = await p._get_shop_item(item_id)
                if item and item.get("stock", 0) > 0:
                    shop.append(self._fmt_item(item))
            for item_id in await self._load_index(p._item_shop_index_key()):
                item = await p._get_item_shop_item(item_id)
                if item and item.get("stock", 0) > 0:
                    shop.append(self._fmt_item(item))

            keys = []
            for k in await self._load_index(p._index_key()):
                kd = await p._get_key_data(k)
                if kd:
                    keys.append({
                        "key": kd.get("key", k),
                        "amount": float(kd.get("amount", 0)),
                        "status": kd.get("status", "unused"),
                        "created_by": kd.get("created_by", "-"),
                        "used_by": kd.get("used_by") or "",
                    })

            return jsonify({
                "users": users, "groups": groups, "shop": shop, "keys": keys
            })
        except Exception as e:
            logger.error(f"[Paywall] get_stats 失败: {e}", exc_info=True)
            return jsonify({
                "users": [], "groups": [], "shop": [], "keys": [],
                "error": str(e),
            })

    async def recharge(self):
        p = self.plugin
        try:
            body = await request.get_json(force=True, silent=True) or {}
            btype = body.get("type", "user")
            bid = str(body.get("id", "")).strip()
            amount = float(body.get("amount", 0))
            # mode: "add" 增量调整（默认，兼容旧调用）；"set" 直接设为指定额度
            mode = str(body.get("mode", "add")).strip().lower()
            if not bid:
                return jsonify({"success": False, "error": "缺少目标ID"})
            if btype not in ("user", "group"):
                btype = "user"

            d = await p._get_data(btype, bid)
            if mode == "set":
                d["balance"] = max(0.0, amount)
            else:
                d["balance"] = max(0.0, float(d.get("balance", 0)) + amount)
            await p._save_data(btype, bid, d)

            logger.info(
                f"[Paywall][WebUI] {btype}:{bid} "
                f"{'设置额度为' if mode == 'set' else '调整'} {amount}，"
                f"新余额 {d['balance']:.2f}"
            )
            return jsonify({"success": True, "new_balance": d["balance"]})
        except Exception as e:
            logger.error(f"[Paywall] recharge 失败: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)})

    async def delist(self):
        p = self.plugin
        try:
            body = await request.get_json(force=True, silent=True) or {}
            item_id = str(body.get("item_id", "")).strip().upper()
            if not item_id:
                return jsonify({"success": False, "error": "缺少商品编号"})

            item = await p._get_shop_item(item_id)
            shop_type = "百货"
            if item is None:
                item = await p._get_item_shop_item(item_id)
                shop_type = "道具"
            if item is None:
                return jsonify({"success": False, "error": "商品不存在"})

            item["stock"] = 0
            if shop_type == "道具":
                await p._save_item_shop_item(item_id, item)
            else:
                await p._save_shop_item(item_id, item)

            logger.info(f"[Paywall][WebUI] 下架商品 {item_id}")
            return jsonify({"success": True, "name": item.get("name", item_id)})
        except Exception as e:
            logger.error(f"[Paywall] delist 失败: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)})

    async def list_item(self):
        p = self.plugin
        try:
            body = await request.get_json(force=True, silent=True) or {}
            name = str(body.get("name", "")).strip()
            shop_type = str(body.get("shop_type", "百货")).strip()
            try:
                price = float(body.get("price", 0))
                stock = int(body.get("stock", 0))
            except (TypeError, ValueError):
                return jsonify({"success": False, "error": "价格/库存格式不正确"})

            if not name:
                return jsonify({"success": False, "error": "缺少商品名称"})
            if price < 0:
                return jsonify({"success": False, "error": "价格不能为负"})
            if stock <= 0:
                return jsonify({"success": False, "error": "库存需大于0"})
            if shop_type not in ("百货", "道具"):
                shop_type = "百货"

            item_id = p._gen_item_id()
            item = {
                "id": item_id,
                "name": name,
                "price": price,
                "original_price": price,
                "stock": stock,
                "seller": "system",
                "seller_name": "系统商店",
                "created_at": datetime.now().isoformat(),
                "discount": 1.0,
                "shop_type": shop_type,
            }
            if shop_type == "道具":
                await p._save_item_shop_item(item_id, item)
                await p._add_item_shop_index(item_id)
            else:
                await p._save_shop_item(item_id, item)
                await p._add_shop_index(item_id)

            logger.info(
                f"[Paywall][WebUI] 上架{shop_type} {name} "
                f"价格 {price} 库存 {stock} 编号 {item_id}"
            )
            return jsonify({"success": True, "id": item_id, "name": name})
        except Exception as e:
            logger.error(f"[Paywall] list_item 失败: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)})

    async def genkey(self):
        p = self.plugin
        try:
            body = await request.get_json(force=True, silent=True) or {}
            amount = float(body.get("amount", 0))
            count = int(body.get("count", 1))
            if amount <= 0 or count <= 0 or count > 50:
                return jsonify({
                    "success": False, "error": "金额需大于0，数量需为1~50"
                })

            keys = []
            for _ in range(count):
                key = p._gen_key()
                while await p._get_key_data(key) is not None:
                    key = p._gen_key()
                kd = {
                    "key": key,
                    "amount": amount,
                    "created_by": "webui",
                    "created_at": datetime.now().isoformat(),
                    "used_by": None,
                    "used_at": None,
                    "status": "unused",
                }
                await p._save_key(key, kd)
                await p._add_key_index(key)
                keys.append(key)

            logger.info(f"[Paywall][WebUI] 生成 {count} 张 {amount} 积分卡密")
            return jsonify({"success": True, "keys": keys})
        except Exception as e:
            logger.error(f"[Paywall] genkey 失败: {e}", exc_info=True)
            return jsonify({"success": False, "error": str(e)})
