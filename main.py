"""
AstrBot 收费插件 v4.0 - 群/私聊双维度计费 + 卡密充值 + 签到系统 + 积分商城 + 人格化欠费提示
按消息条数扣费（一积分一句话）
使用 AstrBot KV 存储
指令前缀: pw
管理员免限额
"""

import sqlite3
import json
import random
import secrets
import string
from datetime import datetime, timedelta
from typing import List, Dict
import asyncio
from collections import Counter
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.provider import ProviderRequest, LLMResponse
from astrbot.api import AstrBotConfig, logger

# ==================== 冒险系统静态数据 ====================
REGIONS = [
    (1, '🌱 新手村外围', 1, 10, 20, 5, 20, 30, 1, 3, 1, 2, 0, 0, 1, 3, '新手友好，薄雾弥漫的安全地带', '🌱 见习冒险者'),
    (2, '🌲 低语森林', 11, 20, 20, 10, 25, 25, 1, 4, 1, 2, 0, 0, 2, 4, '树木低语，草药丰富', '🌿 森林行者'),
    (3, '💧 幽暗沼泽', 21, 30, 20, 20, 30, 20, 1, 4, 1, 3, 1, 2, 3, 6, '毒气弥漫，危险重重', '🪵 沼泽猎人'),
    (4, '🔥 烈焰峡谷', 31, 40, 20, 25, 35, 15, 2, 5, 1, 3, 1, 2, 4, 8, '熔岩流淌，炙热难耐', '⚔️ 烈焰勇者'),
    (5, '❄️ 冰封雪原', 41, 50, 20, 30, 35, 15, 2, 5, 1, 3, 1, 2, 5, 10, '寒风刺骨，冰雪覆盖', '❄️ 雪域行者'),
    (6, '⛈️ 风暴高原', 51, 60, 20, 35, 40, 10, 2, 5, 1, 3, 1, 2, 6, 12, '雷霆万钧，风暴不息', '⛈️ 风暴使者'),
    (7, '🏛️ 远古遗迹', 61, 70, 20, 40, 40, 10, 2, 5, 1, 3, 1, 2, 8, 15, '古老文明，神秘莫测', '🏛️ 遗迹探索者'),
    (8, '🐉 龙之巢穴', 71, 80, 20, 45, 45, 5, 3, 5, 1, 3, 1, 2, 10, 20, '巨龙盘踞，危机四伏', '🐉 龙裔战士'),
    (9, '🌑 虚空裂隙', 81, 90, 20, 50, 45, 5, 3, 5, 2, 3, 1, 2, 15, 30, '虚空扭曲，现实破碎', '🌑 虚空行者'),
    (10, '🌳 世界树之巅', 91, 100, 20, 55, 50, 5, 3, 5, 2, 3, 1, 2, 20, 50, '世界之巅，王者领域', '👑 世界之王'),
]

ITEMS = [
    (1, '野草', 'common', 1, 2, 1, 'material', 'alchemist', 35, '随处可见的野草'),
    (2, '树枝', 'common', 1, 2, 1, 'material', 'blacksmith', 30, '干枯的树枝'),
    (3, '小石子', 'common', 1, 1, 1, 'material', 'blacksmith', 25, '普通的小石子'),
    (4, '野果', 'common', 2, 3, 1, 'material', None, 20, '酸甜的野果'),
    (5, '蘑菇', 'rare', 5, 8, 1, 'material', 'alchemist', 10, '罕见的食用蘑菇'),
    (6, '铁矿石碎片', 'rare', 8, 10, 1, 'material', 'blacksmith', 8, '铁矿石的碎块'),
    (10, '草药', 'common', 3, 5, 2, 'material', 'alchemist', 35, '制药的基础材料'),
    (11, '木材', 'common', 3, 5, 2, 'material', 'blacksmith', 30, '可用的木材'),
    (12, '树皮', 'common', 2, 4, 2, 'material', None, 25, '剥落的树皮'),
    (13, '晨露', 'rare', 10, 15, 2, 'material', 'alchemist', 12, '清晨的露水，蕴含魔力'),
    (14, '精灵花粉', 'rare', 15, 20, 2, 'material', 'alchemist', 10, '精灵花的花粉'),
    (15, '硬木', 'rare', 12, 15, 2, 'material', 'blacksmith', 8, '坚硬的木材'),
    (20, '沼泽苔藓', 'common', 5, 8, 3, 'material', 'alchemist', 35, '沼泽特有的苔藓'),
    (21, '毒蘑菇', 'common', 6, 10, 3, 'material', 'alchemist', 30, '有毒的蘑菇'),
    (22, '淤泥', 'common', 4, 6, 3, 'material', 'blacksmith', 25, '沼泽淤泥'),
    (23, '蛇蜕', 'rare', 20, 25, 3, 'material', None, 12, '蛇类蜕下的皮'),
    (24, '毒液囊', 'rare', 25, 30, 3, 'material', 'alchemist', 8, '装有毒液的囊'),
    (25, '沼泽之心', 'epic', 50, 60, 3, 'breakthrough', None, 3, '20级突破材料'),
    (30, '火成岩', 'common', 8, 12, 4, 'material', 'blacksmith', 35, '火山形成的岩石'),
    (31, '硫磺', 'common', 7, 10, 4, 'material', 'alchemist', 30, '火山的硫磺'),
    (32, '焦炭', 'common', 6, 9, 4, 'material', 'blacksmith', 25, '燃烧后的炭'),
    (33, '熔岩晶', 'rare', 30, 35, 4, 'material', 'blacksmith', 12, '熔岩凝结的晶体'),
    (34, '火焰花', 'rare', 25, 30, 4, 'material', 'alchemist', 10, '火焰中生长的花'),
    (35, '炎龙之息', 'epic', 80, 100, 4, 'breakthrough', None, 3, '30级突破材料'),
    (40, '冰晶', 'common', 12, 15, 5, 'material', None, 35, '凝结的冰晶'),
    (41, '雪莲花', 'common', 15, 18, 5, 'material', 'alchemist', 30, '雪中绽放的莲花'),
    (42, '冻土', 'common', 10, 12, 5, 'material', 'blacksmith', 25, '冻结的土壤'),
    (43, '永冻冰', 'rare', 40, 50, 5, 'material', 'blacksmith', 12, '永不融化的冰'),
    (44, '寒冰草', 'rare', 35, 45, 5, 'material', 'alchemist', 10, '寒冰中生长的草'),
    (45, '霜龙鳞', 'epic', 120, 150, 5, 'breakthrough', None, 3, '40级突破材料'),
    (50, '风信子', 'common', 18, 22, 6, 'material', 'alchemist', 35, '风中摇曳的花'),
    (51, '雷云石', 'common', 20, 25, 6, 'material', 'blacksmith', 30, '蕴含雷电的石头'),
    (52, '羽毛', 'common', 15, 18, 6, 'material', None, 25, '飞鸟的羽毛'),
    (53, '风暴眼', 'rare', 60, 80, 6, 'material', None, 12, '风暴中心的结晶'),
    (54, '雷霆晶', 'rare', 70, 90, 6, 'material', 'blacksmith', 10, '雷霆之力凝结'),
    (55, '风龙之翼', 'epic', 200, 250, 6, 'breakthrough', None, 3, '50级突破材料'),
    (60, '古陶片', 'common', 25, 30, 7, 'material', None, 35, '远古陶器的碎片'),
    (61, '符文石', 'common', 30, 35, 7, 'material', None, 30, '刻有符文的石头'),
    (62, '化石', 'common', 22, 28, 7, 'material', None, 25, '远古生物化石'),
    (63, '远古铭文', 'rare', 100, 120, 7, 'material', None, 12, '远古文字记录'),
    (64, '时光砂', 'rare', 120, 150, 7, 'material', 'alchemist', 10, '蕴含时光之力'),
    (65, '遗迹核心', 'epic', 300, 400, 7, 'breakthrough', None, 3, '60级突破材料'),
    (70, '龙鳞屑', 'common', 40, 50, 8, 'material', 'blacksmith', 35, '脱落的龙鳞碎片'),
    (71, '龙血草', 'common', 45, 55, 8, 'material', 'alchemist', 30, '龙血滋养的草'),
    (72, '龙骨碎片', 'common', 50, 60, 8, 'material', 'blacksmith', 25, '破碎的龙骨'),
    (73, '龙晶', 'rare', 200, 250, 8, 'material', 'blacksmith', 12, '龙族力量结晶'),
    (74, '龙血', 'rare', 250, 300, 8, 'material', 'alchemist', 10, '珍贵的龙血'),
    (75, '龙王之心', 'epic', 800, 1000, 8, 'breakthrough', None, 3, '70级突破材料'),
    (80, '虚空尘埃', 'common', 80, 100, 9, 'material', None, 35, '虚空飘落的尘埃'),
    (81, '裂隙石', 'common', 100, 120, 9, 'material', 'blacksmith', 30, '裂隙边缘的石头'),
    (82, '暗物质', 'common', 90, 110, 9, 'material', 'alchemist', 25, '神秘的暗物质'),
    (83, '虚空晶', 'rare', 400, 500, 9, 'material', None, 12, '虚空凝结的晶体'),
    (84, '混沌碎片', 'rare', 500, 600, 9, 'material', None, 10, '混沌的碎片'),
    (85, '虚空之核', 'epic', 1500, 2000, 9, 'breakthrough', None, 3, '80级突破材料'),
    (90, '世界树叶', 'common', 200, 250, 10, 'material', None, 35, '世界树的叶子'),
    (91, '树液', 'common', 250, 300, 10, 'material', 'alchemist', 30, '世界树的汁液'),
    (92, '古木', 'common', 300, 350, 10, 'material', 'blacksmith', 25, '世界树的木材'),
    (93, '生命精华', 'rare', 1000, 1200, 10, 'material', 'alchemist', 12, '生命之力精华'),
    (94, '世界树之种', 'rare', 1500, 1800, 10, 'material', 'blacksmith', 10, '世界树的种子'),
    (95, '世界树之心', 'epic', 5000, 5000, 10, 'breakthrough', None, 3, '90级突破材料'),
]

TITLES = [
    (1, 9, '🌱 见习冒险者'), (10, 19, '🌿 森林行者'), (20, 29, '🪵 资深猎人'),
    (30, 39, '⚔️ 烈焰勇者'), (40, 49, '❄️ 雪域行者'), (50, 59, '⛈️ 风暴使者'),
    (60, 69, '🏛️ 遗迹探索者'), (70, 79, '🐉 龙裔战士'), (80, 89, '🌑 虚空行者'),
    (90, 99, '🌳 世界守护者'), (100, 100, '👑 世界之王'),
]

BREAK_MAP = {
    10: ('初级冒险者徽章', 1), 20: ('沼泽之心', 3), 30: ('炎龙之息', 3),
    40: ('霜龙鳞', 3), 50: ('风龙之翼', 3), 60: ('遗迹核心', 3),
    70: ('龙王之心', 3), 80: ('虚空之核', 3), 90: ('世界树之心', 3),
    100: ('世界树之心', 5),
}

PROF_CONFIG = {
    'gatherer': {'name': '采集师', 'emoji': '🌿'},
    'alchemist': {'name': '制药师', 'emoji': '⚗️'},
    'blacksmith': {'name': '锻造师', 'emoji': '⚒️'}
}

PROF_LEVEL_REQ = {1: 0, 2: 500, 3: 2000}

# 配方数据 (id, 名称, 职业, 职业等级要求, 材料json, 产物id, 产物数量, 基础成功率, 描述)
RECIPES = [
    # 制药师配方
    (1, '初级体力药水', 'alchemist', 1, '{"1": 2, "4": 1}', 101, 1, 85, '恢复15点体力'),
    (2, '中级体力药水', 'alchemist', 2, '{"10": 3, "13": 1}', 102, 1, 80, '恢复30点体力'),
    (3, '高级体力药水', 'alchemist', 3, '{"20": 3, "24": 1}', 103, 1, 75, '恢复50点体力'),
    (4, '经验增幅剂', 'alchemist', 1, '{"5": 2, "14": 1}', 104, 1, 70, '下次冒险经验+25%'),
    (5, '幸运采集液', 'alchemist', 2, '{"12": 3, "15": 1}', 105, 1, 65, '下次冒险稀有率+20%'),
    (6, '危险规避散', 'alchemist', 2, '{"21": 2, "23": 1}', 106, 1, 60, '下次冒险危险率-15%'),
    # 锻造师配方
    (10, '冒险者护符', 'blacksmith', 1, '{"3": 3, "6": 1}', 110, 1, 80, '装备后经验+8%'),
    (11, '采集者手套', 'blacksmith', 1, '{"2": 3, "12": 2}', 111, 1, 75, '装备后收获数量+1'),
    (12, '防御护石', 'blacksmith', 2, '{"22": 2, "30": 1}', 112, 1, 70, '装备后危险率-5%'),
    (13, '幸运指环', 'blacksmith', 2, '{"32": 2, "33": 1}', 113, 1, 65, '装备后史诗掉率+5%'),
    (14, '大师工具箱', 'blacksmith', 3, '{"43": 2, "53": 1}', 114, 1, 60, '装备后锻造成功率+10%'),
]

