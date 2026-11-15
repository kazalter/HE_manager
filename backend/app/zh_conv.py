"""Lightweight zero-dependency Traditional/Simplified Chinese & Shinjitai converter.

Designed for pure-Python execution inside the slim backend container without
adding heavy external wheels like OpenCC.
"""
from __future__ import annotations

import re

# Bidirectional Traditional Chinese <-> Simplified Chinese character pairs.
# Each whitespace-separated token is exactly 2 chars: <Traditional><Simplified>.
# When multiple Traditional chars map to the same Simplified char, put the primary
# Traditional char first so S->T picks the most common Traditional form.
_PAIR_TOKENS = (
    "萬万 與与 醜丑 專专 業业 叢丛 東东 絲丝 丟丢 兩两 嚴严 喪丧 個个 臨临 為为 麗丽 舉举 "
    "麼么 義义 烏乌 樂乐 喬乔 習习 鄉乡 書书 買买 亂乱 乾干 爭争 於于 虧亏 雲云 亞亚 產产 "
    "畝亩 親亲 褻亵 億亿 僅仅 從从 侖仑 倉仓 儀仪 們们 價价 眾众 優优 夥伙 會会 傘伞 偉伟 "
    "傳传 傷伤 倫伦 偽伪 偵侦 側侧 僑侨 傑杰 備备 傢家 傾倾 僕仆 儲储 兒儿 兌兑 黨党 內内 "
    "關关 興兴 茲兹 養养 獸兽 冊册 寫写 軍军 農农 衝冲 決决 況况 凍冻 凜凛 幾几 鳳凤 凱凯 "
    "憑凭 擊击 鑿凿 劃划 劉刘 則则 剛刚 創创 刪删 別别 劑剂 劍剑 剝剥 劇剧 勸劝 動动 務务 "
    "勝胜 勞劳 勢势 勵励 匯汇 區区 醫医 華华 協协 單单 賣卖 盧卢 衛卫 卻却 廠厂 廳厅 歷历 "
    "厲厉 壓压 厭厌 廁厕 參参 雙双 變变 敘叙 號号 聽听 啟启 吳吴 員员 嗚呜 喚唤 嘆叹 嘔呕 "
    "嘗尝 嘯啸 噴喷 嚇吓 園园 圍围 圖图 團团 圓圆 國国 場场 壞坏 堅坚 壇坛 壩坝 墜坠 墳坟 "
    "墮堕 牆墙 增增 墾垦 壘垒 壯壮 壽寿 處处 復复 夠够 夢梦 頭头 夾夹 奪夺 奮奋 奧奥 妝妆 "
    "婦妇 媽妈 娛娱 婭娅 嬌娇 嬰婴 贏赢 學学 孫孙 實实 宮宫 寢寝 寧宁 審审 寬宽 寵宠 寶宝 "
    "將将 尋寻 對对 導导 爾尔 尷尴 盡尽 層层 屆届 屍尸 屬属 屢屡 岡岗 巖岩 嶽岳 嶺岭 嵐岚 "
    "幣币 師师 帶带 帳帐 幫帮 幹干 庫库 廟庙 廢废 廣广 開开 異异 棄弃 張张 強强 彈弹 彌弥 "
    "彎弯 歸归 當当 錄录 彥彦 徹彻 憶忆 恆恒 恥耻 悅悦 悶闷 惡恶 惱恼 愛爱 態态 慘惨 慣惯 "
    "慮虑 慶庆 憂忧 慾欲 憲宪 應应 懶懒 懷怀 懸悬 戀恋 戰战 戲戏 戶户 掃扫 擴扩 拋抛 擁拥 "
    "攔拦 擰拧 撥拨 擇择 挾挟 損损 撿捡 換换 據据 掙挣 採采 揀拣 揚扬 揮挥 援援 搖摇 搶抢 "
    "攜携 攝摄 擺摆 攤摊 撐撑 撫抚 撲扑 擋挡 擔担 擠挤 擬拟 擾扰 攪搅 敗败 數数 敵敌 斷断 "
    "無无 舊旧 時时 晝昼 曉晓 暈晕 暫暂 暢畅 曆历 條条 來来 極极 構构 槍枪 楓枫 柵栅 標标 "
    "棟栋 欄栏 樹树 樣样 檢检 棲栖 楊杨 樓楼 榮荣 盤盘 樺桦 橋桥 機机 橫横 檔档 櫻樱 權权 "
    "歐欧 歡欢 歲岁 殘残 殺杀 殼壳 毀毁 氣气 漢汉 污污 湯汤 沒没 沖冲 淚泪 湧涌 淺浅 漿浆 "
    "澆浇 測测 濟济 渾浑 濃浓 涼凉 淨净 淵渊 漸渐 湊凑 溫温 滅灭 滑滑 滾滚 滿满 漁渔 漏漏 "
    "潰溃 潤润 澤泽 濁浊 濕湿 濤涛 濫滥 濱滨 濾滤 瀉泻 瀏浏 瀕濒 瀟潇 瀨濑 灘滩 灣湾 靈灵 "
    "災灾 爐炉 點点 烏乌 營营 爛烂 爺爷 牽牵 狀状 獨独 狹狭 獅狮 獄狱 獵猎 獻献 環环 現现 "
    "瑣琐 瑪玛 電电 畢毕 畫画 療疗 癡痴 癢痒 蓋盖 監监 睜睁 瞇眯 矚瞩 碼码 磚砖 礦矿 祕秘 "
    "禮礼 種种 稱称 稅税 穩稳 積积 穢秽 窮穷 窺窥 競竞 筆笔 篩筛 簡简 節节 範范 築筑 籌筹 "
    "簽签 籃篮 籠笼 籤签 類类 糧粮 糾纠 紀纪 約约 紅红 紋纹 納纳 紐纽 純纯 紙纸 級级 紛纷 "
    "細细 紹绍 紳绅 終终 組组 結结 絕绝 絞绞 統统 經经 綠绿 維维 綱纲 網网 綴缀 緊紧 綿棉 "
    "線线 編编 緩缓 緬缅 緯纬 練练 緣缘 縛缚 縫缝 縮缩 縱纵 總总 績绩 繃绷 織织 繞绕 繪绘 "
    "繩绳 繳缴 繼继 續续 纖纤 羅罗 罰罚 罵骂 罷罢 聯联 聰聪 聲声 職职 脅胁 脈脉 脫脱 臉脸 "
    "脹胀 腦脑 腫肿 腳脚 腸肠 膚肤 膠胶 膩腻 膽胆 臥卧 臺台 艦舰 莊庄 莖茎 葉叶 著着 蒼苍 "
    "蓮莲 蔭荫 蕩荡 蕭萧 薦荐 薩萨 藥药 藍蓝 藝艺 蘇苏 蘭兰 虛虚 虜虏 蟲虫 蠟蜡 術术 裝装 "
    "補补 褲裤 製制 複复 襪袜 襯衬 襲袭 覆覆 見见 規规 視视 覺觉 覽览 觀观 觸触 訂订 計计 "
    "訊讯 討讨 訓训 記记 訪访 設设 許许 訴诉 診诊 註注 証证 評评 詞词 試试 詩诗 話话 該该 "
    "詳详 誇夸 認认 誓誓 誕诞 語语 誠诚 誤误 說说 誰谁 課课 調调 談谈 請请 諒谅 論论 諸诸 "
    "諺谚 諾诺 謀谋 謂谓 講讲 謝谢 證证 識识 譜谱 譯译 議议 護护 讀读 讓让 讚赞 豐丰 豬猪 "
    "貓猫 貝贝 貞贞 負负 財财 貢贡 貧贫 貨货 販贩 貪贪 貫贯 責责 貯贮 貴贵 買买 費费 貼贴 "
    "賀贺 資资 賊贼 賓宾 賞赏 賠赔 賢贤 賦赋 質质 賭赌 賴赖 賺赚 購购 賽赛 贈赠 趕赶 趙赵 "
    "趨趋 跡迹 軀躯 車车 軌轨 軒轩 軟软 輕轻 較较 載载 輝辉 輩辈 輪轮 輯辑 輸输 轉转 轟轰 "
    "辦办 辭辞 辯辩 邊边 達达 違违 遙遥 遜逊 遞递 遠远 適适 遲迟 遷迁 選选 遺遗 還还 邁迈 "
    "郵邮 醬酱 釋释 針针 釘钉 釣钓 鈴铃 銀银 銅铜 銘铭 銜衔 銷销 鋁铝 鋒锋 鋼钢 錢钱 錦锦 "
    "錯错 鍋锅 鍛锻 鍵键 鐘钟 鎮镇 鏡镜 鐵铁 鑑鉴 長长 門门 閃闪 閉闭 閏闰 閒闲 間间 閣阁 "
    "閱阅 閹阉 閻阎 闊阔 陰阴 陳陈 陸陆 陽阳 隊队 階阶 際际 隱隐 鄰邻 隸隶 隻只 雜杂 雞鸡 "
    "離离 難难 霧雾 靜静 響响 頁页 頂顶 頃顷 項项 順顺 須须 預预 頑顽 頓顿 頗颇 領领 頰颊 "
    "頸颈 頻频 顆颗 題题 額额 顏颜 願愿 顧顾 顯显 風风 飄飘 飛飞 飯饭 飲饮 飽饱 飾饰 餅饼 "
    "館馆 馬马 驅驱 駁驳 駐驻 駕驾 駛驶 駝驼 驗验 騎骑 騙骗 騷骚 體体 鬧闹 鬥斗 鬱郁 "
    "魚鱼 魯鲁 鮮鲜 鯉鲤 鯨鲸 鳥鸟 鳴鸣 鴉鸦 鴨鸭 鴻鸿 鵝鹅 鶴鹤 鷹鹰 麥麦 麵面 黃黄 齊齐 "
    "齋斋 齒齿 齡龄 龍龙 龜龟 誌志 檔档 姫姬 姉姐 後后 發发 蘿萝 並并 塗涂 溼湿 產产 紓纾 "
    "紺绀 綁绑 綺绮 綾绫 繆缪 裏里 貸贷 連连 進进 遊游 運运 過过 鋸锯 錠锭 鏈链 鐘钟 "
    "閑闲 闇暗 漲涨 潔洁 潛潜 演演 漬渍 漸渐"
)

