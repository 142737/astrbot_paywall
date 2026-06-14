"""
AstrBot 收费插件 v4.0 - 群/私聊双维度计费 + 卡密充值 + 签到系统 + 积分商城 + 人格化欠费提示
按消息条数扣费（一积分一句话）
使用 AstrBot KV 存储
指令前缀: pw
管理员免限额
"""

import json
import random
import secrets
import string
from datetime import datetime, timedelta
import asyncio
from collections import Counter
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.provider import ProviderRequest, LLMResponse
from astrbot.api import AstrBotConfig, logger

@register("paywall", "洛蒂", "API 双维度收费插件", "4.2.1", "https://github.com/yourname/paywall")
class PaywallPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        if config is None:
            config = {}
        self.config = config
        self.cost = config.get("cost_per_message", 1.0)
        self.free_user = config.get("free_user_quota", 3000)
        self.free_group = config.get("free_group_quota", 10000)
        self.sign_min = config.get("sign_min", 10)
        self.sign_max = config.get("sign_max", 100)
        self.sign_item_chance = config.get("sign_item_chance", 20)
        self.items = config.get("items", [])  # 道具商城预设物品
        self.general_items = config.get("general_items", [])  # 百货商城预设物品
        self.tax_rate = config.get("tax_rate", 5)
        self.bank_rate_min = config.get("bank_rate_min", 1.0) / 100  # 银行日利率最小值(配置填百分比，如1表示1%)
        self.bank_rate_max = config.get("bank_rate_max", 2.5) / 100  # 银行日利率最大值(配置填百分比，如2.5表示2.5%)
        self.admins = [str(x) for x in config.get("admins", [])]
        self.user_wl = [str(x) for x in config.get("user_whitelist", [])]
        self.group_wl = [str(x) for x in config.get("group_whitelist", [])]
        self.enabled = config.get("enabled", True)
        self.contact_group = config.get("contact_group", "")
        logger.info(f"[Paywall] 已加载 | 每条消息扣 {self.cost} 积分 | 签到 {self.sign_min}~{self.sign_max} 积分 | 商城税率 {self.tax_rate}% | 管理员免限额")
        # 在 __init__ 阶段就注册 WebUI API，保证热重载插件时路由也能注册成功
        # （on_astrbot_loaded 仅在 AstrBot 整体启动时触发一次，单插件重载未必重放）
        self._register_webui_api()

    def _register_webui_api(self):
        """注册 WebUI API 路由，register_web_api 自带同路由替换，可安全重复调用"""
        try:
            from .plugin_api import PluginAPI
            self.webui_api = PluginAPI(self)
            self.webui_api.register(self.context)
            logger.info("[Paywall] WebUI API 路由已注册")
        except Exception as e:
            logger.warning(f"[Paywall] WebUI API 注册失败: {e}", exc_info=True)

    # ==================== 工具方法 ====================

    def _is_private(self, event: AstrMessageEvent) -> bool:
        return event.is_private_chat() or not event.get_group_id()

    def _get_billing_id(self, event: AstrMessageEvent) -> tuple:
        if self._is_private(event):
            return ("user", str(event.get_sender_id()))
        else:
            return ("group", str(event.get_group_id()))

    def _kv_key(self, btype: str, bid: str) -> str:
        return f"balance:{btype}:{bid}"

    def _key_record_key(self, key: str) -> str:
        return f"key:{key}"

    def _index_key(self) -> str:
        return "key_index"

    def _shop_key(self, item_id: str) -> str:
        return f"shop:{item_id}"

    def _shop_index_key(self) -> str:
        return "shop_index"

    def _inventory_key(self, user_id: str) -> str:
        return f"inventory:{user_id}"

    def _trade_key(self, user_id: str) -> str:
        return f"trade:{user_id}"

    def _user_index_key(self) -> str:
        return "paywall_user_index"

    def _group_index_key(self) -> str:
        return "paywall_group_index"

    def _item_shop_index_key(self) -> str:
        return "item_shop_index"

    def _item_shop_key(self, item_id: str) -> str:
        return f"item_shop:{item_id}"

    def _bank_key(self, user_id: str) -> str:
        return f"bank:{user_id}"

    def _bank_record_key(self, user_id: str) -> str:
        return f"bank_record:{user_id}"

    async def _get_data(self, btype: str, bid: str) -> dict:
        try:
            raw = await self.get_kv_data(self._kv_key(btype, bid), None)
            if raw is not None and raw != "" and raw != "null":
                if isinstance(raw, str):
                    data = json.loads(raw)
                else:
                    data = raw
                if isinstance(data, dict) and "balance" in data:
                    return data
        except Exception as e:
            logger.warning(f"[Paywall] 读取数据失败 {btype}:{bid}: {e}")
        free = self.free_user if btype == "user" else self.free_group
        data = {
            "balance": free,
            "total_used": 0,
            "total_calls": 0,
            "first_seen": datetime.now().isoformat(),
            "type": btype,
            "id": bid,
            "last_sign_date": ""
        }
        await self._add_to_index(btype, bid)
        return data

    async def _save_data(self, btype: str, bid: str, data: dict):
        await self.put_kv_data(self._kv_key(btype, bid), json.dumps(data, ensure_ascii=False))

    def _is_admin(self, user_id: str) -> bool:
        return str(user_id) in self.admins

    def _is_whitelist(self, event: AstrMessageEvent) -> bool:
        sender = str(event.get_sender_id())
        if sender in self.user_wl:
            return True
        gid = event.get_group_id()
        if gid and str(gid) in self.group_wl:
            return True
        return False

    def _fmt_balance(self, data: dict) -> str:
        btype = "👤 个人" if data["type"] == "user" else "👥 群组"
        return (
            f"{btype}账户: {data['id']}\n"
            f"当前余额: {data['balance']:.2f} 积分\n"
            f"累计消耗: {data['total_used']:.2f} 积分\n"
            f"累计调用: {data['total_calls']} 次"
        )

    def _gen_key(self) -> str:
        chars = string.ascii_uppercase + string.digits
        parts = [''.join(secrets.choice(chars) for _ in range(4)) for _ in range(3)]
        return "PW-" + "-".join(parts)

    def _gen_item_id(self) -> str:
        chars = string.ascii_uppercase + string.digits
        return "ITEM-" + ''.join(secrets.choice(chars) for _ in range(6))

    async def _get_key_data(self, key: str) -> dict | None:
        try:
            raw = await self.get_kv_data(self._key_record_key(key), None)
            if raw is not None and raw != "" and raw != "null":
                if isinstance(raw, str):
                    return json.loads(raw)
                elif isinstance(raw, dict):
                    return raw
        except Exception:
            pass
        return None

    async def _save_key(self, key: str, data: dict):
        await self.put_kv_data(self._key_record_key(key), json.dumps(data, ensure_ascii=False))

    async def _add_key_index(self, key: str):
        try:
            idx = await self.get_kv_data(self._index_key(), None)
            if idx is None:
                idx = []
            else:
                idx = json.loads(idx) if isinstance(idx, str) else idx
            if key not in idx:
                idx.append(key)
                await self.put_kv_data(self._index_key(), json.dumps(idx, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"[Paywall] 更新卡密索引失败: {e}")

    # ==================== 商城系统 ====================

    async def _get_shop_item(self, item_id: str) -> dict | None:
        try:
            raw = await self.get_kv_data(self._shop_key(item_id), None)
            if raw is not None and raw != "" and raw != "null":
                if isinstance(raw, str):
                    return json.loads(raw)
                elif isinstance(raw, dict):
                    return raw
        except Exception:
            pass
        return None

    async def _save_shop_item(self, item_id: str, data: dict):
        await self.put_kv_data(self._shop_key(item_id), json.dumps(data, ensure_ascii=False))

    async def _add_shop_index(self, item_id: str):
        try:
            idx = await self.get_kv_data(self._shop_index_key(), None)
            if idx is None:
                idx = []
            else:
                idx = json.loads(idx) if isinstance(idx, str) else idx
            if item_id not in idx:
                idx.append(item_id)
                await self.put_kv_data(self._shop_index_key(), json.dumps(idx, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"[Paywall] 更新商品索引失败: {e}")

    async def _get_inventory(self, user_id: str) -> list:
        try:
            raw = await self.get_kv_data(self._inventory_key(user_id), None)
            if raw is not None and raw != "" and raw != "null":
                if isinstance(raw, str):
                    return json.loads(raw)
                elif isinstance(raw, list):
                    return raw
        except Exception:
            pass
        return []

    async def _save_inventory(self, user_id: str, data: list):
        await self.put_kv_data(self._inventory_key(user_id), json.dumps(data, ensure_ascii=False))

    async def _add_to_index(self, btype: str, bid: str):
        """将用户/群组添加到索引中"""
        try:
            key = self._user_index_key() if btype == "user" else self._group_index_key()
            idx_raw = await self.get_kv_data(key, None)
            if idx_raw is None:
                idx = []
            else:
                idx = json.loads(idx_raw) if isinstance(idx_raw, str) else idx_raw
            if bid not in idx:
                idx.append(bid)
                await self.put_kv_data(key, json.dumps(idx, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"[Paywall] 更新索引失败 {btype}:{bid}: {e}")

    async def _get_item_shop_item(self, item_id: str) -> dict | None:
        """获取道具商城商品"""
        try:
            raw = await self.get_kv_data(self._item_shop_key(item_id), None)
            if raw is not None and raw != "" and raw != "null":
                if isinstance(raw, str):
                    return json.loads(raw)
                elif isinstance(raw, dict):
                    return raw
        except Exception:
            pass
        return None

    async def _save_item_shop_item(self, item_id: str, data: dict):
        await self.put_kv_data(self._item_shop_key(item_id), json.dumps(data, ensure_ascii=False))

    async def _get_bank_data(self, user_id: str) -> dict:
        """获取用户银行数据"""
        try:
            raw = await self.get_kv_data(self._bank_key(user_id), None)
            if raw is not None and raw != "" and raw != "null":
                if isinstance(raw, str):
                    data = json.loads(raw)
                elif isinstance(raw, dict):
                    data = raw
                else:
                    data = {}
                # 兼容旧数据：last_interest_time -> last_interest_date
                if "last_interest_date" not in data and "last_interest_time" in data:
                    try:
                        data["last_interest_date"] = datetime.fromisoformat(data["last_interest_time"]).strftime("%Y-%m-%d")
                    except Exception:
                        data["last_interest_date"] = ""
                return data
        except Exception:
            pass
        return {
            "balance": 0.0,
            "total_deposit": 0.0,
            "total_withdraw": 0.0,
            "total_interest": 0.0,
            "last_interest_date": ""
        }

    async def _save_bank_data(self, user_id: str, data: dict):
        await self.put_kv_data(self._bank_key(user_id), json.dumps(data, ensure_ascii=False))

    async def _add_bank_record(self, user_id: str, record: dict):
        try:
            key = self._bank_record_key(user_id)
            raw = await self.get_kv_data(key, None)
            if raw is None:
                records = []
            else:
                records = json.loads(raw) if isinstance(raw, str) else raw
            records.append(record)
            if len(records) > 50:
                records = records[-50:]
            await self.put_kv_data(key, json.dumps(records, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"[Paywall] 银行记录保存失败: {e}")

    async def _calc_interest(self, user_id: str) -> float:
        """计算并发放利息（每天随机利率，按天结算，每天只结一次）"""
        bank_data = await self._get_bank_data(user_id)
        if bank_data["balance"] <= 0:
            return 0.0

        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        last_date_str = bank_data.get("last_interest_date", "")

        # 兼容旧数据：如果只有 last_interest_time，提取日期
        if not last_date_str:
            last_time_str = bank_data.get("last_interest_time", "")
            if last_time_str:
                try:
                    last_date_str = datetime.fromisoformat(last_time_str).strftime("%Y-%m-%d")
                except Exception:
                    last_date_str = ""

        # 今天已经结算过，不再重复结算
        if last_date_str == today_str:
            return 0.0

        # 计算距离上次结算的天数
        if last_date_str:
            try:
                last_date = datetime.strptime(last_date_str, "%Y-%m-%d")
                days_passed = (now - last_date).days
            except Exception:
                days_passed = 1
        else:
            days_passed = 1

        if days_passed < 1:
            return 0.0

        total_interest = 0.0
        last_rate = 0.0

        # 逐天结算（支持多天未登录的补结）
        for day_offset in range(days_passed):
            daily_rate = random.uniform(self.bank_rate_min, self.bank_rate_max)
            interest = bank_data["balance"] * daily_rate
            interest = round(interest, 2)

            bank_data["balance"] += interest
            bank_data["total_interest"] += interest
            total_interest += interest
            last_rate = daily_rate

            # 记录日期：从上次结算日+1天开始
            if last_date_str:
                record_date = (last_date + timedelta(days=day_offset + 1)).strftime("%Y-%m-%d")
            else:
                record_date = today_str

            record = {
                "type": "利息",
                "amount": interest,
                "rate": round(daily_rate * 100, 2),
                "balance": bank_data["balance"],
                "date": record_date
            }
            await self._add_bank_record(user_id, record)

        bank_data["last_interest_date"] = today_str
        bank_data["last_rate"] = round(last_rate * 100, 2)
        # 清理旧字段，避免重复兼容判断
        if "last_interest_time" in bank_data:
            del bank_data["last_interest_time"]
        await self._save_bank_data(user_id, bank_data)

        return total_interest

    async def _add_item_shop_index(self, item_id: str):
        try:
            idx = await self.get_kv_data(self._item_shop_index_key(), None)
            if idx is None:
                idx = []
            else:
                idx = json.loads(idx) if isinstance(idx, str) else idx
            if item_id not in idx:
                idx.append(item_id)
                await self.put_kv_data(self._item_shop_index_key(), json.dumps(idx, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"[Paywall] 更新道具商城索引失败: {e}")

    async def _add_trade_record(self, user_id: str, record: dict):
        try:
            raw = await self.get_kv_data(self._trade_key(user_id), None)
            if raw is None:
                records = []
            else:
                records = json.loads(raw) if isinstance(raw, str) else raw
            records.append(record)
            await self.put_kv_data(self._trade_key(user_id), json.dumps(records, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"[Paywall] 添加交易记录失败: {e}")

    async def _get_trade_records(self, user_id: str) -> list:
        try:
            raw = await self.get_kv_data(self._trade_key(user_id), None)
            if raw is not None and raw != "" and raw != "null":
                if isinstance(raw, str):
                    return json.loads(raw)
                elif isinstance(raw, list):
                    return raw
        except Exception:
            pass
        return []

    def _parse_args(self, event: AstrMessageEvent, cmd_name: str) -> list:
        text = event.message_str.strip()
        for prefix in [f'/{cmd_name}', cmd_name]:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                break
        return text.split()

    # ==================== LLM 拦截与扣费 ====================

    async def _init_default_shop(self):
        """初始化默认商品到商城"""
        try:
            init_flag = await self.get_kv_data("paywall_shop_initialized", None)
            if init_flag:
                return

            for item_str in self.general_items:
                parts = item_str.split(":")
                if len(parts) >= 2:
                    name = parts[0].strip()
                    price = float(parts[1].strip())
                    item_id = self._gen_item_id()
                    item = {
                        "id": item_id, "name": name, "price": price, "original_price": price,
                        "stock": 999, "seller": "system", "seller_name": "系统商店",
                        "created_at": datetime.now().isoformat(), "discount": 1.0, "shop_type": "杂货"
                    }
                    await self._save_shop_item(item_id, item)
                    await self._add_shop_index(item_id)

            for item_str in self.items:
                parts = item_str.split(":")
                if len(parts) >= 2:
                    name = parts[0].strip()
                    price = float(parts[1].strip())
                    item_id = self._gen_item_id()
                    item = {
                        "id": item_id, "name": name, "price": price, "original_price": price,
                        "stock": 999, "seller": "system", "seller_name": "系统商店",
                        "created_at": datetime.now().isoformat(), "discount": 1.0, "shop_type": "道具"
                    }
                    await self._save_item_shop_item(item_id, item)
                    await self._add_item_shop_index(item_id)

            await self.put_kv_data("paywall_shop_initialized", "true")
            logger.info(f"[Paywall] 默认商品已自动上架：百货{len(self.general_items)}件，道具{len(self.items)}件")
        except Exception as e:
            logger.warning(f"[Paywall] 初始化默认商城失败: {e}")

    # ==================== 红包系统基础方法 ====================

    def _redpacket_key(self, rp_id: str) -> str:
        return f"redpacket:{rp_id}"

    def _redpacket_index_key(self) -> str:
        return "redpacket_index"

    def _redpacket_record_key(self, user_id: str) -> str:
        return f"redpacket_record:{user_id}"

    def _gen_redpacket_id(self) -> str:
        chars = string.ascii_uppercase + string.digits
        return "RP-" + "".join(secrets.choice(chars) for _ in range(8))

    def _split_redpacket(self, total: float, count: int, rp_type: str) -> list:
        if rp_type in ["normal", "普通"]:
            base = round(total / count, 2)
            amounts = [base] * count
            remainder = round(total - sum(amounts), 2)
            i = 0
            while remainder > 0.01 and i < count:
                amounts[i] = round(amounts[i] + 0.01, 2)
                remainder = round(remainder - 0.01, 2)
                i += 1
            return amounts
        else:
            if count == 1:
                return [total]
            amounts = []
            remaining = total
            remaining_count = count
            for i in range(count - 1):
                max_val = (remaining / remaining_count) * 2
                max_val = min(max_val, remaining - 0.01 * (remaining_count - 1))
                min_val = 0.01
                if max_val < min_val:
                    max_val = min_val
                amount = round(random.uniform(min_val, max_val), 2)
                amount = min(amount, remaining - 0.01 * (remaining_count - 1))
                amount = max(amount, min_val)
                amounts.append(amount)
                remaining = round(remaining - amount, 2)
                remaining_count -= 1
            amounts.append(remaining)
            random.shuffle(amounts)
            return amounts

    async def _get_redpacket(self, rp_id: str) -> dict | None:
        try:
            raw = await self.get_kv_data(self._redpacket_key(rp_id), None)
            if raw is not None and raw != "" and raw != "null":
                if isinstance(raw, str):
                    return json.loads(raw)
                elif isinstance(raw, dict):
                    return raw
        except Exception:
            pass
        return None

    async def _save_redpacket(self, rp_id: str, data: dict):
        await self.put_kv_data(self._redpacket_key(rp_id), json.dumps(data, ensure_ascii=False))

    async def _add_redpacket_index(self, rp_id: str):
        try:
            idx = await self.get_kv_data(self._redpacket_index_key(), None)
            if idx is None:
                idx = []
            else:
                idx = json.loads(idx) if isinstance(idx, str) else idx
            if rp_id not in idx:
                idx.append(rp_id)
                await self.put_kv_data(self._redpacket_index_key(), json.dumps(idx, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"[Paywall] 更新红包索引失败: {e}")

    async def _redpacket_expiry_timer(self, rp_id: str):
        """单个红包独立定时器：24小时后自动检查并清理"""
        await asyncio.sleep(86400)
        try:
            rp = await self._get_redpacket(rp_id)
            if rp is None:
                return
            if rp["status"] == "active":
                remaining = round(rp.get("remaining", 0), 2)
                if remaining > 0:
                    sender_id = rp["sender"]
                    sender_data = await self._get_data("user", sender_id)
                    sender_data["balance"] += remaining
                    await self._save_data("user", sender_id, sender_data)
                    record = {"type": "红包退回", "rp_id": rp_id, "amount": remaining, "reason": "24小时过期自动退回", "date": datetime.now().isoformat()}
                    await self._add_redpacket_record(sender_id, record)
                    logger.info(f"[Paywall] 红包 {rp_id} 24小时过期，自动退回 {remaining:.2f} 给 {sender_id}")
                await self.put_kv_data(self._redpacket_key(rp_id), None)
                idx_raw = await self.get_kv_data(self._redpacket_index_key(), None)
                if idx_raw:
                    idx = json.loads(idx_raw) if isinstance(idx_raw, str) else idx_raw
                    if rp_id in idx:
                        idx.remove(rp_id)
                        await self.put_kv_data(self._redpacket_index_key(), json.dumps(idx, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"[Paywall] 红包 {rp_id} 定时清理异常: {e}")









    async def _check_expired_redpackets(self):
        """检查并自动退回24小时未领完的过期红包"""
        try:
            idx_raw = await self.get_kv_data(self._redpacket_index_key(), None)
            if idx_raw is None:
                return

            idx = json.loads(idx_raw) if isinstance(idx_raw, str) else idx_raw
            now = datetime.now()

            for rp_id in idx:
                rp = await self._get_redpacket(rp_id)
                if not rp or rp["status"] != "active":
                    continue

                # 检查是否过期
                expires_at_str = rp.get("expires_at", "")
                if not expires_at_str:
                    continue

                try:
                    expires_at = datetime.fromisoformat(expires_at_str)
                    if now < expires_at:
                        continue  # 还没过期
                except Exception:
                    continue

                # 已过期，退回剩余金额
                remaining = round(rp.get("remaining", 0), 2)
                if remaining > 0:
                    sender_id = rp["sender"]
                    sender_data = await self._get_data("user", sender_id)
                    sender_data["balance"] += remaining
                    await self._save_data("user", sender_id, sender_data)

                    # 记录
                    record = {
                        "type": "红包退回",
                        "rp_id": rp_id,
                        "amount": remaining,
                        "reason": "24小时过期自动退回",
                        "date": now.isoformat()
                    }
                    await self._add_redpacket_record(sender_id, record)

                    logger.info(f"[Paywall] 红包 {rp_id} 24小时过期，自动退回 {remaining:.2f} 给 {sender_id}")

                await self.put_kv_data(self._redpacket_key(rp_id), None)
                idx_raw = await self.get_kv_data(self._redpacket_index_key(), None)
                if idx_raw:
                    idx = json.loads(idx_raw) if isinstance(idx_raw, str) else idx_raw
                    if rp_id in idx:
                        idx.remove(rp_id)
                        await self.put_kv_data(self._redpacket_index_key(), json.dumps(idx, ensure_ascii=False))
                logger.info(f"[Paywall] 红包 {rp_id} 已过期，记录已删除")
        except Exception as e:
            logger.warning(f"[Paywall] 检查过期红包失败: {e}")

    async def _add_redpacket_record(self, user_id: str, record: dict):
        try:
            raw = await self.get_kv_data(self._redpacket_record_key(user_id), None)
            if raw is None:
                records = []
            else:
                records = json.loads(raw) if isinstance(raw, str) else raw
            records.append(record)
            if len(records) > 50:
                records = records[-50:]
            await self.put_kv_data(self._redpacket_record_key(user_id), json.dumps(records, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"[Paywall] 添加红包记录失败: {e}")

    @filter.on_llm_request()
    async def check_balance(self, event: AstrMessageEvent, req: ProviderRequest):
        if not self.enabled:
            return
        # 首次触发时初始化默认商城
        if not getattr(self, '_shop_initialized', False):
            await self._init_default_shop()
            self._shop_initialized = True
        sender = str(event.get_sender_id())
        if self._is_admin(sender):
            return
        if self._is_whitelist(event):
            return
        btype, bid = self._get_billing_id(event)
        data = await self._get_data(btype, bid)
        if data["balance"] <= 0:
            contact = f"如需充值请加群 {self.contact_group}" if self.contact_group else "联系管理员"
            req.system_prompt += (
                f"\n\n[系统提示] 用户积分已耗尽。"
                f"请用你当前的角色口吻，委婉地告诉用户："
                f"『哎呀，你的积分好像用完啦~想要继续聊天的话，需要{contact}充值一下哦！』"
                f"不要直接回答用户的问题，只回复欠费提示。"
            )
            req.prompt = "积分不足"
            logger.info(f"[Paywall] {btype}:{bid} 余额不足，已拦截")

    @filter.on_astrbot_loaded()
    async def on_astrbot_loaded(self):
        """AstrBot 冷启动完成后再注册一次 WebUI API（兜底）"""
        self._register_webui_api()

    @filter.on_llm_response()
    async def deduct_after(self, event: AstrMessageEvent, resp: LLMResponse):
        if not self.enabled:
            return
        sender = str(event.get_sender_id())
        if self._is_admin(sender):
            return
        if self._is_whitelist(event):
            return
        # 双重保险：确认 AI 真的返回了有效内容才扣费
        if resp is None:
            logger.warning(f"[Paywall] {sender} LLM 返回 None，跳过扣费")
            return
        # 检查是否有实际回复内容
        has_content = False
        if hasattr(resp, 'completion_text') and resp.completion_text:
            has_content = True
        elif hasattr(resp, 'raw_completion') and resp.raw_completion:
            has_content = True
        elif hasattr(resp, 'result_chain') and resp.result_chain:
            has_content = True
        if not has_content:
            logger.warning(f"[Paywall] {sender} LLM 返回空内容，跳过扣费")
            return
        btype, bid = self._get_billing_id(event)
        data = await self._get_data(btype, bid)
        cost = self.cost
        if data["balance"] < cost:
            logger.warning(f"[Paywall] {btype}:{bid} 余额不足，跳过扣费")
            return
        data["balance"] -= cost
        data["total_used"] += cost
        data["total_calls"] += 1
        await self._save_data(btype, bid, data)
        logger.info(f"[Paywall] {btype}:{bid} 调用 1 次，扣费 {cost:.2f}，剩余 {data['balance']:.2f}")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """辅助监听：仅收集 QQ 号/群号到索引，不扣费（扣费由 deduct_after 单点控制）"""
        if not self.enabled:
            return
        try:
            sender = str(event.get_sender_id())
            btype, bid = self._get_billing_id(event)
            # 自动加入索引（如果还没有数据的话）
            await self._get_data(btype, bid)
            # 如果是群聊，同时把个人也加入索引
            if btype == "group":
                await self._get_data("user", sender)
            # 简单日志，后台可见活跃 QQ 号
            msg = event.message_str.strip()[:30]
            if btype == "group":
                logger.info(f"[Paywall] 活跃 | 群:{bid} | 用户:{sender} | {msg}")
            else:
                logger.info(f"[Paywall] 活跃 | 用户:{sender} | {msg}")
        except Exception as e:
            logger.debug(f"[Paywall] 消息监听异常: {e}")

    # ==================== 余额查询 ====================

    @filter.command("pw余额")
    async def check_balance_cmd(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        if not self._is_admin(user_id):
            yield event.plain_result("❌ 权限不足，仅管理员可用")
            return

        # 获取所有用户索引
        user_idx_raw = await self.get_kv_data(self._user_index_key(), None)
        group_idx_raw = await self.get_kv_data(self._group_index_key(), None)

        user_entries = []
        group_entries = []
        total_user_balance = 0.0
        total_user_used = 0.0
        total_user_calls = 0
        total_group_balance = 0.0
        total_group_used = 0.0
        total_group_calls = 0

        if user_idx_raw:
            idx = json.loads(user_idx_raw) if isinstance(user_idx_raw, str) else user_idx_raw
            for uid in idx:
                data = await self._get_data("user", uid)
                total_user_balance += data["balance"]
                total_user_used += data["total_used"]
                total_user_calls += data["total_calls"]
                user_entries.append({
                    "id": uid,
                    "balance": data["balance"],
                    "used": data["total_used"],
                    "calls": data["total_calls"]
                })

        if group_idx_raw:
            idx = json.loads(group_idx_raw) if isinstance(group_idx_raw, str) else group_idx_raw
            for gid in idx:
                data = await self._get_data("group", gid)
                total_group_balance += data["balance"]
                total_group_used += data["total_used"]
                total_group_calls += data["total_calls"]
                group_entries.append({
                    "id": gid,
                    "balance": data["balance"],
                    "used": data["total_used"],
                    "calls": data["total_calls"]
                })

        # 按使用量降序排序，各自独立排名
        user_entries.sort(key=lambda x: x["used"], reverse=True)
        group_entries.sort(key=lambda x: x["used"], reverse=True)

        # 生成带排名序号的行
        user_lines = []
        for i, e in enumerate(user_entries[:30], 1):
            rank_emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"#{i:02d}"
            user_lines.append(f"  {rank_emoji} 👤 {e['id']}: 余额 {e['balance']:.2f} | 已用 {e['used']:.2f} | 调用 {e['calls']}次")

        group_lines = []
        for i, e in enumerate(group_entries[:30], 1):
            rank_emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"#{i:02d}"
            group_lines.append(f"  {rank_emoji} 👥 {e['id']}: 余额 {e['balance']:.2f} | 已用 {e['used']:.2f} | 调用 {e['calls']}次")

        body = "📊 全站余额统计\n━━━━━━━━━━━━━━\n"

        # 私聊用户区块
        body += f"【👤 私聊用户排名】共 {len(user_entries)}个 | 总余额: {total_user_balance:.2f} | 总消耗: {total_user_used:.2f} | 总调用: {total_user_calls}次\n"
        if user_lines:
            body += "\n".join(user_lines)
            if len(user_entries) > 30:
                body += f"\n  ... 还有 {len(user_entries)-30} 个用户未显示"
        else:
            body += "  (暂无用户数据)"
        body += "\n\n"

        # 群聊群组区块
        body += f"【👥 群聊群组排名】共 {len(group_entries)}个 | 总余额: {total_group_balance:.2f} | 总消耗: {total_group_used:.2f} | 总调用: {total_group_calls}次\n"
        if group_lines:
            body += "\n".join(group_lines)
            if len(group_entries) > 30:
                body += f"\n  ... 还有 {len(group_entries)-30} 个群组未显示"
        else:
            body += "  (暂无群组数据)"

        body += "\n━━━━━━━━━━━━━━"

        yield event.plain_result(body)
    @filter.command("pw我的余额")
    async def my_balance(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        data = await self._get_data("user", user_id)
        yield event.plain_result(f"💰 个人余额\n━━━━━━━━━━━━━━\n{self._fmt_balance(data)}\n━━━━━━━━━━━━━━")

    @filter.command("pw群余额")
    async def group_balance(self, event: AstrMessageEvent):
        if self._is_private(event):
            yield event.plain_result("❌ 此命令仅在群聊中使用")
            return
        group_id = str(event.get_group_id())
        data = await self._get_data("group", group_id)
        yield event.plain_result(f"💰 本群余额\n━━━━━━━━━━━━━━\n{self._fmt_balance(data)}\n━━━━━━━━━━━━━━\n单价: {self.cost} 积分/条")

    # ==================== 签到系统 ====================

    @filter.command("pw签到")
    async def sign_in(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        data = await self._get_data("user", user_id)
        today = datetime.now().strftime("%Y-%m-%d")

        if data.get("last_sign_date") == today:
            yield event.plain_result("❌ 今天已经签到过啦，明天再来吧~")
            return

        points = random.randint(self.sign_min, self.sign_max)
        data["balance"] += points
        data["last_sign_date"] = today
        await self._save_data("user", user_id, data)

        # 随机掉落物品（从 items + general_items 中随机挑选）
        item_msg = ""
        drop_pool = self.items + self.general_items
        if drop_pool and random.randint(1, 100) <= self.sign_item_chance:
            item_str = random.choice(drop_pool)
            parts = item_str.split(":")
            item_name = parts[0].strip() if parts else "神秘物品"
            item_price = float(parts[1].strip()) if len(parts) > 1 else 100
            inventory = await self._get_inventory(user_id)
            inventory.append({
                "name": item_name,
                "price": item_price,
                "source": "签到掉落",
                "date": today
            })
            await self._save_inventory(user_id, inventory)
            item_msg = f"\n🎁 幸运掉落: {item_name}({item_price:.0f}积分)"

        logger.info(f"[Paywall] 用户 {user_id} 签到获得 {points} 积分")
        yield event.plain_result(
            f"✅ 签到成功！\n"
            f"获得: +{points} 积分\n"
            f"当前余额: {data['balance']:.2f} 积分"
            f"{item_msg}"
        )

    @filter.command("pw群签到")
    async def group_sign_in(self, event: AstrMessageEvent):
        if self._is_private(event):
            yield event.plain_result("❌ 此命令仅在群聊中使用")
            return

        group_id = str(event.get_group_id())
        data = await self._get_data("group", group_id)
        today = datetime.now().strftime("%Y-%m-%d")

        if data.get("last_sign_date") == today:
            yield event.plain_result("❌ 本群今天已经签到过啦，明天再来吧~")
            return

        points = random.randint(self.sign_min, self.sign_max)
        data["balance"] += points
        data["last_sign_date"] = today
        await self._save_data("group", group_id, data)

        logger.info(f"[Paywall] 群 {group_id} 签到获得 {points} 积分")
        yield event.plain_result(
            f"✅ 群签到成功！\n"
            f"获得: +{points} 积分\n"
            f"本群余额: {data['balance']:.2f} 积分"
        )

    # ==================== 商城系统 ====================

    @filter.command("pw上架")
    async def list_item(self, event: AstrMessageEvent):
        parts = self._parse_args(event, "pw上架")
        if len(parts) < 1:
            yield event.plain_result("❌ 用法: /pw上架 商品名 [数量]\n道具: /pw上架 魔法药水 5\n杂货: /pw上架 自定义商品 100 5")
            return

        name = parts[0]
        seller_id = str(event.get_sender_id())

        # 判断是道具还是杂货：检查物品在哪个配置列表中
        item_config = None
        shop_type = "杂货"  # 默认百货商城

        # 先检查 items（道具列表）
        for cfg in self.items:
            cfg_parts = cfg.split(":")
            if cfg_parts[0].strip() == name:
                item_config = cfg
                shop_type = "道具"  # 在道具列表中，上架到道具商城
                break

        # 再检查 general_items（杂物列表）
        if item_config is None:
            for cfg in self.general_items:
                cfg_parts = cfg.split(":")
                if cfg_parts[0].strip() == name:
                    item_config = cfg
                    shop_type = "杂货"  # 在杂物列表中，上架到百货商城
                    break

        is_item = item_config is not None

        if is_item:
            # 道具：使用配置价格，只需要数量参数
            try:
                list_count = int(parts[1]) if len(parts) > 1 else 1
            except ValueError:
                yield event.plain_result("❌ 数量必须是整数")
                return
            cfg_parts = item_config.split(":")
            price = float(cfg_parts[1].strip()) if len(cfg_parts) > 1 else 100
            shop_type = "道具"
        else:
            # 杂货：需要价格参数
            if len(parts) < 2:
                yield event.plain_result(f"❌ 「{name}」不是道具商城物品，上架杂货需要指定价格。\n格式: /pw上架 商品名 价格 [数量]")
                return
            try:
                price = float(parts[1])
                list_count = int(parts[2]) if len(parts) > 2 else 1
            except ValueError:
                yield event.plain_result("❌ 价格必须是数字，数量必须是整数")
                return
            shop_type = "杂货"

        if price <= 0:
            yield event.plain_result("❌ 价格必须大于 0")
            return
        if list_count <= 0:
            yield event.plain_result("❌ 数量必须大于 0")
            return

        # 检查背包：非管理员必须拥有足够数量的该物品才能上架
        if not self._is_admin(seller_id):
            inventory = await self._get_inventory(seller_id)
            owned_count = sum(1 for item in inventory if item.get("name") == name)
            if owned_count < list_count:
                yield event.plain_result(f"❌ 你的背包里只有 {owned_count} 个「{name}」，无法上架 {list_count} 个。\n请通过 /pw签到 获取更多该物品。")
                return
            # 从背包中扣除相应数量的物品
            removed_count = 0
            new_inventory = []
            for item in inventory:
                if item.get("name") == name and removed_count < list_count:
                    removed_count += 1
                else:
                    new_inventory.append(item)
            await self._save_inventory(seller_id, new_inventory)

        item_id = self._gen_item_id()

        # 获取卖家昵称
        seller_data = await self._get_data("user", seller_id)
        seller_name = seller_data.get("nickname", "")
        if not seller_name:
            try:
                sender_name = event.get_sender_name()
                if sender_name:
                    seller_name = str(sender_name)
            except Exception:
                pass

        item = {
            "id": item_id,
            "name": name,
            "price": price,
            "original_price": price,
            "stock": list_count,
            "seller": seller_id,
            "seller_name": seller_name,
            "created_at": datetime.now().isoformat(),
            "discount": 1.0,
            "shop_type": shop_type
        }

        if shop_type == "道具":
            await self._save_item_shop_item(item_id, item)
            await self._add_item_shop_index(item_id)
        else:
            await self._save_shop_item(item_id, item)
            await self._add_shop_index(item_id)

        # 保存昵称到用户数据
        if seller_name:
            seller_data = await self._get_data("user", seller_id)
            if not seller_data.get("nickname"):
                seller_data["nickname"] = seller_name
                await self._save_data("user", seller_id, seller_data)

        logger.info(f"[Paywall] 用户 {seller_id} 上架{shop_type} {name} 价格 {price} 数量 {list_count}")
        yield event.plain_result(
            f"✅ 上架成功！\n"
            f"商城: {shop_type}商城\n"
            f"商品编号: {item_id}\n"
            f"名称: {name}\n"
            f"价格: {price:.2f} 积分\n"
            f"库存: {list_count}"
        )

    @filter.command("pw一键上架")
    async def bulk_list(self, event: AstrMessageEvent):
        """管理员一键上架所有默认物品"""
        admin_id = str(event.get_sender_id())
        if not self._is_admin(admin_id):
            yield event.plain_result("❌ 权限不足")
            return
        parts = self._parse_args(event, "pw一键上架")
        try:
            list_count = int(parts[0]) if parts else 1
        except ValueError:
            yield event.plain_result("❌ 数量必须是整数")
            return
        if list_count <= 0:
            yield event.plain_result("❌ 数量必须大于 0")
            return
        total = 0
        item_count = 0
        general_count = 0
        for item_str in self.items:
            parts_item = item_str.split(":")
            if len(parts_item) >= 2:
                name = parts_item[0].strip()
                price = float(parts_item[1].strip())
                item_id = self._gen_item_id()
                item = {"id": item_id, "name": name, "price": price, "original_price": price, "stock": list_count, "seller": "system", "seller_name": "系统商店", "created_at": datetime.now().isoformat(), "discount": 1.0, "shop_type": "道具"}
                await self._save_item_shop_item(item_id, item)
                await self._add_item_shop_index(item_id)
                item_count += 1
                total += 1
        for item_str in self.general_items:
            parts_item = item_str.split(":")
            if len(parts_item) >= 2:
                name = parts_item[0].strip()
                price = float(parts_item[1].strip())
                item_id = self._gen_item_id()
                item = {"id": item_id, "name": name, "price": price, "original_price": price, "stock": list_count, "seller": "system", "seller_name": "系统商店", "created_at": datetime.now().isoformat(), "discount": 1.0, "shop_type": "百货"}
                await self._save_shop_item(item_id, item)
                await self._add_shop_index(item_id)
                general_count += 1
                total += 1
        logger.info(f"[Paywall] 管理员 {admin_id} 一键上架 {total} 件商品，库存各 {list_count}")
        yield event.plain_result(f"✅ 一键上架成功！\n道具商城: {item_count} 件\n百货商城: {general_count} 件\n总计: {total} 件\n每件库存: {list_count} 个")

    @filter.command("pw百货商城")
    async def general_shop_list(self, event: AstrMessageEvent):
        """查看百货商城"""
        idx_raw = await self.get_kv_data(self._shop_index_key(), None)
        if idx_raw is None:
            yield event.plain_result("📭 百货商城暂无商品")
            return

        idx = json.loads(idx_raw) if isinstance(idx_raw, str) else idx_raw
        items = []
        for item_id in idx[-50:]:
            item = await self._get_shop_item(item_id)
            if item and item.get("stock", 0) > 0:
                discount = item.get("discount", 1.0)
                price = item["price"] * discount
                discount_tag = "" if discount >= 1.0 else f" [🔥{discount*10:.0f}折]"
                seller_name = item.get("seller_name", "")
                if not seller_name:
                    seller_data = await self._get_data("user", item["seller"])
                    seller_name = seller_data.get("nickname", item["seller"][:4] + '****' + item["seller"][-3:] if len(item["seller"]) > 7 else item["seller"])
                seller_tag = f" [👤{seller_name}]" if seller_name else ""
                items.append(f"{item_id}: {item['name']} - {price:.2f}积分 (库存{item['stock']}){discount_tag}{seller_tag}")

        if not items:
            yield event.plain_result("📭 百货商城暂无商品")
            return

        body = "\n".join(items)
        yield event.plain_result(f"📦 百货商城\n━━━━━━━━━━━━━━\n{body}\n━━━━━━━━━━━━━━\n发送 /pw购买 编号 即可购买")

    @filter.command("pw道具商城")
    async def item_shop_list(self, event: AstrMessageEvent):
        """查看道具商城"""
        idx_raw = await self.get_kv_data(self._item_shop_index_key(), None)
        if idx_raw is None:
            yield event.plain_result("📭 道具商城暂无商品")
            return

        idx = json.loads(idx_raw) if isinstance(idx_raw, str) else idx_raw
        items = []
        for item_id in idx[-50:]:
            item = await self._get_item_shop_item(item_id)
            if item and item.get("stock", 0) > 0:
                discount = item.get("discount", 1.0)
                price = item["price"] * discount
                discount_tag = "" if discount >= 1.0 else f" [🔥{discount*10:.0f}折]"
                seller_name = item.get("seller_name", "")
                if not seller_name:
                    seller_data = await self._get_data("user", item["seller"])
                    seller_name = seller_data.get("nickname", item["seller"][:4] + '****' + item["seller"][-3:] if len(item["seller"]) > 7 else item["seller"])
                seller_tag = f" [👤{seller_name}]" if seller_name else ""
                items.append(f"{item_id}: {item['name']} - {price:.2f}积分 (库存{item['stock']}){discount_tag}{seller_tag}")

        if not items:
            yield event.plain_result("📭 道具商城暂无商品")
            return

        body = "\n".join(items)
        yield event.plain_result(f"🗡️ 道具商城\n━━━━━━━━━━━━━━\n{body}\n━━━━━━━━━━━━━━\n发送 /pw购买 编号 即可购买")

    @filter.command("pw购买")
    async def buy_item(self, event: AstrMessageEvent):
        parts = self._parse_args(event, "pw购买")
        if not parts:
            yield event.plain_result("❌ 用法: /pw购买 商品编号 [数量] 或 /pw购买 商品名称 [数量]\n例如: /pw购买 ITEM-AB12CD 5\n或: /pw购买 黄金 10")
            return

        query = parts[0].strip()
        try:
            buy_count = int(parts[1]) if len(parts) > 1 else 1
        except ValueError:
            yield event.plain_result("❌ 数量必须是整数")
            return

        if buy_count <= 0:
            yield event.plain_result("❌ 数量必须大于 0")
            return

        buyer_id = str(event.get_sender_id())
        buyer_data = await self._get_data("user", buyer_id)

        # 判断是按编号还是按名称购买
        if query.upper().startswith("ITEM-"):
            # 按编号购买（精确购买单个商品）
            item_id = query.upper()
            item = await self._get_shop_item(item_id)
            shop_type = "杂货"

            if item is None:
                item = await self._get_item_shop_item(item_id)
                shop_type = "道具"

            if item is None:
                yield event.plain_result("❌ 商品不存在")
                return
            if item.get("stock", 0) <= 0:
                yield event.plain_result("❌ 该商品已售罄")
                return
            if item.get("stock", 0) < buy_count:
                yield event.plain_result(f"❌ 库存不足，该商品仅剩 {item['stock']} 个")
                return

            # 单个商品购买逻辑
            result = await self._process_single_purchase(event, buyer_id, buyer_data, item, item_id, buy_count, shop_type)
            yield event.plain_result(result)
        else:
            # 按名称购买（从多个卖家凑齐）
            # 先尝试百货商城
            player_items = []
            system_items = []
            idx_raw = await self.get_kv_data(self._shop_index_key(), None)
            if idx_raw is not None:
                idx = json.loads(idx_raw) if isinstance(idx_raw, str) else idx_raw
                for item_id in idx:
                    item = await self._get_shop_item(item_id)
                    if item and item.get("stock", 0) > 0 and item.get("name") == query:
                        if item.get("seller") == "system":
                            system_items.append((item_id, item, "杂货"))
                        else:
                            player_items.append((item_id, item, "杂货"))

            # 再尝试道具商城
            item_idx_raw = await self.get_kv_data(self._item_shop_index_key(), None)
            if item_idx_raw is not None:
                idx = json.loads(item_idx_raw) if isinstance(item_idx_raw, str) else item_idx_raw
                for item_id in idx:
                    item = await self._get_item_shop_item(item_id)
                    if item and item.get("stock", 0) > 0 and item.get("name") == query:
                        if item.get("seller") == "system":
                            system_items.append((item_id, item, "道具"))
                        else:
                            player_items.append((item_id, item, "道具"))

            # 优先购买玩家的，不够再买系统的
            target_items = player_items + system_items

            if not target_items:
                yield event.plain_result(f"❌ 商城中没有「{query}」这种商品")
                return

            # 计算总库存
            total_stock = sum(item[1].get("stock", 0) for item in target_items)
            if total_stock < buy_count:
                yield event.plain_result(f"❌ 商城中「{query}」总共只有 {total_stock} 个，无法购买 {buy_count} 个")
                return

            # 计算总价
            total_price = 0
            remaining = buy_count
            purchase_list = []  # (item_id, item, shop_type, count, price)

            for item_id, item, shop_type in target_items:
                if remaining <= 0:
                    break
                available = item.get("stock", 0)
                take = min(available, remaining)
                discount = item.get("discount", 1.0)
                price = item["price"] * discount * take
                total_price += price
                purchase_list.append((item_id, item, shop_type, take, price))
                remaining -= take

            # 检查余额
            if buyer_data["balance"] < total_price:
                yield event.plain_result(f"❌ 余额不足，需要 {total_price:.2f} 积分")
                return

            # 执行购买
            buyer_data["balance"] -= total_price
            await self._save_data("user", buyer_id, buyer_data)

            # 给每个卖家结算
            seller_summary = []
            for item_id, item, shop_type, count, price in purchase_list:
                seller_id = item["seller"]
                tax = price * (self.tax_rate / 100)
                seller_income = price - tax

                if seller_id != buyer_id:
                    seller_data = await self._get_data("user", seller_id)
                    seller_data["balance"] += seller_income
                    await self._save_data("user", seller_id, seller_data)

                # 税款给第一个管理员
                if self.admins:
                    admin_data = await self._get_data("user", self.admins[0])
                    admin_data["balance"] += tax
                    await self._save_data("user", self.admins[0], admin_data)

                # 减库存
                item["stock"] -= count
                if shop_type == "道具":
                    await self._save_item_shop_item(item_id, item)
                else:
                    await self._save_shop_item(item_id, item)

                # 交易记录
                record = {
                    "type": "购买",
                    "item": item["name"],
                    "count": count,
                    "price": price,
                    "tax": tax,
                    "date": datetime.now().isoformat()
                }
                await self._add_trade_record(buyer_id, record)

                seller_record = {
                    "type": "出售",
                    "item": item["name"],
                    "count": count,
                    "price": price,
                    "income": seller_income,
                    "tax": tax,
                    "buyer": buyer_id,
                    "date": datetime.now().isoformat()
                }
                await self._add_trade_record(seller_id, seller_record)

                seller_summary.append(f"  {item['name']} x{count} - {price:.2f}积分 (卖家{item['seller'][:4] + '****' + item['seller'][-3:] if len(item['seller']) > 7 else item['seller']})")

                # 私信通知卖家（始终发送）
                try:
                    # 构建私聊 unified_msg_origin
                    buyer_umo = event.unified_msg_origin
                    logger.info(f"[Paywall] 买家 UMO: {buyer_umo}")

                    parts_umo = buyer_umo.split(":")
                    logger.info(f"[Paywall] UMO 分段: {parts_umo}")

                    if len(parts_umo) >= 4:
                        # 群聊格式: 平台:适配器:GroupMessage:群号
                        # 私聊格式: 平台:适配器:FriendMessage:QQ号
                        seller_umo = f"{parts_umo[0]}:{parts_umo[1]}:FriendMessage:{seller_id}"
                    elif len(parts_umo) >= 3:
                        seller_umo = f"{parts_umo[0]}:{parts_umo[1]}:FriendMessage:{seller_id}"
                    else:
                        seller_umo = buyer_umo

                    logger.info(f"[Paywall] 卖家 UMO: {seller_umo}")

                    notify_msg = (
                        f"💰 商品售出通知\n"
                        f"━━━━━━━━━━━━━━\n"
                        f"你的商品「{item['name']}」被购买了！\n"
                        f"购买人: {buyer_id}\n"
                        f"数量: {count} 个\n"
                        f"售价: {price:.2f} 积分\n"
                        f"税率: {self.tax_rate}%\n"
                        f"扣税后到账: {seller_income:.2f} 积分\n"
                        f"━━━━━━━━━━━━━━"
                    )

                    # 使用 MessageChain 构建消息
                    from astrbot.api.event import MessageChain
                    message_chain = MessageChain().message(notify_msg)

                    logger.info(f"[Paywall] 正在发送私信给 {seller_id}...")
                    await self.context.send_message(seller_umo, message_chain)
                    logger.info(f"[Paywall] 私信通知已发送给 {seller_id}")
                except Exception as e:
                    logger.error(f"[Paywall] 私信通知卖家失败: {e}", exc_info=True)

            # 加买家库存
            inventory = await self._get_inventory(buyer_id)
            today = datetime.now().strftime("%Y-%m-%d")
            for _ in range(buy_count):
                inventory.append({
                    "name": query,
                    "price": total_price / buy_count,
                    "source": "购买",
                    "date": today
                })
            await self._save_inventory(buyer_id, inventory)

            logger.info(f"[Paywall] {buyer_id} 购买 {query} x{buy_count} 花费 {total_price:.2f}")

            body = "\n".join(seller_summary)
            yield event.plain_result(
                f"✅ 购买成功！\n"
                f"商品: {query} x{buy_count}\n"
                f"总花费: {total_price:.2f} 积分\n"
                f"当前余额: {buyer_data['balance']:.2f} 积分\n"
                f"\n"
                f"购买详情:\n"
                f"{body}"
            )

    async def _process_single_purchase(self, event, buyer_id, buyer_data, item, item_id, buy_count, shop_type):
        """处理单个商品的精确购买"""
        discount = item.get("discount", 1.0)
        final_price = item["price"] * discount * buy_count

        if buyer_data["balance"] < final_price:
            return f"❌ 余额不足，需要 {final_price:.2f} 积分"

        # 扣买家钱
        buyer_data["balance"] -= final_price
        await self._save_data("user", buyer_id, buyer_data)

        # 卖家到账（扣税）
        seller_id = item["seller"]
        tax = final_price * (self.tax_rate / 100)
        seller_income = final_price - tax

        # 给卖家到账（即使是自己买自己的商品）
        seller_data = await self._get_data("user", seller_id)
        seller_data["balance"] += seller_income
        await self._save_data("user", seller_id, seller_data)

        # 税款给第一个管理员（始终扣税）
        if self.admins:
            admin_data = await self._get_data("user", self.admins[0])
            admin_data["balance"] += tax
            await self._save_data("user", self.admins[0], admin_data)

        # 减库存
        item["stock"] -= buy_count
        if shop_type == "道具":
            await self._save_item_shop_item(item_id, item)
        else:
            await self._save_shop_item(item_id, item)

        # 加买家库存
        inventory = await self._get_inventory(buyer_id)
        today = datetime.now().strftime("%Y-%m-%d")
        for _ in range(buy_count):
            inventory.append({
                "name": item["name"],
                "price": item["price"],
                "source": "购买",
                "date": today
            })
        await self._save_inventory(buyer_id, inventory)

        # 交易记录
        record = {
            "type": "购买",
            "item": item["name"],
            "count": buy_count,
            "price": final_price,
            "tax": tax,
            "date": datetime.now().isoformat()
        }
        await self._add_trade_record(buyer_id, record)

        seller_record = {
            "type": "出售",
            "item": item["name"],
            "count": buy_count,
            "price": final_price,
            "income": seller_income,
            "tax": tax,
            "buyer": buyer_id,
            "date": datetime.now().isoformat()
        }
        await self._add_trade_record(seller_id, seller_record)

        logger.info(f"[Paywall] {buyer_id} 购买 {item['name']} x{buy_count} 花费 {final_price:.2f}，卖家 {seller_id} 到账 {seller_income:.2f}，税 {tax:.2f}")

        # 私信通知卖家（自己买自己也要通知）
        try:
            buyer_umo = event.unified_msg_origin
            parts_umo = buyer_umo.split(":")
            if len(parts_umo) >= 4:
                seller_umo = ":".join(parts_umo[:2]) + ":FriendMessage:" + seller_id
            else:
                seller_umo = buyer_umo

            notify_msg = (
                f"💰 商品售出通知\n"
                f"━━━━━━━━━━━━━━\n"
                f"你的商品「{item['name']}」被购买了！\n"
                f"购买人: {buyer_id}\n"
                f"数量: {buy_count} 个\n"
                f"售价: {final_price:.2f} 积分\n"
                f"税率: {self.tax_rate}%\n"
                f"扣税后到账: {seller_income:.2f} 积分\n"
                f"━━━━━━━━━━━━━━"
            )
            import astrbot.api.message_components as Comp
            chain = [Comp.Plain(notify_msg)]
            await self.context.send_message(seller_umo, chain)
        except Exception as e:
            logger.warning(f"[Paywall] 私信通知卖家失败: {e}")

        discount_msg = "" if discount >= 1.0 else f"（原价 {item['original_price']:.2f}，{discount*10:.0f}折）"
        return (
            f"✅ 购买成功！\n"
            f"商城: {shop_type}商城\n"
            f"商品: {item['name']}{discount_msg}\n"
            f"数量: {buy_count} 个\n"
            f"花费: {final_price:.2f} 积分\n"
            f"当前余额: {buyer_data['balance']:.2f} 积分"
        )

    @filter.command("pw下架")
    async def delist_item(self, event: AstrMessageEvent):
        parts = self._parse_args(event, "pw下架")
        if not parts:
            yield event.plain_result("❌ 用法: /pw下架 商品编号")
            return

        item_id = parts[0].strip().upper()
        item = await self._get_shop_item(item_id)
        if item is None:
            yield event.plain_result("❌ 商品不存在")
            return

        user_id = str(event.get_sender_id())
        if item["seller"] != user_id and not self._is_admin(user_id):
            yield event.plain_result("❌ 只有商品主人或管理员才能下架")
            return

        item["stock"] = 0
        await self._save_shop_item(item_id, item)

        logger.info(f"[Paywall] {user_id} 下架商品 {item_id}")
        yield event.plain_result(f"✅ 下架成功！\n商品: {item['name']}\n编号: {item_id}")

    @filter.command("pw我的商品")
    async def my_items(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        idx_raw = await self.get_kv_data(self._shop_index_key(), None)
        if idx_raw is None:
            yield event.plain_result("📭 你没有上架任何商品")
            return

        idx = json.loads(idx_raw) if isinstance(idx_raw, str) else idx_raw
        my_items = []
        for item_id in idx:
            item = await self._get_shop_item(item_id)
            if item and item.get("seller") == user_id and item.get("stock", 0) > 0:
                discount = item.get("discount", 1.0)
                price = item["price"] * discount
                discount_tag = "" if discount >= 1.0 else f" [🔥{discount*10:.0f}折]"
                my_items.append(f"{item_id}: {item['name']} - {price:.2f}积分 (库存{item['stock']}){discount_tag}")

        if not my_items:
            yield event.plain_result("📭 你没有上架任何商品")
            return

        body = "\n".join(my_items)
        yield event.plain_result(f"📦 我的商品\n━━━━━━━━━━━━━━\n{body}\n━━━━━━━━━━━━━━")

    @filter.command("pw背包")
    async def my_backpack(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        inventory = await self._get_inventory(user_id)
        if not inventory:
            yield event.plain_result("📭 你的背包是空的")
            return

        items = []
        for item in inventory[-30:]:
            items.append(f"{item['name']} ({item['source']} {item['date']})")

        body = "\n".join(items)
        yield event.plain_result(f"🎒 我的背包 ({len(inventory)} 件)\n━━━━━━━━━━━━━━\n{body}\n━━━━━━━━━━━━━━")
    async def _show_inventory(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        inventory = await self._get_inventory(user_id)
        if not inventory:
            yield event.plain_result("📭 你的背包是空的")
            return

        items = []
        for item in inventory[-30:]:
            items.append(f"{item['name']} ({item['source']} {item['date']})")

        body = "\n".join(items)
        yield event.plain_result(f"🎒 我的背包 ({len(inventory)} 件)\n━━━━━━━━━━━━━━\n{body}\n━━━━━━━━━━━━━━")


    @filter.command("pw出售")
    async def sell_item(self, event: AstrMessageEvent):
        """把背包物品卖给系统，价格80%（按名称出售）"""
        parts = self._parse_args(event, "pw出售")
        if not parts:
            yield event.plain_result("❌ 用法: /pw出售 物品名称 [数量]\n例如: /pw出售 魔法药水\n      /pw出售 魔法药水 5")
            return

        item_name = parts[0]
        try:
            sell_count = int(parts[1]) if len(parts) > 1 else 1
        except ValueError:
            yield event.plain_result("❌ 数量必须是整数")
            return

        if sell_count <= 0:
            yield event.plain_result("❌ 数量必须大于 0")
            return

        user_id = str(event.get_sender_id())
        inventory = await self._get_inventory(user_id)

        # 统计背包中该物品的数量
        matched = [i for i, item in enumerate(inventory) if item.get("name") == item_name]
        if not matched:
            yield event.plain_result(f"❌ 背包中没有「{item_name}」，请用 /pw背包 查看")
            return

        if len(matched) < sell_count:
            yield event.plain_result(f"❌ 背包中只有 {len(matched)} 个「{item_name}」，无法出售 {sell_count} 个")
            return

        # 计算总售价（每个物品价格的80%）
        total_original = 0.0
        removed_items = []
        # 从后往前移除，避免索引变化
        for idx in sorted(matched[:sell_count], reverse=True):
            removed = inventory.pop(idx)
            removed_items.append(removed)
            total_original += removed['price']

        await self._save_inventory(user_id, inventory)

        total_sell = total_original * 0.8

        # 加钱
        data = await self._get_data("user", user_id)
        data["balance"] += total_sell
        await self._save_data("user", user_id, data)

        # 交易记录
        record = {
            "type": "出售给系统",
            "item": item_name,
            "count": sell_count,
            "price": total_sell,
            "original_price": total_original,
            "date": datetime.now().isoformat()
        }
        await self._add_trade_record(user_id, record)

        logger.info(f"[Paywall] {user_id} 出售 {item_name} x{sell_count} 获得 {total_sell:.2f} 积分")
        yield event.plain_result(
            f"✅ 出售成功！\n"
            f"物品: {item_name} x{sell_count}\n"
            f"原价总计: {total_original:.2f} 积分\n"
            f"出售总计: {total_sell:.2f} 积分 (80%)\n"
            f"当前余额: {data['balance']:.2f} 积分"
        )

    @filter.command("pw交易记录")
    async def trade_history(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        records = await self._get_trade_records(user_id)
        if not records:
            yield event.plain_result("📭 暂无交易记录")
            return

        lines = []
        for r in records[-20:]:
            if r["type"] == "购买":
                lines.append(f"[{r['date'][:10]}] 购买 {r['item']} -{r['price']:.2f}积分")
            else:
                lines.append(f"[{r['date'][:10]}] 出售 {r['item']} +{r['income']:.2f}积分(扣税{r['tax']:.2f})")

        body = "\n".join(lines)
        yield event.plain_result(f"📋 交易记录\n━━━━━━━━━━━━━━\n{body}\n━━━━━━━━━━━━━━")

    # ==================== 打折系统（管理员） ====================

    @filter.command("pw打折")
    async def discount_item(self, event: AstrMessageEvent):
        admin_id = str(event.get_sender_id())
        if not self._is_admin(admin_id):
            yield event.plain_result("❌ 权限不足")
            return

        parts = self._parse_args(event, "pw打折")
        if len(parts) != 2:
            yield event.plain_result("❌ 用法: /pw打折 商品编号 折扣\n例如: /pw打折 ITEM-AB12CD 0.8 (8折)")
            return

        item_id = parts[0].strip().upper()
        try:
            discount = float(parts[1])
        except ValueError:
            yield event.plain_result("❌ 折扣必须是数字，如 0.8 表示8折")
            return

        if not (0.1 <= discount <= 1.0):
            yield event.plain_result("❌ 折扣必须在 0.1~1.0 之间")
            return

        item = await self._get_shop_item(item_id)
        shop_type = "百货"
        if item is None:
            item = await self._get_item_shop_item(item_id)
            shop_type = "道具"
        if item is None:
            yield event.plain_result("❌ 商品不存在")
            return
        item["discount"] = discount
        if shop_type == "道具":
            await self._save_item_shop_item(item_id, item)
        else:
            await self._save_shop_item(item_id, item)

        new_price = item["price"] * discount
        logger.info(f"[Paywall] 管理员 {admin_id} 给 {item_id} 设置 {discount*10:.0f}折")
        yield event.plain_result(
            f"✅ 打折设置成功！\n"
            f"商品: {item['name']}\n"
            f"折扣: {discount*10:.0f}折\n"
            f"现价: {new_price:.2f} 积分 (原价 {item['original_price']:.2f})"
        )

    @filter.command("pw取消打折")
    async def cancel_discount(self, event: AstrMessageEvent):
        admin_id = str(event.get_sender_id())
        if not self._is_admin(admin_id):
            yield event.plain_result("❌ 权限不足")
            return

        parts = self._parse_args(event, "pw取消打折")
        if not parts:
            yield event.plain_result("❌ 用法: /pw取消打折 商品编号")
            return

        item_id = parts[0].strip().upper()
        item = await self._get_shop_item(item_id)
        shop_type = "百货"
        if item is None:
            item = await self._get_item_shop_item(item_id)
            shop_type = "道具"
        if item is None:
            yield event.plain_result("❌ 商品不存在")
            return
        item["discount"] = 1.0
        if shop_type == "道具":
            await self._save_item_shop_item(item_id, item)
        else:
            await self._save_shop_item(item_id, item)

        logger.info(f"[Paywall] 管理员 {admin_id} 取消 {item_id} 打折")
        yield event.plain_result(f"✅ 已恢复原价！\n商品: {item['name']}\n价格: {item['price']:.2f} 积分")

    @filter.command("pw全场打折")
    async def discount_all(self, event: AstrMessageEvent):
        admin_id = str(event.get_sender_id())
        if not self._is_admin(admin_id):
            yield event.plain_result("❌ 权限不足")
            return

        parts = self._parse_args(event, "pw全场打折")
        if not parts:
            yield event.plain_result("❌ 用法: /pw全场打折 折扣\n例如: /pw全场打折 0.8")
            return

        try:
            discount = float(parts[0])
        except ValueError:
            yield event.plain_result("❌ 折扣必须是数字")
            return

        if not (0.1 <= discount <= 1.0):
            yield event.plain_result("❌ 折扣必须在 0.1~1.0 之间")
            return

        count = 0
        idx_raw = await self.get_kv_data(self._shop_index_key(), None)
        if idx_raw is not None and idx_raw != "" and idx_raw != "null":
            idx = json.loads(idx_raw) if isinstance(idx_raw, str) else idx_raw
            for item_id in idx:
                item = await self._get_shop_item(item_id)
                if item and item.get("stock", 0) > 0:
                    item["discount"] = discount
                    await self._save_shop_item(item_id, item)
                    count += 1
        item_idx_raw = await self.get_kv_data(self._item_shop_index_key(), None)
        if item_idx_raw is not None and item_idx_raw != "" and item_idx_raw != "null":
            idx = json.loads(item_idx_raw) if isinstance(item_idx_raw, str) else item_idx_raw
            for item_id in idx:
                item = await self._get_item_shop_item(item_id)
                if item and item.get("stock", 0) > 0:
                    item["discount"] = discount
                    await self._save_item_shop_item(item_id, item)
                    count += 1
        if count == 0:
            yield event.plain_result("📭 商城没有商品")
            return

        logger.info(f"[Paywall] 管理员 {admin_id} 全场 {discount*10:.0f}折，共 {count} 件商品")
        yield event.plain_result(f"✅ 全场打折设置成功！\n折扣: {discount*10:.0f}折\n影响商品: {count} 件")

    # ==================== 管理员充值 ====================

    @filter.command("pw充值")
    async def recharge(self, event: AstrMessageEvent):
        admin_id = str(event.get_sender_id())
        if not self._is_admin(admin_id):
            yield event.plain_result("❌ 您没有充值权限")
            return
        parts = self._parse_args(event, "pw充值")
        target_type = "user"
        target_id = ""
        amount = 0
        if len(parts) == 1:
            try:
                amount = float(parts[0])
            except ValueError:
                yield event.plain_result("❌ 金额必须是数字")
                return
            if self._is_private(event):
                target_id = admin_id
            else:
                target_type = "group"
                target_id = str(event.get_group_id())
        elif len(parts) >= 2:
            try:
                amount = float(parts[-1])
                target_raw = parts[0].replace("@", "").strip()
            except ValueError:
                yield event.plain_result("❌ 用法错误\n/pw充值 用户ID 1000\n/pw充值 群号 1000")
                return
            target_id = target_raw
        else:
            yield event.plain_result("❌ 用法:\n/pw充值 用户ID 1000\n/pw充值 群号 1000\n/pw充值 1000")
            return
        if amount <= 0:
            yield event.plain_result("❌ 金额必须大于 0")
            return
        data = await self._get_data(target_type, target_id)
        old_balance = data["balance"]
        data["balance"] += amount
        await self._save_data(target_type, target_id, data)
        type_name = "个人" if target_type == "user" else "群组"
        logger.info(f"[Paywall] 管理员 {admin_id} 给 {target_type}:{target_id} 充值 {amount}，余额 {old_balance:.2f} -> {data['balance']:.2f}")
        yield event.plain_result(
            f"✅ 充值成功\n"
            f"类型: {type_name}\n"
            f"对象: {target_id}\n"
            f"充值: +{amount:.2f} 积分\n"
            f"当前余额: {data['balance']:.2f} 积分"
        )

    @filter.command("pw群充值")
    async def recharge_group(self, event: AstrMessageEvent):
        admin_id = str(event.get_sender_id())
        if not self._is_admin(admin_id):
            yield event.plain_result("❌ 权限不足")
            return
        parts = self._parse_args(event, "pw群充值")
        if len(parts) != 2:
            yield event.plain_result("❌ 用法: /pw群充值 群号 金额\n例如: /pw群充值 123456789 5000")
            return
        group_id = parts[0].strip()
        try:
            amount = float(parts[1])
        except ValueError:
            yield event.plain_result("❌ 金额必须是数字")
            return
        data = await self._get_data("group", group_id)
        old_balance = data["balance"]
        data["balance"] += amount
        await self._save_data("group", group_id, data)
        logger.info(f"[Paywall] 管理员 {admin_id} 给群 {group_id} 充值 {amount}")
        yield event.plain_result(
            f"✅ 群充值成功\n"
            f"群号: {group_id}\n"
            f"充值: +{amount:.2f} 积分\n"
            f"当前余额: {data['balance']:.2f} 积分"
        )

    @filter.command("pw设置额度")
    async def set_quota(self, event: AstrMessageEvent):
        admin_id = str(event.get_sender_id())
        if not self._is_admin(admin_id):
            yield event.plain_result("❌ 权限不足")
            return
        parts = self._parse_args(event, "pw设置额度")
        if len(parts) != 2:
            yield event.plain_result("❌ 用法: /pw设置额度 用户ID 5000\n或: /pw设置额度 群号 5000")
            return
        target = parts[0].replace("@", "").strip()
        try:
            amount = float(parts[1])
        except ValueError:
            yield event.plain_result("❌ 额度必须是数字")
            return
        target_type = "group" if len(target) > 9 else "user"
        data = await self._get_data(target_type, target)
        old_balance = data["balance"]
        data["balance"] = amount
        await self._save_data(target_type, target, data)
        type_name = "个人" if target_type == "user" else "群组"
        logger.info(f"[Paywall] 管理员 {admin_id} 设置 {target_type}:{target} 额度 {amount} (原 {old_balance:.2f})")
        yield event.plain_result(
            f"✅ 额度设置成功\n"
            f"类型: {type_name}\n"
            f"对象: {target}\n"
            f"新余额: {amount:.2f} 积分 (原: {old_balance:.2f})"
        )

    # ==================== 卡密系统 ====================

    @filter.command("pw生成卡密")
    async def gen_key(self, event: AstrMessageEvent):
        admin_id = str(event.get_sender_id())
        if not self._is_admin(admin_id):
            yield event.plain_result("❌ 权限不足")
            return
        parts = self._parse_args(event, "pw生成卡密")
        if len(parts) < 1:
            yield event.plain_result("❌ 用法: /pw生成卡密 金额 [数量]\n例如:\n/pw生成卡密 1000\n/pw生成卡密 1000 5")
            return
        try:
            amount = float(parts[0])
            count = int(parts[1]) if len(parts) > 1 else 1
        except ValueError:
            yield event.plain_result("❌ 金额必须是数字，数量必须是整数")
            return
        if amount <= 0 or count <= 0 or count > 50:
            yield event.plain_result("❌ 金额和数量必须大于 0，单次最多生成 50 张")
            return
        keys = []
        for _ in range(count):
            key = self._gen_key()
            while await self._get_key_data(key) is not None:
                key = self._gen_key()
            kd = {
                "key": key,
                "amount": amount,
                "created_by": admin_id,
                "created_at": datetime.now().isoformat(),
                "used_by": None,
                "used_at": None,
                "status": "unused"
            }
            await self._save_key(key, kd)
            await self._add_key_index(key)
            keys.append(key)
        keys_str = "\n".join(keys)
        logger.info(f"[Paywall] 管理员 {admin_id} 生成 {count} 张 {amount} 积分卡密")
        yield event.plain_result(
            f"✅ 卡密生成成功\n"
            f"面额: {amount:.0f} 积分/张\n"
            f"数量: {count} 张\n"
            f"━━━━━━━━━━━━━━\n"
            f"{keys_str}\n"
            f"━━━━━━━━━━━━━━\n"
            f"用户发送: /pw兑换 卡密 即可充值"
        )

    @filter.command("pw卡密列表")
    async def list_keys(self, event: AstrMessageEvent):
        admin_id = str(event.get_sender_id())
        if not self._is_admin(admin_id):
            yield event.plain_result("❌ 权限不足")
            return
        idx_raw = await self.get_kv_data(self._index_key(), None)
        if idx_raw is None:
            yield event.plain_result("📭 当前没有未使用的卡密")
            return
        idx = json.loads(idx_raw) if isinstance(idx_raw, str) else idx_raw
        unused = []
        for key in idx[-100:]:
            kd = await self._get_key_data(key)
            if kd and kd.get("status") == "unused":
                unused.append(f"{kd['key']} ({kd['amount']:.0f}积分)")
        if not unused:
            yield event.plain_result("📭 当前没有未使用的卡密")
            return
        header = f"📋 未使用卡密列表 (共 {len(unused)} 张)\n━━━━━━━━━━━━━━\n"
        body = "\n".join(unused[:30])
        if len(unused) > 30:
            body += f"\n... 还有 {len(unused)-30} 张未显示"
        yield event.plain_result(header + body + "\n━━━━━━━━━━━━━━")

    @filter.command("pw兑换")
    async def redeem_key(self, event: AstrMessageEvent):
        """卡密兑换个人积分（私聊和群聊都可以）"""
        parts = self._parse_args(event, "pw兑换")
        if not parts:
            yield event.plain_result("❌ 用法: /pw兑换 卡密\n例如: /pw兑换 PW-AB12-CD34-EF56")
            return
        key = parts[0].strip().upper()
        kd = await self._get_key_data(key)
        if kd is None:
            yield event.plain_result("❌ 卡密不存在，请检查输入")
            return
        if kd.get("status") == "used":
            yield event.plain_result("❌ 该卡密已被使用")
            return
        # 始终兑换个人积分
        user_id = str(event.get_sender_id())
        data = await self._get_data("user", user_id)
        amount = kd["amount"]
        old_balance = data["balance"]
        data["balance"] += amount
        await self._save_data("user", user_id, data)
        kd["status"] = "used"
        kd["used_by"] = user_id
        kd["used_at"] = datetime.now().isoformat()
        await self._save_key(key, kd)
        logger.info(f"[Paywall] 卡密 {key} 被用户 {user_id} 兑换，+{amount} 积分")
        yield event.plain_result(
            f"✅ 卡密兑换成功\n"
            f"卡密: {key}\n"
            f"获得: +{amount:.0f} 积分\n"
            f"当前余额: {data['balance']:.2f} 积分 (原: {old_balance:.2f})"
        )

    @filter.command("pw群兑换")
    async def redeem_group_key(self, event: AstrMessageEvent):
        """卡密兑换群积分（仅群聊可用）"""
        parts = self._parse_args(event, "pw群兑换")
        if not parts:
            yield event.plain_result("❌ 用法: /pw群兑换 卡密\n例如: /pw群兑换 PW-AB12-CD34-EF56")
            return
        key = parts[0].strip().upper()
        kd = await self._get_key_data(key)
        if kd is None:
            yield event.plain_result("❌ 卡密不存在，请检查输入")
            return
        if kd.get("status") == "used":
            yield event.plain_result("❌ 该卡密已被使用")
            return
        # 检查是否在群聊中
        btype, bid = self._get_billing_id(event)
        if btype != "group":
            yield event.plain_result("❌ 该指令只能在群聊中使用")
            return
        data = await self._get_data("group", bid)
        amount = kd["amount"]
        old_balance = data["balance"]
        data["balance"] += amount
        await self._save_data("group", bid, data)
        kd["status"] = "used"
        kd["used_by"] = bid
        kd["used_at"] = datetime.now().isoformat()
        await self._save_key(key, kd)
        logger.info(f"[Paywall] 卡密 {key} 被群 {bid} 兑换，+{amount} 积分")
        yield event.plain_result(
            f"✅ 卡密兑换成功\n"
            f"卡密: {key}\n"
            f"获得: +{amount:.0f} 积分\n"
            f"当前群余额: {data['balance']:.2f} 积分 (原: {old_balance:.2f})"
        )


    # ========== 银行系统 ==========

    @filter.command("pw存款")
    async def bank_deposit(self, event: AstrMessageEvent):
        """存款到银行"""
        parts = self._parse_args(event, "pw存款")
        if not parts:
            yield event.plain_result("❌ 用法: /pw存款 金额\n例如: /pw存款 1000")
            return

        try:
            amount = float(parts[0])
        except ValueError:
            yield event.plain_result("❌ 金额必须是数字")
            return

        if amount <= 0:
            yield event.plain_result("❌ 金额必须大于 0")
            return

        user_id = str(event.get_sender_id())
        user_data = await self._get_data("user", user_id)

        if user_data["balance"] < amount:
            yield event.plain_result(f"❌ 余额不足，当前余额: {user_data['balance']:.2f} 积分")
            return

        # 扣除用户余额
        user_data["balance"] -= amount
        await self._save_data("user", user_id, user_data)

        # 存入银行
        bank_data = await self._get_bank_data(user_id)
        bank_data["balance"] += amount
        bank_data["total_deposit"] += amount
        if not bank_data.get("last_interest_date"):
            bank_data["last_interest_date"] = datetime.now().strftime("%Y-%m-%d")
        await self._save_bank_data(user_id, bank_data)

        # 记录
        record = {
            "type": "存款",
            "amount": amount,
            "balance": bank_data["balance"],
            "date": datetime.now().isoformat()
        }
        await self._add_bank_record(user_id, record)

        logger.info(f"[Paywall] {user_id} 存款 {amount:.2f}，银行余额: {bank_data['balance']:.2f}")
        yield event.plain_result(
            f"✅ 存款成功！\n"
            f"存入: {amount:.2f} 积分\n"
            f"银行余额: {bank_data['balance']:.2f} 积分\n"
            f"钱包余额: {user_data['balance']:.2f} 积分"
        )
    @filter.command("pw取款")
    async def bank_withdraw(self, event: AstrMessageEvent):
        """从银行取款"""
        parts = self._parse_args(event, "pw取款")
        if not parts:
            yield event.plain_result("❌ 用法: /pw取款 金额\n例如: /pw取款 500")
            return

        try:
            amount = float(parts[0])
        except ValueError:
            yield event.plain_result("❌ 金额必须是数字")
            return

        if amount <= 0:
            yield event.plain_result("❌ 金额必须大于 0")
            return

        user_id = str(event.get_sender_id())
        bank_data = await self._get_bank_data(user_id)

        if bank_data["balance"] < amount:
            yield event.plain_result(f"❌ 银行余额不足，当前银行余额: {bank_data['balance']:.2f} 积分")
            return

        # 从银行扣除
        bank_data["balance"] -= amount
        bank_data["total_withdraw"] += amount
        await self._save_bank_data(user_id, bank_data)

        # 加到用户余额
        user_data = await self._get_data("user", user_id)
        user_data["balance"] += amount
        await self._save_data("user", user_id, user_data)

        # 记录
        record = {
            "type": "取款",
            "amount": amount,
            "balance": bank_data["balance"],
            "date": datetime.now().isoformat()
        }
        await self._add_bank_record(user_id, record)

        logger.info(f"[Paywall] {user_id} 取款 {amount:.2f}，银行余额: {bank_data['balance']:.2f}")
        yield event.plain_result(
            f"✅ 取款成功！\n"
            f"取出: {amount:.2f} 积分\n"
            f"银行余额: {bank_data['balance']:.2f} 积分\n"
            f"钱包余额: {user_data['balance']:.2f} 积分"
        )
    
    @filter.command("pw转账")
    async def bank_transfer(self, event: AstrMessageEvent):
        """银行转账给其他用户，支持@提及"""
        parts = self._parse_args(event, "pw转账")
        if len(parts) < 2:
            yield event.plain_result("❌ 用法: /pw转账 用户ID 金额\n例如: /pw转账 123456789 500\n群聊中: /pw转账 @小明 500")
            return

        # 解析目标用户ID，支持@提及
        target_raw = parts[0].strip()
        if target_raw.startswith("@"):
            try:
                message_str = event.message_str if hasattr(event, 'message_str') else str(event)
                import re
                at_matches = re.findall(r'@(\d+)', message_str)
                if at_matches:
                    target_id = at_matches[0]
                else:
                    target_id = target_raw[1:].strip()
            except Exception:
                target_id = target_raw.replace("@", "").strip()
        else:
            target_id = target_raw

        try:
            amount = float(parts[1])
        except ValueError:
            yield event.plain_result("❌ 金额必须是数字")
            return

        if amount <= 0:
            yield event.plain_result("❌ 金额必须大于 0")
            return

        user_id = str(event.get_sender_id())
        if target_id == user_id:
            yield event.plain_result("❌ 不能转账给自己")
            return

        bank_data = await self._get_bank_data(user_id)
        if bank_data["balance"] < amount:
            yield event.plain_result(f"❌ 银行余额不足，当前银行余额: {bank_data['balance']:.2f} 积分")
            return

        # 扣除转账人银行余额
        bank_data["balance"] -= amount
        bank_data["total_withdraw"] += amount
        await self._save_bank_data(user_id, bank_data)

        # 加到收款人银行余额
        target_bank = await self._get_bank_data(target_id)
        target_bank["balance"] += amount
        target_bank["total_deposit"] += amount
        await self._save_bank_data(target_id, target_bank)

        # 解析留言
        message = parts[2] if len(parts) > 2 else ""
        # 记录
        now = datetime.now().isoformat()
        record = {"type": "转账转出", "amount": amount, "target": target_id, "message": message, "balance": bank_data["balance"], "date": now}
        await self._add_bank_record(user_id, record)
        target_record = {"type": "转账转入", "amount": amount, "from": user_id, "message": message, "balance": target_bank["balance"], "date": now}
        await self._add_bank_record(target_id, target_record)

        logger.info(f"[Paywall] {user_id} 转账 {amount:.2f} 给 {target_id}")
        yield event.plain_result(
            f"✅ 转账成功！\n"
            f"转出: {amount:.2f} 积分\n"
            f"收款人: {target_id}\n"
            f"银行余额: {bank_data['balance']:.2f} 积分"
        )

    @filter.command("pw银行")
    async def bank_info(self, event: AstrMessageEvent):
        """查看银行信息"""
        user_id = str(event.get_sender_id())

        # 计算利息
        interest = await self._calc_interest(user_id)

        bank_data = await self._get_bank_data(user_id)
        user_data = await self._get_data("user", user_id)

        # 获取最近记录
        try:
            raw = await self.get_kv_data(self._bank_record_key(user_id), None)
            if raw is not None:
                records = json.loads(raw) if isinstance(raw, str) else raw
                recent = records[-5:]
            else:
                recent = []
        except Exception:
            recent = []

        # 获取当天利率
        last_rate = bank_data.get("last_rate", 0)
        if last_rate == 0:
            # 如果还没生成过利率，生成一个
            last_rate = round(random.uniform(self.bank_rate_min, self.bank_rate_max) * 100, 2)
            bank_data["last_rate"] = last_rate
            await self._save_bank_data(user_id, bank_data)

        lines = [
            "🏦 银行信息",
            "━━━━━━━━━━━━━━",
            f"银行余额: {bank_data['balance']:.2f} 积分",
            f"钱包余额: {user_data['balance']:.2f} 积分",
            f"累计存款: {bank_data['total_deposit']:.2f} 积分",
            f"累计取款: {bank_data['total_withdraw']:.2f} 积分",
            f"累计利息: {bank_data['total_interest']:.2f} 积分",
            f"今日利率: {last_rate}%",
        ]

        if interest > 0:
            lines.append(f"本次利息: +{interest:.2f} 积分")

        lines.append("")
        lines.append("【最近记录】")

        if recent:
            for r in recent:
                rate_info = f" (利率{r['rate']}%)" if 'rate' in r else ""
                lines.append(f"{r['type']}: {r['amount']:+.2f}{rate_info} ({r['date'][:10]})")
        else:
            lines.append("暂无记录")

        lines.append("━━━━━━━━━━━━━━")
        lines.append(f"💡 利率范围: 每日 {self.bank_rate_min*100:.1f}% ~ {self.bank_rate_max*100:.1f}%（每天随机）")

        yield event.plain_result("\n".join(lines))


    # ==================== 红包系统指令 ====================

    @filter.command("pw发红包")
    async def send_redpacket(self, event: AstrMessageEvent):
        """发红包：/pw发红包 金额 数量 [类型]"""
        user_id = str(event.get_sender_id())
        parts = self._parse_args(event, "pw发红包")

        if len(parts) < 2:
            yield event.plain_result("❌ 用法: /pw发红包 金额 数量 [类型]\n例如: /pw发红包 100 5 (拼手气)\n      /pw发红包 100 5 普通 (均分)\n      /pw发红包 100 1 (专属)")
            return

        try:
            total = float(parts[0])
            count = int(parts[1])
            rp_type = parts[2].lower() if len(parts) > 2 else "random"
        except ValueError:
            yield event.plain_result("❌ 金额必须是数字，数量必须是整数")
            return

        if total <= 0 or count <= 0:
            yield event.plain_result("❌ 金额和数量必须大于 0")
            return

        if count > 100:
            yield event.plain_result("❌ 单次最多发 100 个红包")
            return

        if rp_type not in ["normal", "random", "普通", "拼手气"]:
            yield event.plain_result("❌ 类型只能是 普通(均分) 或 拼手气(随机)")
            return

        user_data = await self._get_data("user", user_id)
        if user_data["balance"] < total:
            yield event.plain_result(f"❌ 余额不足，需要 {total:.2f} 积分")
            return

        user_data["balance"] -= total
        await self._save_data("user", user_id, user_data)

        rp_id = self._gen_redpacket_id()
        amounts = self._split_redpacket(total, count, rp_type)

        is_group = not self._is_private(event)
        group_id = str(event.get_group_id()) if is_group else ""

        if rp_type in ["random", "拼手气"]:
            rp_type = "random"
            type_name = "拼手气"
        else:
            rp_type = "normal"
            type_name = "普通"

        # 设置24小时后过期
        expires_at = (datetime.now() + timedelta(hours=24)).isoformat()

        rp_data = {
            "id": rp_id, "sender": user_id, "total": total, "count": count,
            "remaining": total, "remaining_count": count, "amounts": amounts,
            "grabbed": [], "type": rp_type, "is_group": is_group, "group_id": group_id,
            "created_at": datetime.now().isoformat(), "expires_at": expires_at, "status": "active"
        }

        await self._save_redpacket(rp_id, rp_data)
        await self._add_redpacket_index(rp_id)
        asyncio.create_task(self._redpacket_expiry_timer(rp_id))

        record = {
            "type": "发红包", "rp_id": rp_id, "amount": total, "count": count,
            "rp_type": type_name + "红包", "date": datetime.now().isoformat()
        }
        await self._add_redpacket_record(user_id, record)

        location = f"群 {group_id}" if is_group else "私聊"

        logger.info(f"[Paywall] {user_id} 发了{type_name}红包 {rp_id} 共 {total} 积分 {count} 个")

        yield event.plain_result(
            f"🧧 红包已发出！\n━━━━━━━━━━━━━━\n红包编号: {rp_id}\n类型: {type_name}红包\n总金额: {total:.2f} 积分\n数量: {count} 个\n地点: {location}\n⏰ 24小时后未领完自动退回\n━━━━━━━━━━━━━━\n发送 /pw抢红包 {rp_id} 即可领取！"
        )

    @filter.command("pw抢红包")
    async def grab_redpacket(self, event: AstrMessageEvent):
        """抢红包：/pw抢红包 红包编号"""
        # 先检查过期红包
        await self._check_expired_redpackets()

        user_id = str(event.get_sender_id())
        parts = self._parse_args(event, "pw抢红包")

        if not parts:
            yield event.plain_result("❌ 用法: /pw抢红包 红包编号\n例如: /pw抢红包 RP-AB12CD34")
            return

        rp_id = parts[0].strip().upper()
        rp_data = await self._get_redpacket(rp_id)

        if rp_data is None:
            yield event.plain_result("❌ 红包不存在或已过期")
            return

        if rp_data["status"] != "active":
            yield event.plain_result("❌ 该红包已被抢完")
            return

        for grab in rp_data["grabbed"]:
            if grab["user"] == user_id:
                yield event.plain_result("❌ 你已经抢过这个红包了")
                return

        if rp_data["is_group"] and not self._is_private(event):
            current_group = str(event.get_group_id())
            if rp_data["group_id"] != current_group:
                yield event.plain_result("❌ 该红包不在本群，请去正确的群聊领取")
                return

        remaining_count = rp_data["remaining_count"]
        remaining = rp_data["remaining"]

        if remaining_count <= 0 or remaining <= 0.01:
            rp_data["status"] = "empty"
            await self._save_redpacket(rp_id, rp_data)
            yield event.plain_result("❌ 手慢了，红包已被抢完")
            return

        if rp_data["type"] in ["normal", "普通"]:
            amount = round(rp_data["total"] / rp_data["count"], 2)
        else:
            amounts = rp_data["amounts"]
            grabbed_amounts = [g["amount"] for g in rp_data["grabbed"]]
            available = [a for a in amounts if round(a, 2) not in [round(g, 2) for g in grabbed_amounts]]
            if not available:
                amount = round(remaining, 2) if remaining_count == 1 else round(random.uniform(0.01, remaining - 0.01 * (remaining_count - 1)), 2)
            else:
                amount = random.choice(available)

        if remaining_count == 1:
            amount = round(remaining, 2)

        amount = min(amount, remaining)
        amount = max(amount, 0.01)

        rp_data["grabbed"].append({"user": user_id, "amount": amount, "time": datetime.now().isoformat()})
        rp_data["remaining"] = round(rp_data["remaining"] - amount, 2)
        rp_data["remaining_count"] -= 1

        if rp_data["remaining_count"] <= 0 or rp_data["remaining"] <= 0.01:
            rp_data["status"] = "empty"
            await self.put_kv_data(self._redpacket_key(rp_id), None)
            idx_raw = await self.get_kv_data(self._redpacket_index_key(), None)
            if idx_raw:
                idx = json.loads(idx_raw) if isinstance(idx_raw, str) else idx_raw
                if rp_id in idx:
                    idx.remove(rp_id)
                    await self.put_kv_data(self._redpacket_index_key(), json.dumps(idx, ensure_ascii=False))
            logger.info(f"[Paywall] 红包 {rp_id} 已被抢完，记录已删除")
        else:
            await self._save_redpacket(rp_id, rp_data)

        user_data = await self._get_data("user", user_id)
        user_data["balance"] += amount
        await self._save_data("user", user_id, user_data)

        record = {
            "type": "抢红包", "rp_id": rp_id, "amount": amount,
            "sender": rp_data["sender"], "date": datetime.now().isoformat()
        }
        await self._add_redpacket_record(user_id, record)

        best_amount = max(g["amount"] for g in rp_data["grabbed"])
        is_best = amount == best_amount
        best_tag = " 🏆手气最佳！" if is_best else ""

        logger.info(f"[Paywall] {user_id} 抢到红包 {rp_id} {amount:.2f} 积分")

        yield event.plain_result(
            f"🧧 抢到红包了！{best_tag}\n━━━━━━━━━━━━━━\n红包编号: {rp_id}\n抢到: +{amount:.2f} 积分\n当前余额: {user_data['balance']:.2f} 积分\n💵 红包剩余: {rp_data['remaining']:.2f} 积分\n━━━━━━━━━━━━━━\n已抢 {len(rp_data['grabbed'])}/{rp_data['count']} 个"
        )

    @filter.command("pw红包记录")
    async def redpacket_records(self, event: AstrMessageEvent):
        """查看红包记录"""
        user_id = str(event.get_sender_id())

        try:
            raw = await self.get_kv_data(self._redpacket_record_key(user_id), None)
            if raw is None:
                yield event.plain_result("📭 暂无红包记录")
                return

            records = json.loads(raw) if isinstance(raw, str) else raw
            if not records:
                yield event.plain_result("📭 暂无红包记录")
                return

            lines = []
            total_sent = 0
            total_grabbed = 0

            for r in records[-20:]:
                t = r["type"]
                amount = r["amount"]
                d = r["date"][:10]
                if t == "发红包":
                    lines.append(f"[{d}] 发出红包 -{amount:.2f} ({r.get('count', 1)}个)")
                    total_sent += amount
                elif t == "抢红包":
                    lines.append(f"[{d}] 抢到红包 +{amount:.2f} (来自{r['sender'][:4]}****{r['sender'][-3:]})")
                    total_grabbed += amount
                elif t == "红包退回":
                    lines.append(f"[{d}] 红包退回 +{amount:.2f}")
                    total_grabbed += amount

            body = "\n".join(lines)
            yield event.plain_result(
                f"🧧 红包记录\n━━━━━━━━━━━━━━\n{body}\n━━━━━━━━━━━━━━\n累计发出: {total_sent:.2f} 积分\n累计抢到/退回: {total_grabbed:.2f} 积分"
            )
        except Exception as e:
            yield event.plain_result(f"❌ 读取记录失败: {e}")

    @filter.command("pw红包详情")
    async def redpacket_detail(self, event: AstrMessageEvent):
        """查看红包详情：/pw红包详情 红包编号"""
        # 先检查过期红包
        await self._check_expired_redpackets()

        user_id = str(event.get_sender_id())
        parts = self._parse_args(event, "pw红包详情")

        if not parts:
            yield event.plain_result("❌ 用法: /pw红包详情 红包编号\n例如: /pw红包详情 RP-AB12CD34")
            return

        rp_id = parts[0].strip().upper()
        rp_data = await self._get_redpacket(rp_id)

        if rp_data is None:
            yield event.plain_result("❌ 红包不存在")
            return

        sender_id = rp_data["sender"]
        # 只有发送者、管理员或抢过的人能查看
        is_sender = user_id == sender_id
        is_admin = self._is_admin(user_id)
        has_grabbed = any(g["user"] == user_id for g in rp_data["grabbed"])

        if not is_sender and not is_admin and not has_grabbed:
            yield event.plain_result("❌ 只有红包发送者、管理员或抢过的人才能查看")
            return

        total = rp_data["total"]
        count = rp_data["count"]
        remaining = rp_data["remaining"]
        grabbed_count = len(rp_data["grabbed"])
        status = rp_data["status"]
        rp_type = "拼手气" if rp_data["type"] == "random" else "普通"

        status_text = {
            "active": "🟢 进行中",
            "empty": "🔴 已抢完",
            "refunded": "🟡 已退回",
            "expired": "⏰ 已过期"
        }.get(status, "⚪ 未知")

        # 计算过期时间
        expires_at_str = rp_data.get("expires_at", "")
        expires_display = ""
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str)
                now = datetime.now()
                if now < expires_at:
                    hours_left = int((expires_at - now).total_seconds() / 3600)
                    expires_display = f"\n⏰ 过期时间: {expires_at_str[:16]} (还剩{hours_left}小时)"
                else:
                    expires_display = "\n⏰ 已过期"
            except Exception:
                pass

        lines = [
            f"🧧 红包详情",
            f"━━━━━━━━━━━━━━",
            f"红包编号: {rp_id}",
            f"发送者: {sender_id}",
            f"类型: {rp_type}红包",
            f"状态: {status_text}",
            f"━━━━━━━━━━━━━━",
            f"💰 总金额: {total:.2f} 积分",
            f"📦 总数量: {count} 个",
            f"✅ 已抢: {grabbed_count} 个",
            f"💵 剩余金额: {remaining:.2f} 积分"
            f"{expires_display}",
            f"━━━━━━━━━━━━━━",
            f"【领取记录】"
        ]

        if rp_data["grabbed"]:
            for g in rp_data["grabbed"]:
                uid = g["user"]
                amt = g["amount"]
                lines.append(f"  👤 {uid}: +{amt:.2f} 积分")
        else:
            lines.append("  暂无领取记录")

        lines.append("━━━━━━━━━━━━━━")

        yield event.plain_result("\n".join(lines))


    @filter.command("pw红包列表")

    async def redpacket_list(self, event: AstrMessageEvent):
        """查看当前活跃红包列表"""
        # 先检查过期红包
        await self._check_expired_redpackets()

        try:
            idx_raw = await self.get_kv_data(self._redpacket_index_key(), None)
            if idx_raw is None:
                yield event.plain_result("📭 当前没有活跃红包")
                return

            idx = json.loads(idx_raw) if isinstance(idx_raw, str) else idx_raw
            active = []

            for rp_id in idx[-30:]:
                rp = await self._get_redpacket(rp_id)
                if rp and rp["status"] == "active":
                    remaining = rp["remaining_count"]
                    total = rp["count"]
                    sender = rp["sender"]
                    rp_type = "拼手气" if rp["type"] == "random" else "普通"
                    active.append(f"{rp_id}: {rp_type}红包 剩余{remaining}/{total}个 💵{rp['remaining']:.2f}积分 (来自{sender[:4]}****{sender[-3:]})")

            if not active:
                yield event.plain_result("📭 当前没有活跃红包")
                return

            body = "\n".join(active)
            yield event.plain_result(
                f"🧧 活跃红包列表\n━━━━━━━━━━━━━━\n{body}\n━━━━━━━━━━━━━━\n发送 /pw抢红包 编号 即可领取"
            )
        except Exception as e:
            yield event.plain_result(f"❌ 读取失败: {e}")

    @filter.command("pw红包退回")
    async def refund_redpacket(self, event: AstrMessageEvent):
        """退回未抢完的红包剩余金额"""
        user_id = str(event.get_sender_id())
        parts = self._parse_args(event, "pw红包退回")

        if not parts:
            yield event.plain_result("❌ 用法: /pw红包退回 红包编号\n例如: /pw红包退回 RP-AB12CD34")
            return

        rp_id = parts[0].strip().upper()
        rp_data = await self._get_redpacket(rp_id)

        if rp_data is None:
            yield event.plain_result("❌ 红包不存在")
            return

        sender_id = rp_data["sender"]
        if not self._is_admin(user_id) and user_id != sender_id:
            yield event.plain_result("❌ 只有管理员或红包发送者才能退回")
            return

        if rp_data["status"] == "refunded":
            yield event.plain_result("❌ 该红包已退回过了")
            return

        remaining = round(rp_data.get("remaining", 0), 2)
        if remaining <= 0:
            yield event.plain_result("❌ 该红包没有剩余金额可退回（可能已被抢完）")
            return

        sender_data = await self._get_data("user", sender_id)
        sender_data["balance"] += remaining
        await self._save_data("user", sender_id, sender_data)

        rp_data["status"] = "refunded"
        rp_data["remaining"] = 0
        rp_data["remaining_count"] = 0
        rp_data["refunded_at"] = datetime.now().isoformat()
        rp_data["refunded_by"] = user_id
        await self._save_redpacket(rp_id, rp_data)

        record = {
            "type": "红包退回", "rp_id": rp_id, "amount": remaining,
            "date": datetime.now().isoformat()
        }
        await self._add_redpacket_record(sender_id, record)

        logger.info(f"[Paywall] {user_id} 退回红包 {rp_id} 剩余 {remaining:.2f} 给 {sender_id}")

        yield event.plain_result(
            f"✅ 红包已退回！\n━━━━━━━━━━━━━━\n红包编号: {rp_id}\n退回金额: {remaining:.2f} 积分（未抢完部分）\n接收人: {sender_id}\n当前余额: {sender_data['balance']:.2f} 积分\n━━━━━━━━━━━━━━"
        )
    @filter.command("pw银行记录")
    async def bank_records(self, event: AstrMessageEvent):
        """查看银行详细记录"""
        user_id = str(event.get_sender_id())

        try:
            raw = await self.get_kv_data(self._bank_record_key(user_id), None)
            if raw is None:
                yield event.plain_result("📭 暂无银行记录")
                return

            records = json.loads(raw) if isinstance(raw, str) else raw
            if not records:
                yield event.plain_result("📭 暂无银行记录")
                return

            lines = ["🏦 银行记录", "━━━━━━━━━━━━━━"]
            for r in records[-20:]:
                lines.append(f"{r['date'][:16]} | {r['type']} | {r['amount']:+.2f} | 余额: {r['balance']:.2f}")
            lines.append("━━━━━━━━━━━━━━")

            yield event.plain_result("\n".join(lines))
        except Exception as e:
            yield event.plain_result(f"❌ 读取记录失败: {e}")

    @filter.command("pw转账记录")
    async def transfer_records(self, event: AstrMessageEvent):
        """查看个人转账记录"""
        user_id = str(event.get_sender_id())
        try:
            raw = await self.get_kv_data(self._bank_record_key(user_id), None)
            if raw is None:
                yield event.plain_result("📭 暂无转账记录")
                return
            records = json.loads(raw) if isinstance(raw, str) else raw
            if not records:
                yield event.plain_result("📭 暂无转账记录")
                return
            lines = ["📋 转账记录", "━━━━━━━━━━━━━━"]
            total_out = 0
            total_in = 0
            for r in records[-20:]:
                t = r["type"]
                amount = r["amount"]
                d = r["date"][:16]
                if t == "转账转出":
                    target = r.get("target", "未知")
                    lines.append(f"[{d}] 转出 -{amount:.2f} → {target}")
                    total_out += amount
                elif t == "转账转入":
                    from_id = r.get("from", "未知")
                    lines.append(f"[{d}] 转入 +{amount:.2f} ← {from_id}")
                    total_in += amount
            if len(lines) == 2:
                yield event.plain_result("📭 暂无转账记录")
                return
            lines.append("━━━━━━━━━━━━━━")
            lines.append(f"累计转出: {total_out:.2f} 积分")
            lines.append(f"累计转入: {total_in:.2f} 积分")
            yield event.plain_result("\n".join(lines))
        except Exception as e:
            yield event.plain_result(f"❌ 读取记录失败: {e}")

    @filter.command("pw收款记录")
    async def receive_records(self, event: AstrMessageEvent):
        """查看个人收款记录（别人转给自己的）"""
        user_id = str(event.get_sender_id())
        try:
            raw = await self.get_kv_data(self._bank_record_key(user_id), None)
            if raw is None:
                yield event.plain_result("📭 暂无收款记录")
                return
            records = json.loads(raw) if isinstance(raw, str) else raw
            if not records:
                yield event.plain_result("📭 暂无收款记录")
                return
            lines = ["📥 收款记录", "━━━━━━━━━━━━━━"]
            total_in = 0
            has_record = False
            for r in records[-20:]:
                if r["type"] == "转账转入":
                    has_record = True
                    amount = r["amount"]
                    from_id = r.get("from", "未知")
                    message = r.get("message", "")
                    d = r["date"][:16]
                    msg_tag = f" 💬{message}" if message else ""
                    lines.append(f"[{d}] +{amount:.2f} ← {from_id}{msg_tag}")
                    total_in += amount
            if not has_record:
                yield event.plain_result("📭 暂无收款记录")
                return
            lines.append("━━━━━━━━━━━━━━")
            lines.append(f"累计收款: {total_in:.2f} 积分")
            yield event.plain_result("\n".join(lines))
        except Exception as e:
            yield event.plain_result(f"❌ 读取记录失败: {e}")

    @filter.command("pw管理面板")
    async def admin_panel(self, event: AstrMessageEvent):
        """获取 WebUI 管理面板地址"""
        user_id = str(event.get_sender_id())
        if not self._is_admin(user_id):
            yield event.plain_result("❌ 权限不足，仅管理员可用")
            return
        yield event.plain_result(
            "🏦 Paywall 管理面板\n"
            "━━━━━━━━━━━━━━\n"
            "请通过 AstrBot Dashboard 访问插件页面，\n"
            "或使用浏览器打开插件目录下的 pages/index.html\n"
            "━━━━━━━━━━━━━━\n"
            "功能：\n"
            "• 查看所有用户/群组余额\n"
            "• 快捷充值/扣费\n"
            "• 管理商城商品\n"
            "• 生成/查看卡密\n"
            "• 修改插件配置"
        )

    @filter.command("pw帮助")
    async def help_panel(self, event: AstrMessageEvent):
        status = "✅ 开启" if self.enabled else "❌ 关闭"
        contact = self.contact_group or "未设置"
        yield event.plain_result(
            f"🔧 Paywall 帮助面板\n"
            f"━━━━━━━━━━━━━━\n"
            f"状态: {status}\n"
            f"单价: {self.cost} 积分/条\n"
            f"私聊免费额度: {self.free_user} 积分\n"
            f"群聊免费额度: {self.free_group} 积分\n"
            f"签到范围: {self.sign_min}~{self.sign_max} 积分\n"
            f"物品掉落概率: {self.sign_item_chance}%\n"
            f"商城税率: {self.tax_rate}%\n"
            f"银行利率: {self.bank_rate_min*100:.1f}% ~ {self.bank_rate_max*100:.1f}% (每天随机)\n"
            f"如需充值请加群: {contact}\n"
            f"━━━━━━━━━━━━━━\n"
            f"【余额查询】\n"
            f"/pw余额 - 👑 查看所有用户/群余额统计\n"
            f"/pw我的余额 - 查个人余额\n"
            f"/pw群余额 - 查本群余额\n"
            f"【签到系统】\n"
            f"/pw签到介绍 - 📖 查看签到系统详细介绍\n"
            f"/pw签到 - 个人签到（积分+概率掉物品）\n"
            f"/pw群签到 - 群签到（仅积分）\n"
            f"【商城系统】\n"
            f"/pw商城介绍 - 📖 查看商城系统详细介绍\n"
            f"/pw上架 商品名 [数量] - 上架（自动识别商城）\n"
            f"/pw一键上架 [数量] - 👑 一键上架所有默认物品\n"
            f"/pw百货商城 - 查看百货商城\n"
            f"/pw道具商城 - 查看道具商城\n"
            f"/pw购买 编号/名称 [数量] - 购买商品\n"
            f"/pw下架 编号 - 下架商品\n"
            f"/pw我的商品 - 查看上架的商品\n"
            f"/pw背包 - 查看背包\n"
            f"/pw出售 物品名称 [数量] - 出售背包物品给系统（80%价格）\n"
            f"/pw交易记录 - 查看交易记录\n"
            f"【银行系统】\n"
            f"/pw银行介绍 - 📖 查看银行系统详细介绍\n"
            f"/pw存款 金额 - 存款到银行\n"
            f"/pw取款 金额 - 从银行取款\n"
            f"/pw转账 用户ID 金额 - 银行转账给其他用户\n"
            f"/pw银行 - 查看银行信息（含利息）\n"
            f"/pw银行记录 - 查看银行详细流水\n"
            f"/pw转账记录 - 查看转账记录\n"
            f"/pw收款记录 - 查看收款记录\n"
            f"【红包系统】\n"
            f"/pw红包介绍 - 📖 查看红包系统详细介绍\n"
            f"/pw发红包 金额 数量 [类型] - 发红包\n"
            f"  类型: 普通=均分, 拼手气=随机(默认)\n"
            f"/pw抢红包 编号 - 抢红包\n"
            f"/pw红包列表 - 查看活跃红包\n"
            f"/pw红包详情 编号 - 查看红包详情\n"
            f"/pw红包记录 - 查看红包记录\n"
            f"/pw红包退回 编号 - 退回未抢完的红包\n"
            f"【卡密系统】\n"
            f"/pw卡密介绍 - 📖 查看卡密系统详细介绍\n"
            f"/pw生成卡密 金额 [数量] - 👑 生成充值卡密\n"
            f"/pw卡密列表 - 👑 查看未使用卡密\n"
            f"/pw兑换 卡密 - 兑换个人积分\n"
            f"/pw群兑换 卡密 - 兑换群积分（仅群聊）\n"
            f"【计费机制】\n"
            f"/pw计费介绍 - 📖 查看计费机制详细介绍\n"
            f"【手动充值】👑 管理员\n"
            f"/pw充值 用户ID 金额\n"
            f"/pw群充值 群号 金额\n"
            f"/pw设置额度 用户ID/群号 金额\n"
            f"【打折活动】👑 管理员\n"
            f"/pw打折 编号 折扣\n"
            f"/pw取消打折 编号\n"
            f"/pw全场打折 折扣\n"
            f"【其他】\n"
            f"/pw管理面板 - 👑 获取 WebUI 地址\n"
            f"/pw帮助 - 显示本帮助\n"
            f"━━━━━━━━━━━━━━\n"
            f"👑 = 仅管理员可用"
        )


    @filter.command("pw商城介绍")
    async def shop_intro(self, event: AstrMessageEvent):
        """商城系统介绍"""
        text = (
            f"🛒 商城系统\n"
            f"━━━━━━━━━━━━━━\n"
            f"双商城: 道具商城 + 百货商城\n"
            f"交易税: {self.tax_rate}% 给管理员\n"
            f"\n"
            f"【指令】\n"
            f"/pw百货商城 - 查看百货商城\n"
            f"/pw道具商城 - 查看道具商城\n"
            f"/pw购买 编号/名称 [数量] - 购买商品\n"
            f"/pw上架 商品名 [数量] - 上架商品\n"
            f"/pw下架 编号 - 下架商品\n"
            f"/pw我的商品 - 查看上架商品\n"
            f"/pw背包 - 查看背包\n"
            f"/pw出售 名称 [数量] - 出售给系统(80%)\n"
            f"/pw交易记录 - 查看交易记录\n"
            f"\n"
            f"【管理员】\n"
            f"/pw一键上架 [数量] - 批量上架\n"
            f"/pw打折 编号 折扣 - 单个打折\n"
            f"/pw全场打折 折扣 - 全场打折"
        )
        yield event.plain_result(text)

    @filter.command("pw银行介绍")
    async def bank_intro(self, event: AstrMessageEvent):
        """银行系统介绍"""
        text = (
            f"🏦 银行系统\n"
            f"━━━━━━━━━━━━━━\n"
            f"存款计息，日利率 {self.bank_rate_min*100:.1f}%~{self.bank_rate_max*100:.1f}%\n"
            f"随时存取，无手续费\n"
            f"\n"
            f"【指令】\n"
            f"/pw存款 金额 - 存款到银行\n"
            f"/pw取款 金额 - 从银行取款\n"
            f"/pw转账 用户ID 金额 - 转账给他人\n"
            f"/pw银行 - 查看余额和利息\n"
            f"/pw银行记录 - 查看流水\n"
            f"/pw转账记录 - 查看转账记录\n"
            f"/pw收款记录 - 查看收款记录"
        )
        yield event.plain_result(text)

    @filter.command("pw红包介绍")
    async def redpacket_intro(self, event: AstrMessageEvent):
        """红包系统介绍"""
        text = (
            f"🧧 红包系统\n"
            f"━━━━━━━━━━━━━━\n"
            f"类型: 拼手气(随机) / 普通(均分)\n"
            f"有效期: 24小时，过期自动退回\n"
            f"\n"
            f"【指令】\n"
            f"/pw发红包 金额 数量 [类型] - 发红包\n"
            f"/pw抢红包 编号 - 领取红包\n"
            f"/pw红包列表 - 查看活跃红包\n"
            f"/pw红包详情 编号 - 查看详情\n"
            f"/pw红包记录 - 查看收发记录\n"
            f"/pw红包退回 编号 - 手动退回"
        )
        yield event.plain_result(text)

    @filter.command("pw卡密介绍")
    async def card_intro(self, event: AstrMessageEvent):
        """卡密系统介绍"""
        text = (
            f"🔑 卡密系统\n"
            f"━━━━━━━━━━━━━━\n"
            f"格式: PW-XXXX-XXXX-XXXX\n"
            f"\n"
            f"【用户】\n"
            f"/pw兑换 卡密 - 兑换个人积分\n"
            f"/pw群兑换 卡密 - 兑换群积分(仅群聊)\n"
            f"\n"
            f"【管理员】\n"
            f"/pw生成卡密 金额 [数量] - 生成卡密\n"
            f"/pw卡密列表 - 查看未使用卡密"
        )
        yield event.plain_result(text)

    @filter.command("pw签到介绍")
    async def sign_intro(self, event: AstrMessageEvent):
        """签到系统介绍"""
        text = (
            f"📅 签到系统\n"
            f"━━━━━━━━━━━━━━\n"
            f"个人签到: {self.sign_min}~{self.sign_max} 积分\n"
            f"掉落概率: {self.sign_item_chance}% 获得商城物品\n"
            f"群签到: 仅积分，不掉落\n"
            f"\n"
            f"【指令】\n"
            f"/pw签到 - 个人签到\n"
            f"/pw群签到 - 群签到"
        )
        yield event.plain_result(text)

    @filter.command("pw计费介绍")
    async def billing_intro(self, event: AstrMessageEvent):
        """计费机制介绍"""
        text = (
            f"💰 计费机制\n"
            f"━━━━━━━━━━━━━━\n"
            f"单价: {self.cost} 积分/条\n"
            f"私聊免费额度: {self.free_user} 积分\n"
            f"群聊免费额度: {self.free_group} 积分\n"
            f"\n"
            f"【规则】\n"
            f"• 只有触发AI回复才扣费\n"
            f"• 插件指令不扣费\n"
            f"• 管理员/白名单豁免\n"
            f"• 余额≤0时AI被拦截"
        )
        yield event.plain_result(text)