# 产物物品 (id, 名称, 稀有度, 基础价格, 类型, 效果类型, 效果值, 描述, hp加成, 攻击加成, 防御加成)
CRAFT_PRODUCTS = [
    (101, '初级体力药水', 'common', 50, 'consumable', 'stamina', 15, '恢复15点体力', 0, 0, 0),
    (102, '中级体力药水', 'rare', 120, 'consumable', 'stamina', 30, '恢复30点体力', 0, 0, 0),
    (103, '高级体力药水', 'epic', 300, 'consumable', 'stamina', 50, '恢复50点体力', 0, 0, 0),
    (104, '经验增幅剂', 'rare', 150, 'consumable', 'exp_bonus', 0.25, '下次冒险经验+25%', 0, 0, 0),
    (105, '幸运采集液', 'rare', 180, 'consumable', 'rare_bonus', 0.20, '下次冒险稀有率+20%', 0, 0, 0),
    (106, '危险规避散', 'rare', 160, 'consumable', 'danger_reduce', 0.15, '下次冒险危险率-15%', 0, 0, 0),
    (110, '冒险者护符', 'rare', 200, 'equipment', 'exp_bonus', 0.08, '装备后经验+8%', 20, 0, 0),
    (111, '采集者手套', 'rare', 220, 'equipment', 'qty_bonus', 1, '装备后收获数量+1', 0, 5, 0),
    (112, '防御护石', 'epic', 350, 'equipment', 'danger_reduce', 0.05, '装备后危险率-5%', 50, 0, 10),
    (113, '幸运指环', 'epic', 400, 'equipment', 'epic_bonus', 0.05, '装备后史诗掉率+5%', 30, 8, 0),
    (114, '大师工具箱', 'epic', 500, 'equipment', 'craft_bonus', 0.10, '装备后锻造成功率+10%', 40, 0, 5),
    # 新增高级装备
    (115, '龙鳞铠甲', 'epic', 800, 'equipment', 'hp_bonus', 0.15, '装备后血量上限+15%', 100, 0, 20),
    (116, '风暴之剑', 'epic', 750, 'equipment', 'atk_bonus', 0.10, '装备后攻击+10%', 0, 25, 0),
    (117, '虚空护盾', 'legendary', 1200, 'equipment', 'def_bonus', 0.20, '装备后防御+20%', 150, 0, 30),
]




INIT_SQL = """
CREATE TABLE IF NOT EXISTS regions (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, min_level INTEGER NOT NULL,
    max_level INTEGER NOT NULL, cost REAL NOT NULL DEFAULT 20, danger_rate INTEGER DEFAULT 5,
    trigger_rate INTEGER DEFAULT 30, empty_rate INTEGER DEFAULT 20,
    qty_common_min INTEGER DEFAULT 1, qty_common_max INTEGER DEFAULT 3,
    qty_rare_min INTEGER DEFAULT 1, qty_rare_max INTEGER DEFAULT 2,
    qty_epic_min INTEGER DEFAULT 1, qty_epic_max INTEGER DEFAULT 2,
    exp_min INTEGER DEFAULT 1, exp_max INTEGER DEFAULT 3, desc TEXT, unlock_title TEXT
);
CREATE TABLE IF NOT EXISTS level_config (
    level INTEGER PRIMARY KEY, title TEXT NOT NULL, exp_needed INTEGER NOT NULL,
    is_breakthrough INTEGER DEFAULT 0, break_item TEXT, break_count INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, rarity TEXT DEFAULT 'common',
    base_price REAL DEFAULT 0, exp_value INTEGER DEFAULT 0, region_id INTEGER,
    item_type TEXT DEFAULT 'material', profession_bonus TEXT, weight INTEGER DEFAULT 10, desc TEXT
);
CREATE TABLE IF NOT EXISTS user_levels (
    user_id TEXT PRIMARY KEY, group_id TEXT, level INTEGER DEFAULT 1, exp INTEGER DEFAULT 0,
    total_exp INTEGER DEFAULT 0, profession TEXT DEFAULT 'none', profession_level INTEGER DEFAULT 1,
    profession_exp INTEGER DEFAULT 0, gather_count INTEGER DEFAULT 0, danger_count INTEGER DEFAULT 0,
    break_through_count INTEGER DEFAULT 0, last_daily_reset DATE, stamina INTEGER DEFAULT 100,
    max_stamina INTEGER DEFAULT 100, last_stamina_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    current_region INTEGER DEFAULT 1, adventure_start TIMESTAMP, adventure_region INTEGER,
    adventure_active INTEGER DEFAULT 0, adventure_last_check TIMESTAMP,
    adventure_items TEXT DEFAULT '{}', adventure_exp INTEGER DEFAULT 0, adventure_danger INTEGER DEFAULT 0,
    adventure_buffs TEXT DEFAULT '{}',
    hp INTEGER DEFAULT 100, max_hp INTEGER DEFAULT 100, attack INTEGER DEFAULT 10, defense INTEGER DEFAULT 5
);
CREATE TABLE IF NOT EXISTS inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, group_id TEXT,
    item_id INTEGER NOT NULL, quantity INTEGER DEFAULT 0, UNIQUE(user_id, group_id, item_id)
);
CREATE TABLE IF NOT EXISTS gather_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, group_id TEXT, region_id INTEGER,
    result TEXT, items_gained TEXT, exp_gained INTEGER DEFAULT 0, cost REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS recipes (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, profession TEXT NOT NULL,
    profession_level INTEGER DEFAULT 1, materials TEXT NOT NULL, product_id INTEGER NOT NULL,
    product_qty INTEGER DEFAULT 1, base_rate INTEGER DEFAULT 70, desc TEXT
);
CREATE TABLE IF NOT EXISTS user_buffs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, buff_type TEXT NOT NULL,
    buff_value REAL DEFAULT 0, buff_desc TEXT, expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS user_equipments (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, item_id INTEGER NOT NULL,
    slot TEXT DEFAULT 'accessory', equipped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, slot)
);
"""