# One-way Japanese Shinjitai / variant -> Simplified mappings (must NOT pollute S->T).
_SHINJITAI_TOKENS = (
    "髮发 裡里 黒黑 気气 悪恶 戦战 戯戏 転转 絵绘 続续 桜樱 楽乐 広广 実实 仮假 読读 訳译 発发 "
    "駅驿 剣剑 団团 専专 対对 伝传 円圆 写写 歯齿 庁厅 辺边 処处 図图 圧压 増增 壊坏 "
    "売卖 査查 歳岁 残残 満满 瀬濑 竜龙 薬药 軽轻 関关 郷乡 倶俱 焼烧 獣兽 独独 狭狭 "
    "献献 県县 経经 継继 総総 緑绿 縁缘 縄绳 繊纤 聴听 脳脑 臓脏 荘庄 蛍萤 覚觉 覧览 "
    "観观 証证 諸诸 譲让 豊丰 賛赞 辞辞 遅遅 銭钱 鉄铁 鉱矿 陥陷 険险 隠隐 雑杂 難难 "
    "霊灵 頼赖 顔颜 顕显 駆驱 騒骚 髪发 闘斗 鶏鸡 麺面 麦麦 齢龄 爲为"
)

_T2S_MAP: dict[int, str] = {}
_S2T_MAP: dict[int, str] = {}