class AdventureSystem:
    def __init__(self, db_path: str, plugin=None):
        self.db_path = db_path
        self.plugin = plugin
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.executescript(INIT_SQL)
        c.executemany('INSERT OR IGNORE INTO regions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', REGIONS)
        for lv in range(1, 101):
            exp = int(50 * (lv ** 1.5))
            is_b = 1 if lv % 10 == 0 and lv > 0 else 0
            b_item, b_cnt = (None, 0)
            if is_b and lv in BREAK_MAP:
                b_item, b_cnt = BREAK_MAP[lv]
            title = '🌱 见习冒险者'
            for s, e, t in TITLES:
                if s <= lv <= e:
                    title = t
                    break
            c.execute('INSERT OR IGNORE INTO level_config (level,title,exp_needed,is_breakthrough,break_item,break_count) VALUES (?,?,?,?,?,?)',
                      (lv, title, exp, is_b, b_item, b_cnt))
        c.executemany('INSERT OR IGNORE INTO items (id,name,rarity,base_price,exp_value,region_id,item_type,profession_bonus,weight,desc) VALUES (?,?,?,?,?,?,?,?,?,?)', ITEMS)
        # 初始化配方产物到物品表
        for pid, name, rarity, price, itype, effect, val, desc, hp_b, atk_b, def_b in CRAFT_PRODUCTS:
            c.execute('INSERT OR IGNORE INTO items (id,name,rarity,base_price,exp_value,region_id,item_type,profession_bonus,weight,desc) VALUES (?,?,?,?,0,0,?,?,0,?)',
                      (pid, name, rarity, price, itype, None, desc))
        # 初始化配方表
        for rid, name, prof, plv, mats, pid, qty, rate, desc in RECIPES:
            c.execute('INSERT OR IGNORE INTO recipes (id,name,profession,profession_level,materials,product_id,product_qty,base_rate,desc) VALUES (?,?,?,?,?,?,?,?,?)',
                      (rid, name, prof, plv, mats, pid, qty, rate, desc))
        c.execute('PRAGMA table_info(user_levels)')
        user_level_cols = {row[1] for row in c.fetchall()}
        if 'adventure_buffs' not in user_level_cols:
            c.execute("ALTER TABLE user_levels ADD COLUMN adventure_buffs TEXT DEFAULT '{}'")
        conn.commit()
        conn.close()

    # ---------- 体力 ----------
    def _recover_stamina(self, user_id: str) -> int:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT stamina,max_stamina,last_stamina_update FROM user_levels WHERE user_id=?', (user_id,))
        row = c.fetchone()
        if not row:
            conn.close(); return 100
        st, mx, last = row
        mx = mx or 100
        if last:
            last_dt = datetime.strptime(last, "%Y-%m-%d %H:%M:%S")
            mins = int((datetime.now() - last_dt).total_seconds() // 60)
            rec = mins // 5
            if rec > 0:
                st = min(mx, st + rec)
                new_t = last_dt + timedelta(minutes=rec * 5)
                c.execute('UPDATE user_levels SET stamina=?,last_stamina_update=? WHERE user_id=?',
                          (st, new_t.strftime("%Y-%m-%d %H:%M:%S"), user_id))
                conn.commit()
        conn.close()
        return st

    def _get_stamina_info(self, user_id: str) -> dict:
        st = self._recover_stamina(user_id)
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT max_stamina,last_stamina_update FROM user_levels WHERE user_id=?', (user_id,))
        row = c.fetchone()
        conn.close()
        mx, last = (row[0] or 100, row[1]) if row else (100, None)
        nxt = "已满"
        if st < mx and last:
            last_dt = datetime.strptime(last, "%Y-%m-%d %H:%M:%S")
            nxt_dt = last_dt + timedelta(minutes=5)
            if nxt_dt > datetime.now():
                sec = int((nxt_dt - datetime.now()).total_seconds())
                nxt = f"{sec//60}分{sec%60}秒"
            else:
                nxt = "即将恢复"
        return {'stamina': st, 'max': mx, 'next_recover': nxt}

    # ---------- 用户数据 ----------
    def _get_user_data(self, user_id: str, group_id: str) -> Dict:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT * FROM user_levels WHERE user_id=?', (user_id,))
        row = c.fetchone()
        if not row:
            now = datetime.now()
            c.execute('INSERT INTO user_levels (user_id,group_id,level,exp,profession,last_daily_reset,last_stamina_update) VALUES (?,?,1,0,"none",?,?)',
                      (user_id, group_id or "", now.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            c.execute('SELECT * FROM user_levels WHERE user_id=?', (user_id,))
            row = c.fetchone()
        columns = [desc[0] for desc in c.description]
        conn.close()
        data = {k: v for k, v in zip(columns, row)}
        data.setdefault('adventure_buffs', '{}')
        data.setdefault('hp', 100)
        data.setdefault('max_hp', 100)
        data.setdefault('attack', 10)
        data.setdefault('defense', 5)
        data.setdefault('last_reset', data.get('last_daily_reset'))
        data.setdefault('break_through', data.get('break_through_count', 0))
        return data

    def _get_level_config(self, level: int) -> Dict:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT * FROM level_config WHERE level=?', (level,))
        r = c.fetchone()
        conn.close()
        if r:
            return {'level': r[0], 'title': r[1], 'exp_needed': r[2], 'is_break': r[3], 'break_item': r[4], 'break_count': r[5]}
        return None

    def _get_region(self, region_id: int) -> Dict:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT * FROM regions WHERE id=?', (region_id,))
        r = c.fetchone()
        conn.close()
        if r:
            keys = ['id','name','min_level','max_level','cost','danger_rate','trigger_rate','empty_rate',
                    'qty_common_min','qty_common_max','qty_rare_min','qty_rare_max','qty_epic_min','qty_epic_max',
                    'exp_min','exp_max','desc','title']
            return {k: v for k, v in zip(keys, r)}
        return None

    def _get_region_by_level(self, level: int) -> Dict:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT * FROM regions WHERE min_level<=? AND max_level>=?', (level, level))
        r = c.fetchone()
        conn.close()
        if r:
            keys = ['id','name','min_level','max_level','cost','danger_rate','trigger_rate','empty_rate',
                    'qty_common_min','qty_common_max','qty_rare_min','qty_rare_max','qty_epic_min','qty_epic_max',
                    'exp_min','exp_max','desc','title']
            return {k: v for k, v in zip(keys, r)}
        return None

    # ---------- 冒险结算（职业加成 + 升级检测）----------
    def _calc_adventure_loot(self, user_id: str, group_id: str, force_end: bool = False) -> dict:
        user = self._get_user_data(user_id, group_id)
        if not user.get('adventure_start') or not user.get('adventure_last_check'):
            return {}
        start = datetime.strptime(user['adventure_start'], "%Y-%m-%d %H:%M:%S")
        last = datetime.strptime(user['adventure_last_check'], "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        end = start + timedelta(hours=1)
        calc_end = min(now, end)
        if force_end:
            calc_end = now
        elapsed = int((calc_end - last).total_seconds() // 60)
        if elapsed <= 0:
            return {}

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        rid = user['adventure_region']
        c.execute('SELECT trigger_rate,danger_rate,empty_rate,qty_common_min,qty_common_max,qty_rare_min,qty_rare_max,qty_epic_min,qty_epic_max,exp_min,exp_max FROM regions WHERE id=?', (rid,))
        cfg = c.fetchone()
        if not cfg:
            conn.close(); return {}
        (trig, dang, emp, cmin, cmax, rmin, rmax, emin, emax, exp_min, exp_max) = cfg

        c.execute('SELECT id,name,rarity,base_price,exp_value,weight,profession_bonus FROM items WHERE region_id=? AND item_type="material"', (rid,))
        pool = c.fetchall()
        prof = user.get('profession', 'none')
        prof_level = user.get('profession_level', 1)

        # 采集师加成
        trigger_bonus = 0
        empty_bonus = 0
        qty_bonus = 0
        if prof == 'gatherer':
            trigger_bonus = prof_level * 5
            empty_bonus = prof_level * 5
            qty_bonus = prof_level
        actual_trigger = min(100, trig + trigger_bonus)
        actual_empty = max(0, emp - empty_bonus)
        try:
            adventure_buffs = json.loads(user.get('adventure_buffs') or '{}')
        except Exception:
            adventure_buffs = {}
        exp_rate = float(adventure_buffs.get('exp_bonus', 0) or 0)
        rare_bonus = float(adventure_buffs.get('rare_bonus', 0) or 0)
        danger_reduce = float(adventure_buffs.get('danger_reduce', 0) or 0)
        actual_danger = max(0, int(round(dang * (1 - danger_reduce))))

        try:
            total_items = json.loads(user.get('adventure_items', '{}') or '{}')
            if not isinstance(total_items, dict):
                total_items = {}
        except Exception:
            total_items = {}
        total_exp = user.get('adventure_exp', 0)
        total_dang = user.get('adventure_danger', 0)
        new_items = {}
        new_exp = 0
        new_dang = 0
        prof_exp_gain = 0
        prof_result = {'leveled_up': False, 'new_level': prof_level}

        for _ in range(elapsed):
            if random.randint(1, 100) > actual_trigger:
                continue
            roll = random.randint(1, 100)
            if roll <= actual_danger:
                new_dang += 1
                new_exp += random.randint(exp_min, max(exp_min, exp_max // 2))
            elif roll <= actual_danger + actual_empty:
                new_exp += random.randint(exp_min, exp_max)
            else:
                if not pool:
                    new_exp += random.randint(exp_min, exp_max)
                    continue
                def wgt(item):
                    w = item[5]
                    if item[6] and item[6] == prof:
                        w = int(w * 1.5)
                    if rare_bonus > 0:
                        if item[2] == 'rare':
                            w = int(w * (1 + rare_bonus))
                        elif item[2] == 'epic':
                            w = int(w * (1 + rare_bonus * 1.5))
                        elif item[2] == 'legendary':
                            w = int(w * (1 + rare_bonus * 2))
                    return w
                weights = [wgt(p) for p in pool]
                tw = sum(weights)
                if tw <= 0:
                    new_exp += random.randint(exp_min, exp_max)
                    continue
                pick = random.randint(1, tw)
                cur = 0
                drop = None
                for item, w in zip(pool, weights):
                    cur += w
                    if pick <= cur:
                        drop = item
                        break
                if drop:
                    iid, name, rarity, price, ev, _, _ = drop
                    if rarity == 'common':
                        qty = random.randint(cmin, cmax)
                    elif rarity == 'rare':
                        qty = random.randint(rmin, rmax)
                    elif rarity == 'epic':
                        qty = random.randint(emin, emax)
                    else:
                        qty = 1
                    if prof == 'gatherer':
                        qty += qty_bonus
                    new_items[name] = new_items.get(name, 0) + qty
                    new_exp += ev * qty
                    prof_exp_gain += qty
                    c.execute('INSERT INTO inventory (user_id,group_id,item_id,quantity) VALUES (?,?,?,?) ON CONFLICT(user_id,group_id,item_id) DO UPDATE SET quantity=quantity+?', (user_id, group_id or "", iid, qty, qty))
                else:
                    # 遇险扣HP
                    dmg = random.randint(5, 15)
                    c.execute('SELECT hp FROM user_levels WHERE user_id=?', (user_id,))
                    hprow = c.fetchone()
                    if hprow:
                        new_hp_val = max(1, hprow[0] - dmg)
                        c.execute('UPDATE user_levels SET hp=? WHERE user_id=?', (new_hp_val, user_id))

        if exp_rate > 0 and new_exp > 0:
            new_exp = max(1, int(round(new_exp * (1 + exp_rate))))

        # 采集师职业经验（上限20）
        if prof == 'gatherer' and prof_exp_gain > 0:
            prof_exp_gain = min(prof_exp_gain, 20)
            prof_result = self._add_profession_exp(user_id, prof_exp_gain)

        for name, qty in new_items.items():
            total_items[name] = total_items.get(name, 0) + qty
        total_exp += new_exp
        total_dang += new_dang
        ended = (now >= end) or force_end
        new_last = calc_end.strftime("%Y-%m-%d %H:%M:%S")

        # 冒险结束时加经验并检测升级
        level_result = {'leveled_up': False, 'new_level': user['level'], 'need_profession': False, 'breakthrough_ready': False}
        if ended:
            c.execute('INSERT INTO gather_logs (user_id,group_id,region_id,result,items_gained,exp_gained,cost) VALUES (?,?,?,?,?,?,?)',
                      (user_id, group_id or "", rid, 'ended', json.dumps(total_items, ensure_ascii=False), total_exp, 0))
            c.execute('UPDATE user_levels SET adventure_active=0,adventure_start=NULL,adventure_region=NULL,adventure_last_check=NULL,adventure_items="{}",adventure_exp=0,adventure_danger=0,adventure_buffs="{}" WHERE user_id=?', (user_id,))
            conn.commit()
            conn.close()
            if total_exp > 0:
                level_result = self._add_exp(user_id, group_id, total_exp)
        else:
            c.execute('UPDATE user_levels SET adventure_last_check=?,adventure_items=?,adventure_exp=?,adventure_danger=? WHERE user_id=?',
                      (new_last, json.dumps(total_items, ensure_ascii=False), total_exp, total_dang, user_id))
            conn.commit()
            conn.close()

        return {
            'new_items': new_items, 'new_exp': new_exp, 'new_danger': new_dang,
            'total': total_items, 'total_exp': total_exp, 'total_danger': total_dang,
            'ended': ended, 'elapsed_min': int((calc_end - start).total_seconds() // 60),
            'remain_min': max(0, 60 - int((now - start).total_seconds() // 60)) if not ended else 0,
            'level_up': level_result.get('leveled_up', False),
            'new_level': level_result.get('new_level', user['level']),
            'need_profession': level_result.get('need_profession', False),
            'breakthrough_ready': level_result.get('breakthrough_ready', False),
            'prof_level_up': prof_result.get('leveled_up', False),
            'new_prof_level': prof_result.get('new_level', prof_level),
            'prof_exp': prof_exp_gain if prof == 'gatherer' else 0,
            'buffs': adventure_buffs,
        }

    async def _sync_adventure_items_to_kv(self, user_id: str, result: dict) -> None:
        """将冒险收获结果同步到商城背包（KV存储）。"""
        if not self.plugin or not result or not result.get('new_items'):
            return
        try:
            inv = await self.plugin._get_inventory(user_id)
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            for name, qty in result['new_items'].items():
                c.execute('SELECT base_price FROM items WHERE name=?', (name,))
                row = c.fetchone()
                price = row[0] if row else 0
                for _ in range(qty):
                    inv.append({'name': name, 'price': price, 'source': '冒险', 'date': now_str})
            conn.close()
            await self.plugin._save_inventory(user_id, inv)
        except Exception as e:
            logger.warning(f'[Paywall] 冒险物品同步失败: {e}')
    # ---------- 格式化收获报告（状态栏置顶）----------
    def _format_loot(self, result: dict, user_data: dict) -> str:
        region = self._get_region(user_data.get('adventure_region'))
        rname = region['name'] if region else "未知地区"
        rarity_emoji = {'common': '⚪', 'rare': '🔵', 'epic': '🟣', 'legendary': '🟡'}
        is_ended = result.get('ended', False)
        prof = user_data.get('profession', 'none')
        prof_level = user_data.get('profession_level', 1)

        # ===== 最上面：状态栏 =====
        config = self._get_level_config(user_data['level'])
        title = config['title'] if config else '冒险者'
        msg = f"📊 冒险等级：Lv.{user_data['level']} {title}"
        if config:
            msg += f"  经验：{user_data['exp']}/{config['exp_needed']}"
        msg += "\n"

        if prof != 'none':
            prof_name = PROF_CONFIG.get(prof, {}).get('name', prof)
            titles = {1: '初级', 2: '资深', 3: '大师'}
            pt = titles.get(prof_level, '初级')
            msg += f"🎭 职业：{pt}{prof_name} Lv.{prof_level}"
            msg += f"  经验：{user_data.get('profession_exp', 0)}"
            if prof_level < 3:
                msg += f"/{PROF_LEVEL_REQ[prof_level + 1]}"
            msg += ""

        msg += "\n"  # 空行分隔

        # ===== 冒险报告标题 =====
        msg += f"📦 **{rname} 冒险报告**"
        if is_ended:
            msg += "⏱️ 状态：冒险已结束"
        else:
            msg += f"⏱️ 状态：冒险进行中（剩余 {result.get('remain_min', 0)} 分钟）"
        msg += f"📍 地区：{rname}"

        # 遇险和经验
        if result.get('buffs', {}).get('descs'):
            msg += "🧪 药水效果：" + "、".join(result['buffs']['descs'])

        if result.get('new_danger', 0) > 0:
            msg += f"⚠️ 本次遇险：{result['new_danger']} 次"

        if is_ended:
            if result.get('new_exp', 0) > 0:
                msg += f"📖 本次冒险经验：+{result['new_exp']}"
            if result.get('prof_exp', 0) > 0 and prof == 'gatherer':
                msg += f"🎭 本次职业经验：+{result['prof_exp']}"
        else:
            if result.get('new_exp', 0) > 0:
                msg += f"📖 本次新增经验：+{result['new_exp']}"
        msg += ""

        # 本次新增
        if result.get('new_items'):
            msg += "🎒 **本次新增：**"
            for name, qty in sorted(result['new_items'].items(), key=lambda x: -x[1]):
                conn = sqlite3.connect(self.db_path)
                c = conn.cursor()
                c.execute('SELECT rarity FROM items WHERE name=?', (name,))
                r = c.fetchone()
                conn.close()
                emoji = rarity_emoji.get(r[0] if r else 'common', '⚪')
                msg += f"  {emoji} {name} x{qty}"
            msg += ""

        # 累计收获
        if result.get('total'):
            msg += "📊 **累计收获：**"
            for name, qty in sorted(result['total'].items(), key=lambda x: -x[1]):
                conn = sqlite3.connect(self.db_path)
                c = conn.cursor()
                c.execute('SELECT rarity FROM items WHERE name=?', (name,))
                r = c.fetchone()
                conn.close()
                emoji = rarity_emoji.get(r[0] if r else 'common', '⚪')
                msg += f"  {emoji} {name} x{qty}"
            msg += ""

        # 升级提示（仅结束时）
        if is_ended:
            msg += "━━━━━━━━━━━━━━"
            if result.get('level_up'):
                new_lv = result.get('new_level', user_data['level'])
                config_new = self._get_level_config(new_lv)
                title_new = config_new['title'] if config_new else '冒险者'
                msg += f"🎉 **恭喜你升级到 Lv.{new_lv}！** {title_new}"
            if result.get('need_profession'):
                msg += "🎭 **转职提示**：你已达到10级，可以转职了！"
                msg += "💡 `pw转职 [采集师/制药师/锻造师]`"
            if result.get('breakthrough_ready'):
                config_br = self._get_level_config(user_data['level'])
                if config_br and config_br['break_item']:
                    msg += f"🔒 **突破任务**：提交 `{config_br['break_item']} x{config_br['break_count']}`"
                    msg += f"💡 `pw突破` 提交材料"
            if result.get('prof_level_up'):
                prof_name = PROF_CONFIG.get(prof, {}).get('name', prof)
                new_pl = result.get('new_prof_level', prof_level)
                titles = {1: '初级', 2: '资深', 3: '大师'}
                pt = titles.get(new_pl, '初级')
                msg += f"🎭 **职业升级！** {prof_name} Lv.{new_pl}（{pt}）"
            msg += ""

        # 底部提示
        if not is_ended:
            msg += "💡 冒险继续中... 过会儿再 `pw查看收获`"

        return msg

    # ---------- 经验与升级 ----------
    def _add_exp(self, user_id: str, group_id: str, exp: int) -> Dict:
        user = self._get_user_data(user_id, group_id)
        new_exp = user['exp'] + exp
        new_total = user['total_exp'] + exp
        new_level = user['level']
        leveled_up = False
        breakthrough_ready = False
        need_profession = False
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        while True:
            config = self._get_level_config(new_level)
            if not config:
                break
            if config['is_break']:
                if new_exp >= config['exp_needed']:
                    breakthrough_ready = True
                    new_exp = config['exp_needed']
                break
            else:
                if new_exp >= config['exp_needed']:
                    new_exp -= config['exp_needed']
                    new_level += 1
                    next_config = self._get_level_config(new_level)
                    if next_config:
                        leveled_up = True
                        if new_level == 10 and user['profession'] == 'none':
                            need_profession = True
                            new_level = 9
                            new_exp = config['exp_needed']
                            leveled_up = False
                            break
                    else:
                        new_level -= 1
                        new_exp += config['exp_needed']
                        break
                else:
                    break
        # 升级时增加属性
        new_max_hp = 100 + (new_level - 1) * 10
        new_attack = 10 + (new_level - 1) * 2
        new_defense = 5 + (new_level - 1) * 1
        # HP 按比例增长，保持当前比例
        hp_ratio = user.get('hp', 100) / max(1, user.get('max_hp', 100))
        new_hp = int(new_max_hp * hp_ratio)
        c.execute('UPDATE user_levels SET level=?,exp=?,total_exp=?,gather_count=gather_count+1,max_hp=?,hp=?,attack=?,defense=? WHERE user_id=?',
                  (new_level, new_exp, new_total, new_max_hp, new_hp, new_attack, new_defense, user_id))
        conn.commit()
        conn.close()
        return {
            'leveled_up': leveled_up, 'breakthrough_ready': breakthrough_ready,
            'need_profession': need_profession, 'new_level': new_level,
            'exp': new_exp, 'next_needed': self._get_level_config(new_level)['exp_needed'] if self._get_level_config(new_level) else 0
        }

    # ---------- 职业系统 ----------
    def _add_profession_exp(self, user_id: str, exp_gain: int) -> dict:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT profession,profession_level,profession_exp FROM user_levels WHERE user_id=?', (user_id,))
        row = c.fetchone()
        if not row or row[0] == 'none':
            conn.close()
            return {'leveled_up': False, 'msg': ''}
        prof, lv, exp = row
        new_exp = exp + exp_gain
        new_lv = lv
        up_msg = ''
        while new_lv < 3:
            need = PROF_LEVEL_REQ[new_lv + 1]
            if new_exp >= need:
                new_lv += 1
                titles = {1: '初级', 2: '资深', 3: '大师'}
                up_msg = f"🎉 职业升级！{PROF_CONFIG[prof]['name']} Lv.{new_lv}（{titles.get(new_lv, '大师')}）"
            else:
                break
        c.execute('UPDATE user_levels SET profession_exp=?,profession_level=? WHERE user_id=?', (new_exp, new_lv, user_id))
        conn.commit()
        conn.close()
        return {'leveled_up': new_lv > lv, 'new_level': new_lv, 'exp': new_exp, 'msg': up_msg, 'next_need': PROF_LEVEL_REQ[new_lv + 1] if new_lv < 3 else 0}

    def change_profession(self, user_id: str, group_id: str, profession_name: str) -> dict:
        valid = {'采集师': 'gatherer', '制药师': 'alchemist', '锻造师': 'blacksmith'}
        if profession_name not in valid:
            return {'success': False, 'msg': '❌ 可选：采集师、制药师、锻造师'}
        target = valid[profession_name]
        user = self._get_user_data(user_id, group_id)
        current = user.get('profession', 'none')
        if current == target:
            lv = user.get('profession_level', 1)
            exp = user.get('profession_exp', 0)
            titles = {1: '初级', 2: '资深', 3: '大师'}
            t = titles.get(lv, '初级')
            cfg = PROF_CONFIG[target]
            msg = f"🎭 你当前是 **{cfg['emoji']} {t}{profession_name}**"
            msg += f"📖 职业等级：Lv.{lv}  经验：{exp}"
            if lv < 3:
                need = PROF_LEVEL_REQ[lv + 1]
                msg += f" / {need}（还需 {need - exp}）"
            else:
                msg += "（已满级）"
            bonuses = {
                'gatherer': f"触发率+{lv*5}%，空手率-{lv*5}%，数量+{lv}",
                'alchemist': f"制药成功率+{lv*15}%，效果+{(lv-1)*20}%",
                'blacksmith': f"锻造成功率+{lv*15}%，属性+{(lv-1)*20}%"
            }
            msg += f"✨ 加成：{bonuses[target]}"
            return {'success': True, 'msg': msg}
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('UPDATE user_levels SET profession=?,profession_level=1,profession_exp=0 WHERE user_id=?', (target, user_id))
        conn.commit()
        conn.close()
        cfg = PROF_CONFIG[target]
        msg = f"🆕 **切换职业：{cfg['emoji']} {profession_name}**"
        msg += f"📖 从 **初级（Lv.1）** 开始，经验：0"
        msg += f"⚠️ 注意：切换职业后，旧职业进度**全部清零**！"
        bonuses = {
            'gatherer': "触发率+5%，空手率-5%，数量+1（每次冒险最多+20职业经验）",
            'alchemist': "制药成功率+15%，效果+0%（失败+1~5经验，成功+合成经验）",
            'blacksmith': "锻造成功率+15%，属性+0%（失败+1~5经验，成功+合成经验）"
        }
        msg += f"💡 加成：{bonuses[target]}"
        return {'success': True, 'msg': msg}

    def get_craft_bonus(self, user_id: str, craft_type: str) -> dict:
        user = self._get_user_data(user_id, "")
        prof = user.get('profession', 'none')
        level = user.get('profession_level', 1)
        if craft_type == 'alchemist' and prof == 'alchemist':
            return {'success_rate': level * 15, 'effect_bonus': (level - 1) * 20}
        elif craft_type == 'blacksmith' and prof == 'blacksmith':
            return {'success_rate': level * 15, 'attr_bonus': (level - 1) * 20}
        return {'success_rate': 0, 'effect_bonus': 0, 'attr_bonus': 0}

    # ==================== 职业技能系统 ====================
    def _get_inventory(self, user_id: str, group_id: str) -> dict:
        """获取用户背包 {item_id: quantity}（优先使用商城背包）"""
        if self.plugin:
            import asyncio
            try:
                inv = asyncio.get_event_loop().run_until_complete(self.plugin._get_inventory(user_id))
                # 将商城背包按物品名称统计，再映射到 item_id
                conn = sqlite3.connect(self.db_path)
                c = conn.cursor()
                c.execute('SELECT id, name FROM items')
                id_name_map = {row[1]: row[0] for row in c.fetchall()}
                conn.close()
                result = {}
                for item in inv:
                    name = item.get("name", "")
                    iid = id_name_map.get(name)
                    if iid:
                        result[iid] = result.get(iid, 0) + 1
                return result
            except Exception:
                pass
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT item_id, quantity FROM inventory WHERE user_id=? AND group_id=?', (user_id, group_id or ""))
        items = {row[0]: row[1] for row in c.fetchall()}
        conn.close()
        return items

    def _remove_items(self, user_id: str, group_id: str, items_dict: dict) -> bool:
        """扣除材料，items_dict = {item_id: quantity}（优先使用商城背包）"""
        # 使用商城背包
        if self.plugin:
            import asyncio
            try:
                inv = asyncio.get_event_loop().run_until_complete(self.plugin._get_inventory(user_id))
                # 获取物品名称映射
                conn = sqlite3.connect(self.db_path)
                c = conn.cursor()
                name_map = {}
                for iid in items_dict.keys():
                    c.execute('SELECT name FROM items WHERE id=?', (int(iid),))
                    r = c.fetchone()
                    if r:
                        name_map[int(iid)] = r[0]
                conn.close()
                # 检查数量
                for iid, need_qty in items_dict.items():
                    iid = int(iid)
                    name = name_map.get(iid, '')
                    have = sum(1 for item in inv if item.get("name") == name)
                    if have < need_qty:
                        return False
                # 扣除
                for iid, need_qty in items_dict.items():
                    iid = int(iid)
                    name = name_map.get(iid, '')
                    removed = 0
                    new_inv = []
                    for item in inv:
                        if item.get("name") == name and removed < need_qty:
                            removed += 1
                        else:
                            new_inv.append(item)
                    inv = new_inv
                asyncio.get_event_loop().run_until_complete(self.plugin._save_inventory(user_id, inv))
                return True
            except Exception:
                pass
        # 回退到 SQLite
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        for iid, qty in items_dict.items():
            c.execute('SELECT quantity FROM inventory WHERE user_id=? AND group_id=? AND item_id=?', (user_id, group_id or "", iid))
            row = c.fetchone()
            if not row or row[0] < qty:
                conn.close()
                return False
        for iid, qty in items_dict.items():
            c.execute('UPDATE inventory SET quantity=quantity-? WHERE user_id=? AND group_id=? AND item_id=?', (qty, user_id, group_id or "", iid))
            c.execute('DELETE FROM inventory WHERE user_id=? AND group_id=? AND item_id=? AND quantity<=0', (user_id, group_id or "", iid))
        conn.commit()
        conn.close()
        return True

    def _add_item(self, user_id: str, group_id: str, item_id: int, qty: int):
        """添加物品到背包（优先使用商城背包系统）"""
        # 获取物品信息
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT name, base_price FROM items WHERE id=?', (item_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            return
        name, price = row
        # 使用商城背包
        if self.plugin:
            import asyncio
            try:
                inv = asyncio.get_event_loop().run_until_complete(self.plugin._get_inventory(user_id))
                today = datetime.now().strftime("%Y-%m-%d")
                for _ in range(qty):
                    inv.append({"name": name, "price": float(price), "source": "冒险采集", "date": today})
                asyncio.get_event_loop().run_until_complete(self.plugin._save_inventory(user_id, inv))
                return
            except Exception:
                pass
        # 回退到 SQLite
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('INSERT INTO inventory (user_id,group_id,item_id,quantity) VALUES (?,?,?,?) ON CONFLICT(user_id,group_id,item_id) DO UPDATE SET quantity=quantity+?', (user_id, group_id or "", item_id, qty, qty))
        conn.commit()
        conn.close()

    def _get_user_equipments(self, user_id: str) -> list:
        """获取用户已装备的物品"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT item_id, quantity FROM inventory WHERE user_id=? AND item_id >= 110', (user_id,))
        eqs = c.fetchall()
        conn.close()
        return eqs

    def _get_buffs(self, user_id: str) -> list:
        """获取用户当前有效buff"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute('SELECT buff_type, buff_value, buff_desc FROM user_buffs WHERE user_id=? AND (expires_at IS NULL OR expires_at > ?)', (user_id, now))
        buffs = c.fetchall()
        conn.close()
        return buffs

    def _take_adventure_buffs(self, user_id: str) -> dict:
        """取出一次冒险药水效果，并从待生效列表中移除。"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute('DELETE FROM user_buffs WHERE user_id=? AND expires_at IS NOT NULL AND expires_at <= ?', (user_id, now))
        c.execute('SELECT id, buff_type, buff_value, buff_desc FROM user_buffs WHERE user_id=? AND (expires_at IS NULL OR expires_at > ?)', (user_id, now))
        rows = c.fetchall()
        buff_totals = {}
        descs = []
        used_ids = []
        for buff_id, buff_type, buff_value, buff_desc in rows:
            if buff_type in ('exp_bonus', 'rare_bonus', 'danger_reduce'):
                buff_totals[buff_type] = buff_totals.get(buff_type, 0) + float(buff_value or 0)
                descs.append(buff_desc)
                used_ids.append(buff_id)
        if used_ids:
            marks = ','.join('?' for _ in used_ids)
            c.execute(f'DELETE FROM user_buffs WHERE id IN ({marks})', used_ids)
        conn.commit()
        conn.close()
        if descs:
            buff_totals['descs'] = descs
        return buff_totals

    def _add_buff(self, user_id: str, buff_type: str, buff_value: float, buff_desc: str, expires_at: str = None):
        """添加buff"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('INSERT INTO user_buffs (user_id,buff_type,buff_value,buff_desc,expires_at) VALUES (?,?,?,?,?)', (user_id, buff_type, buff_value, buff_desc, expires_at))
        conn.commit()
        conn.close()

    def craft(self, user_id: str, group_id: str, recipe_name: str) -> dict:
        """制药/锻造核心逻辑"""
        user = self._get_user_data(user_id, group_id)
        prof = user.get('profession', 'none')
        prof_level = user.get('profession_level', 1)

        # 检查职业
        if prof == 'none':
            return {'success': False, 'msg': '❌ 你尚未转职！\n💡 `pw转职 [职业名]` 选择职业'}

        # 查找配方
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT * FROM recipes WHERE name=?', (recipe_name,))
        recipe = c.fetchone()
        conn.close()

        if not recipe:
            return {'success': False, 'msg': f'❌ 找不到配方 `{recipe_name}`\n💡 `pw制药配方` 或 `pw锻造配方` 查看可制作列表'}

        rid, rname, rprof, rplv, mats_json, pid, pqty, base_rate, rdesc = recipe

        # 检查职业匹配
        if rprof != prof:
            prof_name_map = {'gatherer': '采集师', 'alchemist': '制药师', 'blacksmith': '锻造师'}
            need_prof = prof_name_map.get(rprof, rprof)
            return {'success': False, 'msg': f'❌ `{rname}` 是 **{need_prof}** 专属配方！\n你当前是 {prof_name_map.get(prof, prof)}，无法制作。'}

        # 检查职业等级
        if prof_level < rplv:
            return {'success': False, 'msg': f'❌ `{rname}` 需要 {PROF_CONFIG[rprof]["name"]} Lv.{rplv}！\n你当前 Lv.{prof_level}'}

        # 检查材料
        materials = json.loads(mats_json)
        inventory = self._get_inventory(user_id, group_id)
        missing = []
        for mid, need_qty in materials.items():
            mid = int(mid)
            have = inventory.get(mid, 0)
            if have < need_qty:
                # 获取材料名称
                conn = sqlite3.connect(self.db_path)
                c = conn.cursor()
                c.execute('SELECT name FROM items WHERE id=?', (mid,))
                mname = c.fetchone()
                conn.close()
                mname = mname[0] if mname else f'物品{mid}'
                missing.append(f'{mname} x{need_qty}（有{have}）')
        if missing:
            return {'success': False, 'msg': '❌ 材料不足！\n' + '\n'.join([f'  • {m}' for m in missing]) + '\n\n💡 `pw背包` 查看持有材料'}

        # 计算成功率
        bonus = self.get_craft_bonus(user_id, prof)
        success_rate = base_rate + bonus.get('success_rate', 0)
        # 装备加成
        eqs = self._get_user_equipments(user_id)
        for eq_id, eq_qty in eqs:
            if eq_id == 114:  # 大师工具箱
                success_rate += 10
        success_rate = min(95, success_rate)

        # 扣除材料
        if not self._remove_items(user_id, group_id, {int(k): v for k, v in materials.items()}):
            return {'success': False, 'msg': '❌ 材料扣除失败'}

        # 判定成败
        roll = random.randint(1, 100)
        if roll <= success_rate:
            # 成功
            self._add_item(user_id, group_id, pid, pqty)
            # 加职业经验
            exp_gain = random.randint(5, 15) + prof_level * 2
            prof_result = self._add_profession_exp(user_id, exp_gain)
            # 获取产物信息
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('SELECT name, rarity, item_type, desc FROM items WHERE id=?', (pid,))
            prod = c.fetchone()
            conn.close()
            if not prod:
                return {'success': True, 'msg': f"✅ **制作成功！**\n🎭 职业经验 +{exp_gain}\n⚠️ 产物信息缺失（id={pid}）"}
            pname, prarity, ptype, pdesc = prod
            rarity_emoji = {'common': '⚪', 'rare': '🔵', 'epic': '🟣'}
            emoji = rarity_emoji.get(prarity, '⚪')
            msg = f"✅ **制作成功！**\n"
            msg += f"{emoji} {pname} x{pqty}\n"
            msg += f"📖 {pdesc}\n"
            msg += f"🎭 职业经验 +{exp_gain}\n"
            if prof_result.get('leveled_up'):
                titles = {1: '初级', 2: '资深', 3: '大师'}
                pt = titles.get(prof_result['new_level'], '大师')
                msg += f"🎉 **职业升级！** {PROF_CONFIG[prof]['name']} Lv.{prof_result['new_level']}（{pt}）\n"
            msg += f"\n📊 成功率：{success_rate}%（判定 {roll}）"
            return {'success': True, 'msg': msg}
        else:
            # 失败
            exp_gain = random.randint(1, 5)
            prof_result = self._add_profession_exp(user_id, exp_gain)
            msg = f"❌ **制作失败...**\n"
            msg += f"🎭 职业经验 +{exp_gain}（失败也有成长）\n"
            if prof_result.get('leveled_up'):
                titles = {1: '初级', 2: '资深', 3: '大师'}
                pt = titles.get(prof_result['new_level'], '大师')
                msg += f"🎉 **职业升级！** {PROF_CONFIG[prof]['name']} Lv.{prof_result['new_level']}（{pt}）\n"
            msg += f"\n📊 成功率：{success_rate}%（判定 {roll}）\n"
            msg += f"💡 提升职业等级或装备「大师工具箱」可提高成功率"
            return {'success': False, 'msg': msg}

    def get_recipes(self, user_id: str, group_id: str) -> dict:
        """获取当前职业可制作的配方列表"""
        user = self._get_user_data(user_id, group_id)
        prof = user.get('profession', 'none')
        prof_level = user.get('profession_level', 1)

        if prof == 'none':
            return {'success': False, 'msg': '❌ 你尚未转职！\n💡 `pw转职 [职业名]` 选择职业'}

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT * FROM recipes WHERE profession=? ORDER BY profession_level, id', (prof,))
        recipes = c.fetchall()
        conn.close()

        if not recipes:
            return {'success': True, 'msg': '暂无可用配方'}

        prof_name = PROF_CONFIG[prof]['name']
        msg = f"🎭 **{prof_name} 配方列表**（Lv.{prof_level}）\n\n"
        inventory = self._get_inventory(user_id, group_id)
        bonus = self.get_craft_bonus(user_id, prof)

        for rid, rname, rprof, rplv, mats_json, pid, pqty, base_rate, rdesc in recipes:
            status = '🔓' if prof_level >= rplv else '🔒'
            rate = min(95, base_rate + bonus.get('success_rate', 0))
            # 检查材料
            mats = json.loads(mats_json)
            can_make = True
            mat_strs = []
            for mid, need in mats.items():
                mid = int(mid)
                have = inventory.get(mid, 0)
                conn = sqlite3.connect(self.db_path)
                c = conn.cursor()
                c.execute('SELECT name FROM items WHERE id=?', (mid,))
                mname = c.fetchone()
                conn.close()
                mname = mname[0] if mname else f'物品{mid}'
                mat_strs.append(f'{mname}x{need}({have})')
                if have < need:
                    can_make = False
            msg += f"{status} **{rname}** [Lv.{rplv}] 成功率{rate}%\n"
            msg += f"   📦 材料：{' | '.join(mat_strs)}\n"
            msg += f"   📖 {rdesc}\n"
            if can_make and prof_level >= rplv:
                msg += f"   💡 `pw{'制药' if prof == 'alchemist' else '锻造'} {rname}`\n"
            msg += "\n"
        return {'success': True, 'msg': msg}

    def use_item(self, user_id: str, group_id: str, item_name: str) -> dict:
        """使用消耗品（药水等）"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT id, name, item_type, desc FROM items WHERE name=?', (item_name,))
        item = c.fetchone()
        if not item:
            conn.close()
            return {'success': False, 'msg': f'❌ 找不到物品 `{item_name}`'}
        iid, iname, itype, idesc = item
        conn.close()

        if itype != 'consumable':
            return {'success': False, 'msg': f'❌ `{item_name}` 不是消耗品，不能使用\n💡 装备用 `pw装备 {item_name}` 穿戴'}

        product_effect = None
        for product in CRAFT_PRODUCTS:
            if product[0] == iid:
                product_effect = product
                break
        if not product_effect:
            return {'success': False, 'msg': '❌ 该物品无法使用'}

        # 检查背包（优先商城背包）
        has_item = False
        if self.plugin:
            import asyncio
            try:
                inv = asyncio.get_event_loop().run_until_complete(self.plugin._get_inventory(user_id))
                has_count = sum(1 for it in inv if it.get("name") == item_name)
                has_item = has_count > 0
            except Exception:
                has_item = False
        if not has_item:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('SELECT quantity FROM inventory WHERE user_id=? AND group_id=? AND item_id=?', (user_id, group_id or "", iid))
            row = c.fetchone()
            conn.close()
            if not row or row[0] <= 0:
                return {'success': False, 'msg': f'❌ 你没有 `{item_name}`'}

        # 扣除物品（优先商城背包）
        if self.plugin and has_item:
            import asyncio
            try:
                inv = asyncio.get_event_loop().run_until_complete(self.plugin._get_inventory(user_id))
                removed = False
                new_inv = []
                for it in inv:
                    if not removed and it.get("name") == item_name:
                        removed = True
                    else:
                        new_inv.append(it)
                asyncio.get_event_loop().run_until_complete(self.plugin._save_inventory(user_id, new_inv))
            except Exception:
                pass
        else:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('UPDATE inventory SET quantity=quantity-1 WHERE user_id=? AND group_id=? AND item_id=?', (user_id, group_id or "", iid))
            c.execute('DELETE FROM inventory WHERE user_id=? AND group_id=? AND item_id=? AND quantity<=0', (user_id, group_id or "", iid))
            conn.commit()
            conn.close()

        # 查找产物效果
        pid, pname, prarity, price, ptype, effect, val, pdesc, hp_b, atk_b, def_b = product_effect
        msg = f"✅ 使用了 **{iname}**\n"
        if effect == 'stamina':
            new_st = min(100, self._recover_stamina(user_id) + val)
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('UPDATE user_levels SET stamina=? WHERE user_id=?', (new_st, user_id))
            conn.commit()
            conn.close()
            msg += f"⚡ 体力恢复 +{val}！当前 {new_st}/100"
        elif effect == 'exp_bonus':
            expires = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
            self._add_buff(user_id, 'exp_bonus', val, f'经验+{int(val*100)}%', expires)
            msg += f"📖 下次冒险经验 +{int(val*100)}%（持续1小时内出发生效）"
        elif effect == 'rare_bonus':
            expires = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
            self._add_buff(user_id, 'rare_bonus', val, f'稀有率+{int(val*100)}%', expires)
            msg += f"🔵 下次冒险稀有率 +{int(val*100)}%（持续1小时内出发生效）"
        elif effect == 'danger_reduce':
            expires = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
            self._add_buff(user_id, 'danger_reduce', val, f'危险率-{int(val*100)}%', expires)
            msg += f"🛡️ 下次冒险危险率 -{int(val*100)}%（持续1小时内出发生效）"
        else:
            msg += f"📖 {idesc}"
        return {'success': True, 'msg': msg}

    def get_inventory_list(self, user_id: str, group_id: str) -> str:
        """查看背包"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT i.id, i.name, i.rarity, i.item_type, inv.quantity FROM inventory inv JOIN items i ON inv.item_id=i.id WHERE inv.user_id=? AND inv.group_id=? AND inv.quantity>0 ORDER BY i.item_type, i.rarity DESC', (user_id, group_id or ""))
        rows = c.fetchall()
        conn.close()
        if not rows:
            return "🎒 冒险背包空空如也\n💡 `pw出发冒险` 去采集材料吧"
        rarity_emoji = {'common': '⚪', 'rare': '🔵', 'epic': '🟣', 'legendary': '🟡'}
        type_emoji = {'material': '🌿', 'consumable': '🧪', 'equipment': '⚔️', 'breakthrough': '🔮'}
        msg = "🎒 **冒险背包**\n\n"
        current_type = None
        for iid, name, rarity, itype, qty in rows:
            if itype != current_type:
                current_type = itype
                tname = {'material': '🌿 材料', 'consumable': '🧪 消耗品', 'equipment': '⚔️ 装备', 'breakthrough': '🔮 突破材料'}.get(itype, itype)
                msg += f"{tname}：\n"
            emoji = rarity_emoji.get(rarity, '⚪')
            temoji = type_emoji.get(itype, '')
            if itype == 'consumable':
                msg += f"  {emoji} {name}×{qty}  💡 `pw使用 {name}`\n"
            elif itype == 'equipment':
                msg += f"  {emoji} {name}×{qty}（已装备）\n"
            else:
                msg += f"  {emoji} {name}×{qty}\n"
        return msg

    def get_introduction(self, user_id: str, group_id: str) -> str:
        """冒险系统介绍"""
        user = self._get_user_data(user_id, group_id)
        prof = user.get('profession', 'none')
        prof_level = user.get('profession_level', 1)
        level = user.get('level', 1)

        prof_name_map = {'gatherer': '采集师', 'alchemist': '制药师', 'blacksmith': '锻造师', 'none': '无'}
        prof_name = prof_name_map.get(prof, '无')

        msg = "📖 **冒险系统介绍**\n"
        msg += "━━━━━━━━━━━━━━\n\n"

        msg += "🎮 **基础玩法**\n"
        msg += "1️⃣ `pw出发冒险 [地区名]` — 开始1小时冒险\n"
        msg += "2️⃣ `pw查看收获` — 实时查看收益或结束结算\n"
        msg += "3️⃣ `pw结束冒险` — 提前返回（立即结算）\n"
        msg += "4️⃣ `pw背包` — 查看采集到的材料\n\n"

        msg += "⚡ **体力系统**\n"
        msg += "• 上限100点，每次冒险消耗20点\n"
        msg += "• 每5分钟恢复1点\n"
        msg += "• `pw购买体力` — 100积分买10点\n\n"

        msg += "📈 **等级系统**（Lv.1 ~ Lv.100）\n"
        msg += "• 冒险获取经验升级\n"
        msg += "• 每10级需要突破：`pw突破` 提交材料\n"
        msg += "• 满级100级可前往任何地区👑\n\n"

        msg += "🎭 **职业系统**（10级解锁）\n"
        msg += "• `pw转职 [职业名]` — 选择职业（首次500积分，切换1000）\n"
        msg += "  🌿 采集师 — 触发率↑ 空手率↓ 收获数量↑\n"
        msg += "  ⚗️ 制药师 — 制作药水/buff药剂\n"
        msg += "  ⚒️ 锻造师 — 制作装备/工具\n"
        msg += "• 职业等级：初级→资深→大师（Lv.1~3）\n\n"

        msg += "⚗️ **制药师技能**\n"
        msg += "• `pw制药配方` — 查看可制药水\n"
        msg += "• `pw制药 [药水名]` — 制作（消耗材料）\n"
        msg += "• 药水：体力恢复 / 经验加成 / 稀有率加成 / 危险减免\n"
        msg += "• `pw使用 [药水名]` — 使用消耗品\n\n"

        msg += "⚒️ **锻造师技能**\n"
        msg += "• `pw锻造配方` — 查看可锻造物\n"
        msg += "• `pw锻造 [物品名]` — 制作（消耗材料）\n"
        msg += "• 装备：经验加成 / 收获加成 / 危险减免 / 史诗率加成\n"
        msg += "• 装备后永久生效，无需重复制作\n\n"

        msg += "🎒 **物品品质**\n"
        msg += "⚪ 普通 → 🔵 稀有 → 🟣 史诗\n"
        msg += "• 材料：用于制作/突破\n"
        msg += "• 消耗品：药水类，用完就没了\n"
        msg += "• 装备：永久生效，可叠加多个\n"
        msg += "• 突破材料：每10级突破必需\n\n"

        msg += "📊 **我的状态**\n"
        msg += f"📈 等级：Lv.{level}\n"
        msg += f"🎭 职业：{prof_name}"
        if prof != 'none':
            titles = {1: '初级', 2: '资深', 3: '大师'}
            pt = titles.get(prof_level, '初级')
            msg += f" Lv.{prof_level}（{pt}）"
        msg += "\n\n"

        msg += "💡 **快速开始**\n"
        msg += "`pw出发冒险` → 选地区 → 等1小时 → `pw查看收获`\n"
        msg += "10级后 `pw转职 采集师 确认` 开启职业玩法！"
        return msg

    # ==================== 装备系统 ====================
    def _get_equipment_stats(self, user_id: str) -> dict:
        """获取装备提供的属性加成"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT item_id FROM user_equipments WHERE user_id=?', (user_id,))
        eqs = c.fetchall()
        conn.close()

        bonus_hp = 0
        bonus_atk = 0
        bonus_def = 0
        bonus_exp = 0
        bonus_qty = 0
        bonus_danger = 0
        bonus_epic = 0
        bonus_craft = 0

        for (eid,) in eqs:
            for pid, pname, prarity, price, ptype, effect, val, pdesc, hp_b, atk_b, def_b in CRAFT_PRODUCTS:
                if pid == eid:
                    bonus_hp += hp_b
                    bonus_atk += atk_b
                    bonus_def += def_b
                    if effect == 'exp_bonus':
                        bonus_exp += val
                    elif effect == 'qty_bonus':
                        bonus_qty += val
                    elif effect == 'danger_reduce':
                        bonus_danger += val
                    elif effect == 'epic_bonus':
                        bonus_epic += val
                    elif effect == 'craft_bonus':
                        bonus_craft += val
                    break

        return {
            'hp': bonus_hp, 'attack': bonus_atk, 'defense': bonus_def,
            'exp_rate': bonus_exp, 'qty_bonus': bonus_qty,
            'danger_reduce': bonus_danger, 'epic_bonus': bonus_epic,
            'craft_bonus': bonus_craft
        }

    def equip_item(self, user_id: str, group_id: str, item_name: str) -> dict:
        """装备物品"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT id, name, item_type, desc FROM items WHERE name=?', (item_name,))
        item = c.fetchone()
        if not item:
            conn.close()
            return {'success': False, 'msg': f'❌ 找不到物品 `{item_name}`'}
        iid, iname, itype, idesc = item
        conn.close()

        if itype != 'equipment':
            return {'success': False, 'msg': f'❌ `{item_name}` 不是装备，无法穿戴'}

        # 检查背包（优先商城背包）
        has_item = False
        if self.plugin:
            import asyncio
            try:
                inv = asyncio.get_event_loop().run_until_complete(self.plugin._get_inventory(user_id))
                has_count = sum(1 for it in inv if it.get("name") == item_name)
                has_item = has_count > 0
            except Exception:
                has_item = False
        if not has_item:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('SELECT quantity FROM inventory WHERE user_id=? AND group_id=? AND item_id=?', (user_id, group_id or "", iid))
            row = c.fetchone()
            conn.close()
            if not row or row[0] <= 0:
                return {'success': False, 'msg': f'❌ 你没有 `{item_name}`'}

        # 检查是否已装备
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT item_id FROM user_equipments WHERE user_id=?', (user_id,))
        existing = c.fetchall()
        if existing and any(e[0] == iid for e in existing):
            conn.close()
            return {'success': False, 'msg': f'❌ `{item_name}` 已经装备了'}

        # 装备（最多5件）
        if len(existing) >= 5:
            conn.close()
            return {'success': False, 'msg': '❌ 装备栏已满（最多5件）\n💡 `pw卸下 [装备名]` 腾出位置'}

        c.execute('INSERT INTO user_equipments (user_id, item_id) VALUES (?,?)', (user_id, iid))
        conn.commit()
        conn.close()

        # 获取装备属性
        for pid, pname, prarity, price, ptype, effect, val, pdesc, hp_b, atk_b, def_b in CRAFT_PRODUCTS:
            if pid == iid:
                msg = f"✅ **装备成功！**\n"
                msg += f"⚔️ {iname}\n"
                if hp_b > 0:
                    msg += f"❤️ HP +{hp_b}\n"
                if atk_b > 0:
                    msg += f"⚔️ 攻击 +{atk_b}\n"
                if def_b > 0:
                    msg += f"🛡️ 防御 +{def_b}\n"
                msg += f"📖 {idesc}"
                return {'success': True, 'msg': msg}
        return {'success': True, 'msg': f'✅ 装备了 {iname}'}

    def unequip_item(self, user_id: str, item_name: str) -> dict:
        """卸下装备"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT id, name FROM items WHERE name=?', (item_name,))
        item = c.fetchone()
        if not item:
            conn.close()
            return {'success': False, 'msg': f'❌ 找不到装备 `{item_name}`'}
        iid, iname = item
        c.execute('DELETE FROM user_equipments WHERE user_id=? AND item_id=?', (user_id, iid))
        if c.rowcount == 0:
            conn.close()
            return {'success': False, 'msg': f'❌ 你没有装备 `{item_name}`'}
        conn.commit()
        conn.close()
        return {'success': True, 'msg': f'✅ 已卸下 **{iname}**'}

    # ==================== 角色面板 ====================
    def get_character_panel(self, user_id: str, group_id: str) -> str:
        """角色面板"""
        user = self._get_user_data(user_id, group_id)
        level = user.get('level', 1)
        exp = user.get('exp', 0)
        hp = user.get('hp', 100)
        max_hp = user.get('max_hp', 100)
        attack = user.get('attack', 10)
        defense = user.get('defense', 5)
        prof = user.get('profession', 'none')
        prof_level = user.get('profession_level', 1)
        profession_exp = user.get('profession_exp', 0)
        stamina = self._recover_stamina(user_id)

        # 获取装备加成
        eq_stats = self._get_equipment_stats(user_id)
        total_hp = max_hp + eq_stats['hp']
        total_atk = attack + eq_stats['attack']
        total_def = defense + eq_stats['defense']

        # 获取等级称号
        config = self._get_level_config(level)
        title = config['title'] if config else '冒险者'

        # HP 进度条
        hp_bar_len = 10
        hp_filled = int((hp / max(1, total_hp)) * hp_bar_len)
        hp_bar = '█' * hp_filled + '░' * (hp_bar_len - hp_filled)

        # 体力进度条
        st_bar_len = 10
        st_filled = int((stamina / 100) * st_bar_len)
        st_bar = '█' * st_filled + '░' * (st_bar_len - st_filled)

        # 经验进度条
        exp_needed = config['exp_needed'] if config else 100
        exp_bar_len = 10
        exp_filled = int((exp / max(1, exp_needed)) * exp_bar_len)
        exp_bar = '█' * exp_filled + '░' * (exp_bar_len - exp_filled)

        msg = f"🎴 **{title} 的角色面板**\n"
        msg += "━━━━━━━━━━━━━━\n\n"

        # 基础信息
        msg += f"📈 等级：Lv.{level} {title}\n"
        msg += f"📖 经验：[{exp_bar}] {exp}/{exp_needed}\n\n"

        # 血量
        msg += f"❤️ 血量：[{hp_bar}] {hp}/{total_hp}"
        if eq_stats['hp'] > 0:
            msg += f"（基础{max_hp} + 装备+{eq_stats['hp']}）"
        msg += "\n"

        # 攻击
        msg += f"⚔️ 攻击：{total_atk}"
        if eq_stats['attack'] > 0:
            msg += f"（基础{attack} + 装备+{eq_stats['attack']}）"
        msg += "\n"

        # 防御
        msg += f"🛡️ 防御：{total_def}"
        if eq_stats['defense'] > 0:
            msg += f"（基础{defense} + 装备+{eq_stats['defense']}）"
        msg += "\n\n"

        # 体力
        msg += f"⚡ 体力：[{st_bar}] {stamina}/100\n"
        sinfo = self._get_stamina_info(user_id)
        if sinfo['stamina'] < 100:
            msg += f"⏱️ 下次恢复：{sinfo['next_recover']}\n"
        msg += "\n"

        # 职业
        if prof != 'none':
            prof_name = PROF_CONFIG.get(prof, {}).get('name', prof)
            titles = {1: '初级', 2: '资深', 3: '大师'}
            pt = titles.get(prof_level, '初级')
            msg += f"🎭 职业：{pt}{prof_name} Lv.{prof_level}\n"
            msg += f"📖 职业经验：{profession_exp}"
            if prof_level < 3:
                need = PROF_LEVEL_REQ[prof_level + 1]
                msg += f" / {need}（还需 {need - profession_exp}）"
            else:
                msg += "（已满级）"
            msg += "\n\n"

        # 装备栏
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT e.item_id, i.name, i.rarity FROM user_equipments e JOIN items i ON e.item_id=i.id WHERE e.user_id=?', (user_id,))
        eqs = c.fetchall()
        conn.close()

        if eqs:
            rarity_emoji = {'common': '⚪', 'rare': '🔵', 'epic': '🟣', 'legendary': '🟡'}
            msg += "⚔️ **已装备**（{}/5）：\n".format(len(eqs))
            for eid, ename, erarity in eqs:
                emoji = rarity_emoji.get(erarity, '⚪')
                msg += f"  {emoji} {ename}\n"
            msg += "\n"
        else:
            msg += "⚔️ **装备栏**：空（0/5）\n"
            msg += "💡 `pw锻造` 制作装备，然后 `pw装备 [装备名]`\n\n"

        # 装备特效汇总
        if any(v > 0 for v in [eq_stats['exp_rate'], eq_stats['qty_bonus'], eq_stats['danger_reduce'], eq_stats['epic_bonus'], eq_stats['craft_bonus']]):
            msg += "✨ **装备特效**：\n"
            if eq_stats['exp_rate'] > 0:
                msg += f"  📖 经验加成 +{int(eq_stats['exp_rate']*100)}%\n"
            if eq_stats['qty_bonus'] > 0:
                msg += f"  🎒 收获数量 +{eq_stats['qty_bonus']}\n"
            if eq_stats['danger_reduce'] > 0:
                msg += f"  🛡️ 危险减免 -{int(eq_stats['danger_reduce']*100)}%\n"
            if eq_stats['epic_bonus'] > 0:
                msg += f"  🟣 史诗掉率 +{int(eq_stats['epic_bonus']*100)}%\n"
            if eq_stats['craft_bonus'] > 0:
                msg += f"  ⚒️ 锻造成功率 +{int(eq_stats['craft_bonus']*100)}%\n"
            msg += "\n"

        # 当前冒险状态
        if user.get('adventure_active') == 1:
            start = datetime.strptime(user['adventure_start'], "%Y-%m-%d %H:%M:%S")
            remain = max(0, 60 - int((datetime.now() - start).total_seconds() // 60))
            region = self._get_region(user.get('adventure_region'))
            rname = region['name'] if region else '未知'
            msg += f"🗺️ **当前冒险**：{rname}\n"
            msg += f"⏱️ 剩余 {remain} 分钟\n"
            msg += f"💡 `pw查看收获` 查看收益\n"

        msg += "\n💡 `pw冒险介绍` 查看完整玩法说明"
        return msg


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
        # 初始化冒险系统
        import os
        db_dir = os.path.dirname(os.path.abspath(__file__))
        self.adv_db_path = os.path.join(db_dir, "adventure.db")
        self.adventure = AdventureSystem(self.adv_db_path, plugin=self)

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
        return not event.get_group_id()

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

    def _parse_shop_config(self, item_str: str) -> tuple[str, float] | None:
        parts = item_str.split(":")
        if len(parts) < 2:
            return None
        name = parts[0].strip()
        if not name:
            return None
        try:
            price = float(parts[1].strip())
        except ValueError:
            return None
        return name, price

    async def _get_existing_shop_names(self, index_key: str, getter) -> set:
        names = set()
        raw = await self.get_kv_data(index_key, None)
        if raw is None or raw == "" or raw == "null":
            return names
        idx = json.loads(raw) if isinstance(raw, str) else raw
        for item_id in idx:
            item = await getter(item_id)
            if item and item.get("stock", 0) > 0:
                names.add(item.get("name", ""))
        return names

    def _parse_args(self, event: AstrMessageEvent, cmd_name: str) -> list:
        text = event.message_str.strip()
        for prefix in [f'/{cmd_name}', cmd_name]:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                break
        return text.split()

    # ==================== LLM 拦截与扣费 ====================

    async def _init_default_shop(self):
        """初始化或补齐默认商品到商城"""
        try:
            general_names = await self._get_existing_shop_names(self._shop_index_key(), self._get_shop_item)
            item_names = await self._get_existing_shop_names(self._item_shop_index_key(), self._get_item_shop_item)
            general_count = 0
            item_count = 0

            for item_str in self.general_items:
                parsed = self._parse_shop_config(item_str)
                if parsed:
                    name, price = parsed
                    if name in general_names:
                        continue
                    item_id = self._gen_item_id()
                    item = {
                        "id": item_id, "name": name, "price": price, "original_price": price,
                        "stock": 999, "seller": "system", "seller_name": "系统商店",
                        "created_at": datetime.now().isoformat(), "discount": 1.0, "shop_type": "百货"
                    }
                    await self._save_shop_item(item_id, item)
                    await self._add_shop_index(item_id)
                    general_names.add(name)
                    general_count += 1

            for item_str in self.items:
                parsed = self._parse_shop_config(item_str)
                if parsed:
                    name, price = parsed
                    if name in item_names:
                        continue
                    item_id = self._gen_item_id()
                    item = {
                        "id": item_id, "name": name, "price": price, "original_price": price,
                        "stock": 999, "seller": "system", "seller_name": "系统商店",
                        "created_at": datetime.now().isoformat(), "discount": 1.0, "shop_type": "道具"
                    }
                    await self._save_item_shop_item(item_id, item)
                    await self._add_item_shop_index(item_id)
                    item_names.add(name)
                    item_count += 1

            await self.put_kv_data("paywall_shop_initialized", "true")
            if general_count or item_count:
                logger.info(f"[Paywall] 默认商品已自动补齐：百货{general_count}件，道具{item_count}件")
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
        self._start_adventure_checker()

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

    def _start_adventure_checker(self):
        """启动后台冒险结算检查器。"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                self._adventure_checker_task = asyncio.ensure_future(self._adventure_check_loop())
        except Exception:
            pass

    async def _adventure_check_loop(self):
        """定时检查并自动结算过期冒险。"""
        await asyncio.sleep(30)
        while True:
            try:
                await self._check_expired_adventures()
            except Exception as e:
                logger.error(f"冒险自动结算异常: {e}")
            await asyncio.sleep(60)

    async def _check_expired_adventures(self):
        """查找并结算已过期的冒险。"""
        conn = sqlite3.connect(self.adv_db_path)
        c = conn.cursor()
        c.execute("""
            SELECT user_id, group_id FROM user_levels
            WHERE adventure_active=1
            AND adventure_start IS NOT NULL
            AND datetime(adventure_start, '+1 hour') <= datetime('now', 'localtime')
        """)
        rows = c.fetchall()
        conn.close()
        if not rows:
            return
        for user_id, group_id in rows:
            if not group_id: group_id = ""
            try:
                result = self.adventure._calc_adventure_loot(user_id, group_id, force_end=True)
                if result:
                    await self.adventure._sync_adventure_items_to_kv(user_id, result)
                    logger.info(f"[Paywall] 自动结算冒险: user={user_id}, items={list(result.get('new_items', {}).keys())}")
            except Exception as e:
                logger.error(f"[Paywall] 自动结算用户 {user_id} 冒险失败: {e}")
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
            yield event.plain_result("❌ 用法: /pw上架 商品名 [数量]\n道具: /pw上架 蘑菇 5\n百货: /pw上架 自定义商品 100 5")
            return

        name = parts[0]
        seller_id = str(event.get_sender_id())

        # 判断是道具还是百货：检查物品在哪个配置列表中
        item_config = None
        shop_type = "百货"  # 默认百货商城

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
                    shop_type = "百货"  # 在百货列表中，上架到百货商城
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
        else:
            # 百货：需要价格参数
            if len(parts) < 2:
                yield event.plain_result(f"❌ 「{name}」不是道具商城物品，上架百货需要指定价格。\n格式: /pw上架 商品名 价格 [数量]")
                return
            try:
                price = float(parts[1])
                list_count = int(parts[2]) if len(parts) > 2 else 1
            except ValueError:
                yield event.plain_result("❌ 价格必须是数字，数量必须是整数")
                return
            shop_type = "百货"

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
                discount_tag = "" if discount >= 1.0 else f" [🔥{discount*10:g}折]"
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
                discount_tag = "" if discount >= 1.0 else f" [🔥{discount*10:g}折]"
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
            shop_type = "百货"

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
                            system_items.append((item_id, item, "百货"))
                        else:
                            player_items.append((item_id, item, "百货"))

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

        discount_msg = "" if discount >= 1.0 else f"（原价 {item['original_price']:.2f}，{discount*10:g}折）"
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
                discount_tag = "" if discount >= 1.0 else f" [🔥{discount*10:g}折]"
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

        body = self._format_stacked_inventory(inventory)
        yield event.plain_result(f"🎒 **背包物品** ({len(inventory)} 件 / {len(body)} 种)\n━━━━━━━━━━━━━━\n" + "\n".join(body) + "\n━━━━━━━━━━━━━━")

    def _format_stacked_inventory(self, inventory: list) -> list:
        """按名称堆叠 KV 背包，避免同名物品刷屏。"""
        stacked = {}
        order = []
        for item in inventory:
            name = str(item.get("name", "未知物品"))
            if name not in stacked:
                stacked[name] = {
                    "count": 0,
                    "source": item.get("source", ""),
                    "date": item.get("date", ""),
                }
                order.append(name)
            stacked[name]["count"] += 1
            if item.get("date"):
                stacked[name]["date"] = item.get("date")
            if item.get("source"):
                stacked[name]["source"] = item.get("source")

        lines = []
        for name in order:
            info = stacked[name]
            lines.append(f"{name}×{info['count']}")
        return lines

    async def _show_inventory(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        group_id = event.get_group_id() or ""
        kv_inv = await self._get_inventory(user_id)
        adv_inv = self.adventure.get_inventory_list(user_id, group_id)

        parts = []

        if kv_inv:
            items = self._format_stacked_inventory(kv_inv)
            parts.append(f"🎒 **背包物品** ({len(kv_inv)} 件 / {len(items)} 种)\n" + "\n".join(items))

        if adv_inv and "空空如也" not in adv_inv:
            parts.append(adv_inv)

        if not parts:
            if adv_inv:
                yield event.plain_result(adv_inv)
            else:
                yield event.plain_result("📭 你的背包是空的")
            return

        yield event.plain_result("\n".join(parts))


    @filter.command("pw出售")
    async def sell_item(self, event: AstrMessageEvent):
        """把背包物品卖给系统，价格80%（按名称出售）"""
        parts = self._parse_args(event, "pw出售")
        if not parts:
            yield event.plain_result("❌ 用法: /pw出售 物品名称 [数量]\n例如: /pw出售 蘑菇\n      /pw出售 蘑菇 5")
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
            yield event.plain_result("❌ 用法: /pw打折 商品编号/全部 折扣\n例如: /pw打折 ITEM-AB12CD 0.8 (8折) 或 /pw打折 全部 0.8 (全场8折)")
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

        
        # 全部商品打折
        if item_id == "全部":
            count = 0
            # 百货
            idx_raw = await self.get_kv_data(self._shop_index_key(), None)
            if idx_raw is not None and idx_raw != "" and idx_raw != "null":
                idx = json.loads(idx_raw) if isinstance(idx_raw, str) else idx_raw
                for sid in idx:
                    item = await self._get_shop_item(sid)
                    if item and item.get("stock", 0) > 0:
                        item["discount"] = discount
                        await self._save_shop_item(sid, item)
                        count += 1
            # 道具
            idx_raw = await self.get_kv_data(self._item_shop_index_key(), None)
            if idx_raw is not None and idx_raw != "" and idx_raw != "null":
                idx = json.loads(idx_raw) if isinstance(idx_raw, str) else idx_raw
                for sid in idx:
                    item = await self._get_item_shop_item(sid)
                    if item and item.get("stock", 0) > 0:
                        item["discount"] = discount
                        await self._save_item_shop_item(sid, item)
                        count += 1
            if count == 0:
                yield event.plain_result("📭 商城没有商品")
                return
            logger.info(f"[Paywall] 管理员 {admin_id} 全部商品 {discount*10:g}折，共 {count} 件")
            yield event.plain_result(f"✅ 全部商品打折设置成功！\n折扣: {discount*10:g}折\n影响商品: {count} 件")
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
        logger.info(f"[Paywall] 管理员 {admin_id} 给 {item_id} 设置 {discount*10:g}折")
        yield event.plain_result(
            f"✅ 打折设置成功！\n"
            f"商品: {item['name']}\n"
            f"折扣: {discount*10:g}折\n"
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
            yield event.plain_result("❌ 用法: /pw取消打折 商品编号 或 /pw取消打折 全部")
            return

        item_id = parts[0].strip().upper()

        # 全部取消
        if item_id == "全部":
            count = 0
            # 百货
            idx_raw = await self.get_kv_data(self._shop_index_key(), None)
            if idx_raw is not None and idx_raw != "" and idx_raw != "null":
                idx = json.loads(idx_raw) if isinstance(idx_raw, str) else idx_raw
                for sid in idx:
                    item = await self._get_shop_item(sid)
                    if item and item.get("discount", 1.0) != 1.0:
                        item["discount"] = 1.0
                        await self._save_shop_item(sid, item)
                        count += 1
            # 道具
            idx_raw = await self.get_kv_data(self._item_shop_index_key(), None)
            if idx_raw is not None and idx_raw != "" and idx_raw != "null":
                idx = json.loads(idx_raw) if isinstance(idx_raw, str) else idx_raw
                for sid in idx:
                    item = await self._get_item_shop_item(sid)
                    if item and item.get("discount", 1.0) != 1.0:
                        item["discount"] = 1.0
                        await self._save_item_shop_item(sid, item)
                        count += 1
            logger.info(f"[Paywall] 管理员 {admin_id} 取消全部打折，共 {count} 件")
            yield event.plain_result(f"✅ 已取消全部打折！\n共恢复 {count} 件商品原价")
            return

        # 单个取消
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
            f"【冒险系统】\n"
            f"/pw冒险介绍 - 📖 查看冒险系统详细介绍\n"
            f"/pw出发冒险 [地区名] - 开始冒险\n"
            f"/pw查看收获 - 查看冒险收益\n"
            f"/pw结束冒险 - 提前结束冒险\n"
            f"/pw购买体力 - 100积分买10体力\n"
            f"/pw突破 - 等级突破（需材料）\n"
            f"/pw角色面板 - 查看角色状态\n"
            f"/pw装备 [装备名] - 穿戴装备\n"
            f"/pw卸下 [装备名] - 卸下装备\n"
            f"/pw使用 [物品名] - 使用消耗品\n"
            f"/pw转职 [职业名] [确认] - 选择职业（首次500，切换1000）\n"
            f"  🌿 采集师 - 触发率↑ 空手率↓ 收获数量↑\n"
            f"  ⚗️ 制药师 - 制作药水/buff药剂\n"
            f"  ⚒️ 锻造师 - 制作装备/工具\n"
            f"  ⚗️ 制药师专属: /pw制药配方 /pw制药 [药水名]\n"
            f"  ⚒️ 锻造师专属: /pw锻造配方 /pw锻造 [物品名]\n"
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
            f"/pw打折 全部 折扣\n"
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
            f"/pw打折 全部 折扣 - 全场打折"
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

    # ==================== 冒险系统指令 ====================

    @filter.command("pw出发冒险")
    async def cmd_adventure(self, event: AstrMessageEvent):
        args = self._parse_args(event, "pw出发冒险")
        user_id = str(event.get_sender_id())
        group_id = event.get_group_id() or ""
        user = self.adventure._get_user_data(user_id, group_id)
        stamina = self.adventure._recover_stamina(user_id)
        if not args:
            conn = sqlite3.connect(self.adventure.db_path)
            c = conn.cursor()
            c.execute('SELECT id,name,min_level,max_level,cost,danger_rate,desc FROM regions ORDER BY min_level')
            regions = c.fetchall()
            conn.close()
            is_max = user['level'] >= 100
            current = self.adventure._get_region_by_level(user['level'])
            sinfo = self.adventure._get_stamina_info(user_id)
            bar_len = 10; filled = int((sinfo['stamina'] / sinfo['max']) * bar_len); bar = '█' * filled + '░' * (bar_len - filled)
            msg = f"🗺️ **冒险地图** | "; msg += "👑 **满级冒险家**" if is_max else f"Lv.{user['level']}"

            msg += "\n\n"
            for rid, name, min_lv, max_lv, cost, danger, desc in regions:
                if is_max: status, note = "👑", ""
                elif user['level'] >= min_lv: status, note = "🔓", " ← 当前" if current and current['id'] == rid else ""
                else: status, note = "🔒", f"（需{min_lv}级）"
                msg += f"{status} {name}  [Lv.{min_lv}-{max_lv}]  危险{danger}%  ⚡{cost}{note}"
                if status != "🔒": msg += f"   {desc}\n"
            msg += "\n💡 用法：`pw出发冒险 [地区名]`（每次⚡20）"
            if sinfo['stamina'] < 20: msg += "\n⚠️ 体力不足！`pw购买体力` 补充"
            yield event.plain_result(msg); return
        target = args[0]
        conn = sqlite3.connect(self.adventure.db_path); c = conn.cursor()
        c.execute('SELECT id,name,min_level,cost,danger_rate,desc FROM regions WHERE name LIKE ?', (f'%{target}%',))
        region = c.fetchone()
        if not region: conn.close(); yield event.plain_result(f"❌ 找不到 `{target}`"); return
        rid, rname, min_lv, cost, danger, desc = region
        if user.get('adventure_active') == 1 and user.get('adventure_start'):
            start = datetime.strptime(user['adventure_start'], "%Y-%m-%d %H:%M:%S")
            if datetime.now() < start + timedelta(hours=1): conn.close(); _ar = self.adventure._get_region(user['adventure_region']) if user.get('adventure_region') else None; yield event.plain_result(f"⏱️ 你已经在冒险中了！\n📍 {_ar['name'] if _ar else '未知'}\n💡 `pw查看收获` 或 `pw结束冒险`"); return

        if user['level'] < 100 and user['level'] < min_lv: conn.close(); yield event.plain_result(f"🔒 等级不足！{rname} 需{min_lv}级，你当前 Lv.{user['level']}"); return
        if stamina < cost: conn.close(); yield event.plain_result(f"😫 体力不足！需⚡{cost}，当前⚡{stamina}\n💡 `pw购买体力` 补充"); return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        adventure_buffs = self.adventure._take_adventure_buffs(user_id)
        c.execute('UPDATE user_levels SET stamina=?,adventure_start=?,adventure_region=?,adventure_active=1,adventure_last_check=?,adventure_items="{}",adventure_exp=0,adventure_danger=0,adventure_buffs=? WHERE user_id=?',
                  (stamina - cost, now, rid, now, json.dumps(adventure_buffs, ensure_ascii=False), user_id))
        conn.commit(); conn.close()
        end_time = (datetime.now() + timedelta(hours=1)).strftime("%H:%M")
        privilege = "\n👑 满级特权生效" if user['level'] >= 100 else ""
        buff_msg = ""
        if adventure_buffs.get('descs'):
            buff_msg = "\n🧪 药水效果：" + "、".join(adventure_buffs['descs'])
        yield event.plain_result(f"🎒 **出发冒险！**{privilege}\n📍 {rname}\n⚡ 消耗：{cost}体力 | 剩余：{stamina-cost}/100\n⏱️ 时长：1小时（到 {end_time}）\n💀 危险率：{danger}%{buff_msg}\n\n✨ 冒险期间每分钟自动随机获取物品！\n💡 `pw查看收获` 随时查看收益\n💡 `pw结束冒险` 提前返回")

    @filter.command("pw转职")
    async def cmd_profession(self, event: AstrMessageEvent):
        args = self._parse_args(event, "pw转职")
        user_id = str(event.get_sender_id()); group_id = event.get_group_id() or ""
        if not args:
            user = self.adventure._get_user_data(user_id, group_id); current = user.get('profession', 'none')
            if current == 'none': yield event.plain_result("🎭 **转职系统**\n10级后可选择职业：\n• 🌿 采集师（按收获数量升级，每次冒险最多+20经验）\n• ⚗️ 制药师（按制药成败升级）\n• ⚒️ 锻造师（按锻造成败升级）\n\n💡 `pw转职 [职业名]` 选择\n⚠️ 切换职业后，旧进度清零！"); return
            prof_name = {'gatherer': '采集师', 'alchemist': '制药师', 'blacksmith': '锻造师'}[current]
            result = self.adventure.change_profession(user_id, group_id, prof_name); yield event.plain_result(result['msg']); return

        confirm = False
        if args and args[-1] == '确认':
            confirm = True
            args = args[:-1]

        if not args:
            yield event.plain_result("❌ 请指定职业名：采集师、制药师、锻造师\n💡 用法：`pw转职 [职业名] 确认`")
            return

        prof_name = args[0]
        valid = {'采集师': 'gatherer', '制药师': 'alchemist', '锻造师': 'blacksmith'}
        if prof_name not in valid:
            yield event.plain_result("❌ 可选：采集师、制药师、锻造师"); return

        user = self.adventure._get_user_data(user_id, group_id)
        current = user.get('profession', 'none')
        target = valid[prof_name]

        if current == target:
            result = self.adventure.change_profession(user_id, group_id, prof_name)
            yield event.plain_result(result['msg']); return

        is_first = (current == 'none')
        cost = 500 if is_first else 1000

        if not confirm:
            current_name_map = {'gatherer': '采集师', 'alchemist': '制药师', 'blacksmith': '锻造师', 'none': '无'}
            current_name = current_name_map.get(current, '无')
            cfg = PROF_CONFIG.get(target, {})
            msg = f"⚠️ **职业切换确认**\n"
            msg += f"🎭 当前职业：{current_name}\n"
            msg += f"🎯 目标职业：{cfg.get('emoji', '')} {prof_name}\n"
            msg += f"💰 所需积分：{cost}（{'首次转职' if is_first else '切换职业'}）\n"
            msg += f"⚠️ 切换后，旧职业进度**全部清零**！\n"
            msg += f"💡 请发送：`pw转职 {prof_name} 确认` 以确认切换"
            yield event.plain_result(msg); return

        # 检查并扣除积分
        data = await self._get_data("user", user_id)
        if data["balance"] < cost:
            yield event.plain_result(f'❌ 积分不足！需要 {cost}，当前 {data["balance"]:.2f}\n💡 请充值后再试'); return
        data["balance"] -= cost
        await self._save_data("user", user_id, data)

        result = self.adventure.change_profession(user_id, group_id, prof_name)
        if result['success']:
            result['msg'] = result['msg'].replace('📖 从 **初级（Lv.1）** 开始，经验：0\n', f'📖 从 **初级（Lv.1）** 开始，经验：0\n💰 已扣除积分：{cost}\n')
        yield event.plain_result(result['msg'])

    @filter.command("pw查看收获")
    async def cmd_check_loot(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id()); group_id = event.get_group_id() or ""
        user = self.adventure._get_user_data(user_id, group_id)
        if user.get('adventure_active') != 1: yield event.plain_result("❌ 你尚未参与冒险\n💡 `pw出发冒险 [地区名]` 开始冒险"); return
        start = datetime.strptime(user['adventure_start'], "%Y-%m-%d %H:%M:%S")
        if datetime.now() >= start + timedelta(hours=1): result = self.adventure._calc_adventure_loot(user_id, group_id, force_end=True)
        else: result = self.adventure._calc_adventure_loot(user_id, group_id)
        if result:
            await self.adventure._sync_adventure_items_to_kv(user_id, result)
        user = self.adventure._get_user_data(user_id, group_id)
        msg = self.adventure._format_loot(result, user); yield event.plain_result(msg)

    @filter.command("pw结束冒险")
    async def cmd_end_adventure(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id()); group_id = event.get_group_id() or ""
        user = self.adventure._get_user_data(user_id, group_id)
        if user.get('adventure_active') != 1: yield event.plain_result("❌ 你尚未参与冒险"); return
        result = self.adventure._calc_adventure_loot(user_id, group_id, force_end=True)
        if result:
            await self.adventure._sync_adventure_items_to_kv(user_id, result)
        user = self.adventure._get_user_data(user_id, group_id)
        msg = self.adventure._format_loot(result, user); yield event.plain_result(msg)

    @filter.command("pw购买体力")
    async def cmd_buy_stamina(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id()); group_id = event.get_group_id() or ""
        self.adventure._get_user_data(user_id, group_id)  # 确保 user_levels 行已初始化
        data = await self._get_data("user", user_id)
        cost = 100
        if data["balance"] < cost:
            yield event.plain_result(f"❌ 积分不足！需要 {cost}，当前 {data['balance']:.2f}\n💡 请充值后再试"); return

        conn = sqlite3.connect(self.adventure.db_path)
        c = conn.cursor()
        c.execute('SELECT stamina, max_stamina FROM user_levels WHERE user_id=?', (user_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            yield event.plain_result("❌ 体力数据初始化失败，请先发送 `pw出发冒险` 后重试"); return
        st, mx = row
        new_st = min(mx or 100, (st or 0) + 10)
        c.execute('UPDATE user_levels SET stamina=? WHERE user_id=?', (new_st, user_id))
        conn.commit()
        conn.close()
        data["balance"] -= cost
        await self._save_data("user", user_id, data)
        yield event.plain_result(f"✅ 体力购买成功！\n⚡ +10 体力\n💰 扣除积分：{cost}\n📊 当前体力：{new_st}/{mx or 100}")

    @filter.command("pw突破")
    async def cmd_breakthrough(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id()); group_id = event.get_group_id() or ""
        user = self.adventure._get_user_data(user_id, group_id)
        level = user.get('level', 1)
        if level % 10 != 0 or level == 0:
            yield event.plain_result(f"❌ 当前 Lv.{level}，无需突破\n💡 突破只在 Lv.10/20/30... 时需要进行"); return

        config = self.adventure._get_level_config(level)
        if not config or not config.get('break_item'):
            yield event.plain_result("❌ 当前等级无需突破材料"); return
        need_item = config['break_item']
        need_count = config['break_count']
        conn = sqlite3.connect(self.adventure.db_path)
        c = conn.cursor()
        c.execute('SELECT item_id, quantity FROM inventory WHERE user_id=? AND group_id=?', (user_id, group_id or ""))
        inv = {row[0]: row[1] for row in c.fetchall()}
        c.execute('SELECT id FROM items WHERE name=?', (need_item,))
        item_row = c.fetchone()
        conn.close()
        if not item_row:
            yield event.plain_result(f"❌ 突破材料 `{need_item}` 不存在"); return
        item_id = item_row[0]
        have = inv.get(item_id, 0)
        if have < need_count:
            yield event.plain_result(f"❌ 突破材料不足！\n🔒 需要：{need_item} x{need_count}（有{have}）\n💡 `pw背包` 查看材料，或去对应地区冒险获取"); return

        # 扣除材料
        conn = sqlite3.connect(self.adventure.db_path)
        c = conn.cursor()
        c.execute('UPDATE inventory SET quantity=quantity-? WHERE user_id=? AND group_id=? AND item_id=?', (need_count, user_id, group_id or "", item_id))
        c.execute('DELETE FROM inventory WHERE user_id=? AND group_id=? AND item_id=? AND quantity<=0', (user_id, group_id or "", item_id))
        # 突破：升级
        new_level = level + 1
        new_max_hp = 100 + (new_level - 1) * 10
        new_attack = 10 + (new_level - 1) * 2
        new_defense = 5 + (new_level - 1) * 1
        c.execute('UPDATE user_levels SET level=?,exp=0,max_hp=?,hp=?,attack=?,defense=? WHERE user_id=?', (new_level, new_max_hp, new_max_hp, new_attack, new_defense, user_id))
        conn.commit()
        conn.close()
        new_config = self.adventure._get_level_config(new_level)
        title = new_config['title'] if new_config else '冒险者'
        yield event.plain_result(f"🔓 **等级突破成功！**\n🎉 Lv.{level} → Lv.{new_level}\n🎭 称号升级：{config['title']} → {title}\n❤️ 血量上限提升：{user.get('max_hp', 100)} → {new_max_hp}\n⚔️ 攻击提升：{user.get('attack', 10)} → {new_attack}\n🛡️ 防御提升：{user.get('defense', 5)} → {new_defense}\n\n💡 继续 `pw出发冒险` 获取经验吧！")

    @filter.command("pw制药配方")
    async def cmd_alchemy_recipes(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id()); group_id = event.get_group_id() or ""
        result = self.adventure.get_recipes(user_id, group_id); yield event.plain_result(result['msg'])

    @filter.command("pw锻造配方")
    async def cmd_blacksmith_recipes(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id()); group_id = event.get_group_id() or ""
        result = self.adventure.get_recipes(user_id, group_id); yield event.plain_result(result['msg'])

    @filter.command("pw制药")
    async def cmd_alchemy(self, event: AstrMessageEvent):
        args = self._parse_args(event, "pw制药")
        user_id = str(event.get_sender_id()); group_id = event.get_group_id() or ""
        if not args: yield event.plain_result("❌ 请指定药水名称\n💡 `pw制药配方` 查看可制药水"); return
        result = self.adventure.craft(user_id, group_id, args[0]); yield event.plain_result(result['msg'])

    @filter.command("pw锻造")
    async def cmd_blacksmith(self, event: AstrMessageEvent):
        args = self._parse_args(event, "pw锻造")
        user_id = str(event.get_sender_id()); group_id = event.get_group_id() or ""
        if not args: yield event.plain_result("❌ 请指定物品名称\n💡 `pw锻造配方` 查看可锻造物"); return
        result = self.adventure.craft(user_id, group_id, args[0]); yield event.plain_result(result['msg'])

    @filter.command("pw使用")
    async def cmd_use(self, event: AstrMessageEvent):
        args = self._parse_args(event, "pw使用")
        user_id = str(event.get_sender_id()); group_id = event.get_group_id() or ""
        if not args: yield event.plain_result("❌ 请指定物品名称\n💡 `pw背包` 查看可用物品"); return
        result = self.adventure.use_item(user_id, group_id, args[0]); yield event.plain_result(result['msg'])



    @filter.command("pw冒险介绍")
    async def cmd_intro(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id()); group_id = event.get_group_id() or ""
        msg = self.adventure.get_introduction(user_id, group_id); yield event.plain_result(msg)

    @filter.command("pw角色面板")
    async def cmd_panel(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id()); group_id = event.get_group_id() or ""
        msg = self.adventure.get_character_panel(user_id, group_id); yield event.plain_result(msg)

    @filter.command("pw装备")
    async def cmd_equip(self, event: AstrMessageEvent):
        args = self._parse_args(event, "pw装备")
        user_id = str(event.get_sender_id()); group_id = event.get_group_id() or ""
        if not args: yield event.plain_result("❌ 请指定装备名称\n💡 `pw背包` 查看可用装备"); return
        result = self.adventure.equip_item(user_id, group_id, args[0]); yield event.plain_result(result['msg'])

    @filter.command("pw卸下")
    async def cmd_unequip(self, event: AstrMessageEvent):
        args = self._parse_args(event, "pw卸下")
        user_id = str(event.get_sender_id()); group_id = event.get_group_id() or ""
        if not args: yield event.plain_result("❌ 请指定装备名称\n💡 `pw角色面板` 查看已装备"); return
        result = self.adventure.unequip_item(user_id, args[0]); yield event.plain_result(result['msg'])