for _pair in _PAIR_TOKENS.split():
    if len(_pair) != 2:
        raise ValueError(f"Invalid trad/simp pair token: {_pair!r}")
    _trad, _simp = _pair[0], _pair[1]
    if _trad != _simp:
        _T2S_MAP.setdefault(ord(_trad), _simp)
        _S2T_MAP.setdefault(ord(_simp), _trad)

for _pair in _SHINJITAI_TOKENS.split():
    if len(_pair) != 2:
        raise ValueError(f"Invalid shinjitai pair token: {_pair!r}")
    _variant, _simp = _pair[0], _pair[1]
    if _variant != _simp:
        _T2S_MAP.setdefault(ord(_variant), _simp)

_CJK_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")


def to_simplified(text: str) -> str:
    """Convert Traditional Chinese / Shinjitai CJK characters to Simplified Chinese."""
    if not text:
        return ""
    return text.translate(_T2S_MAP)


def to_traditional(text: str) -> str:
    """Convert Simplified Chinese characters to primary Traditional equivalents."""
    if not text:
        return ""
    return text.translate(_S2T_MAP)


def expand_zh_variants(text: str) -> list[str]:
    """Return deduplicated [original, simplified, traditional, ...] variants for search."""
    raw = (text or "").strip()
    if not raw:
        return []
    out: list[str] = [raw]
    if _CJK_CHAR_RE.search(raw):
        simp = to_simplified(raw)
        if simp and simp not in out:
            out.append(simp)
        trad = to_traditional(raw)
        if trad and trad not in out:
            out.append(trad)
        # Disambiguate 1-to-2 Simplified '发' (發/髮) for hair tags like 长发/黑发/超长发
        if "发" in simp:
            hair_trad = trad.replace("發", "髮")
            if hair_trad and hair_trad not in out:
                out.append(hair_trad)
    return out
