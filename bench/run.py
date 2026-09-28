"""黑话翻译 · 真实语料验证。

语料来源：知乎「职场黑话翻译」类整理 + 面试潜台词讨论（2026-09-28 搜索获得）。
⚠️ 每一句的「来源给的真实意思」是该网页的原文表述，不是我编的。
⚠️ 但把它映射到我们的六类分类学，**是我的判断**——这一步有主观性，已在下文标注。

目的不是打分，是看**六类的分布**：
  · 某一类从不出现 → 分类学有多余的类别
  · 某一类吃掉大半 → 颗粒度不对
  · 大量句子落在「确定度低」→ 分类学缺关键类别
"""
import json, os, subprocess, sys, time, collections, statistics as st
from pathlib import Path

D = Path(__file__).parent
URL = "https://api.typesafe.ai/v1/systemone"

# ⚠️ 语料：句子来自网页，「真实意思」也是网页原话
CASES = [
    ("这事不急，慢慢来",           "今晚就要看到结果"),
    ("抽空处理一下",               "尽快，最好现在"),
    ("帮忙盯一下",                 "烂摊子甩给你，别想甩回来"),
    ("这个任务很有挑战性",         "巨坑、难搞、易背锅、没人接"),
    ("你看着办",                   "办砸了你背锅"),
    ("你们研究研究",               "建议不太行，等你们自觉放弃"),
    ("这个事你再想想",             "方案不成熟、不同意"),
    ("原则上同意",                 "细节全不满意"),
    ("原则上不行",                 "实际上可以，但有代价"),
    ("我会好好考虑下",             "想想怎么拒绝你"),
    ("我尽量吧",                   "别指望我"),
    ("你很有潜力",                 "现在能力还不行"),
    ("我对事不对人",               "就是针对你"),
    ("这事也不能赖你",             "就是你的错"),
    ("下次就有经验了",             "这次锅你背好"),
    ("找个时间聊聊",               "出事了，准备挨批"),
    ("优化组织结构",               "准备裁员"),
    ("你还年轻，以后机会多的是",   "这次机会轮不到你"),
    ("不会亏待你的",               "先拼命干，奖励再说"),
    ("明年会重点考虑",             "画饼，先拖着"),
    ("年轻人别只看钱",             "低成本榨干你"),
    ("这个岗位很锻炼人",           "事会很多"),
    ("大家还有没有什么补充的",     "客气话，方案已定，别提"),
    ("这只是我个人想法，你们有啥意见尽管提", "方案已定，反对视为对抗"),
    ("以上几点体会和建议，供大家参考", "这些要求要落实"),
    ("我们再看看",                 "大概率委婉拒绝或备胎"),
    ("后面再联系",                 "没有时间表，基本是婉拒"),
    ("有消息我们会通知你",         "不通知你，就是没过"),
    ("你的逻辑很好，但可能不太适合我们团队", "婉拒，归因于团队契合度"),
    ("按公司规章制度来",           "公司不允许，不关我事"),
]

QUESTIONS = {
    "meaning": {
        "type": "choice",
        "instructions": (
            "这句话在职场上实际是什么意思。注意：中文职场里很多话字面意思不等于真实意思——"
            "「对齐」「同步」常常表示还没定；「后面再说」「再看看」常常表示不会推进；"
            "「你自己看着办」「你来定」常常是把责任推回给对方；"
            "「这个很简单」「很快就好了」常常是在压低你对工作量的预期。"
            "有些话甚至是反着说的——说的和实际意思相反。请读出真实意图，不要只读字面。"
        ),
        "criteria": {
            "literal":     "就是字面意思，没有言外之意",
            "undecided":   "这事还没定，需要再讨论",
            "deferred":    "含糊其辞，实际上不会推进",
            "declined":    "在委婉拒绝，只是没有直说",
            "pushed_back": "把决定或责任推回给你",
            "downplayed":  "在轻描淡写，实际更严重（低估工作量、难度或紧迫性）",
        },
    },
    "boilerplate": {
        "type": "score",
        "instructions": "这句话的「套话浓度」有多高——换一个人、换一个场合说，是否也完全成立",
        "criteria": ["具体到只可能指这件事", "基本具体但留有模糊", "一半是套话",
                     "大部分是套话", "换谁都能说"],
    },
    "opposite":   {"type": "noul", "instructions": "这句话的真实意思和字面意思相反吗（说的是反话）"},
    "has_commitment": {"type": "noul", "instructions": "这句话里包含具体、可验证的承诺吗"},
    "needs_me_to_act": {"type": "noul", "instructions": "这句话把下一步动作交给了你吗"},
}


def call(state, retries=5):
    key = os.environ["TYPESAFE_API_KEY"]
    payload = {"state": {"message": state}, "model": "jev-latest", "questions": QUESTIONS}
    delay = 2.0
    for a in range(retries):
        r = subprocess.run(
            ["curl", "-s", "--max-time", "40", "-w", "\n%{http_code}", "-X", "POST", URL,
             "-H", f"Authorization: Bearer {key}", "-H", "Content-Type: application/json",
             "-d", json.dumps(payload, ensure_ascii=False)], capture_output=True, text=True)
        body, _, code = r.stdout.rpartition("\n")
        if code == "200":
            return json.loads(body)
        if code in ("429", "529") and a < retries - 1:
            time.sleep(delay); delay *= 2; continue
        raise RuntimeError(f"HTTP {code}: {body[:200]}")
    raise RuntimeError("重试用尽")


if __name__ == "__main__":
    t0 = time.time()
    call(CASES[0][0])
    rows = []
    for s, truth in CASES:
        try:
            d = call(s)
        except Exception as e:
            print(f"  {s} 失败：{e}", file=sys.stderr); continue
        m = d["answers"]["meaning"]
        rows.append({
            "sentence": s, "source_meaning": truth,
            "read_as": m["choice"], "confidence": m["confidence"],
            "probabilities": m["probabilities"],
            "opposite": d["answers"]["opposite"]["noul"],
            "boilerplate": d["answers"]["boilerplate"]["score"],
            "has_commitment": d["answers"]["has_commitment"]["noul"],
            "needs_me_to_act": d["answers"]["needs_me_to_act"]["noul"],
        })
        time.sleep(0.15)

    print("═" * 92)
    print("① 六类分布（**不看对错，只看分类学合不合用**）")
    print("═" * 92)
    dist = collections.Counter(r["read_as"] for r in rows)
    for k, v in dist.most_common():
        print(f"  {k:<12} {v:>2}  {'█' * v}")
    never = [k for k in QUESTIONS["meaning"]["criteria"] if k not in dist]
    print(f"\n  ⚠️ 从未出现的类别：{never if never else '（无）'}")

    print("\n" + "═" * 92)
    print("② 确定度分布（低确定度 = 分类学没给它位置，或这句话本就模糊）")
    print("═" * 92)
    cs = [r["confidence"] for r in rows]
    print(f"  中位 {st.median(cs):.2f}  min {min(cs):.2f}  max {max(cs):.2f}")
    print(f"  ≥0.85 斩钉截铁 : {sum(1 for c in cs if c>=.85):>2}/{len(cs)}")
    print(f"  0.55–0.85 猜的 : {sum(1 for c in cs if .55<=c<.85):>2}/{len(cs)}")
    print(f"  <0.55 读不懂   : {sum(1 for c in cs if c<.55):>2}/{len(cs)}")

    print("\n" + "═" * 92)
    print("③ 「说的是反话」维度——我怀疑这是缺失的那一类")
    print("═" * 92)
    hi = sorted([r for r in rows if r["opposite"] >= .5], key=lambda x: -x["opposite"])
    print(f"  被判为「反话」的有 {len(hi)}/{len(rows)} 条：")
    for r in hi:
        print(f"    {r['opposite']:.2f}  「{r['sentence']}」 → {r['read_as']} ({r['confidence']:.2f})")

    print("\n" + "═" * 92)
    print("④ 逐条（对照网页给出的真实意思）")
    print("═" * 92)
    print(f"  {'句子':<24} {'AI 读作':<12} {'确':<5} 反话  网页给的意思")
    for r in rows:
        print(f"  {r['sentence'][:22]:<24} {r['read_as']:<12} {r['confidence']:.2f}  "
              f"{r['opposite']:.2f}  {r['source_meaning']}")

    json.dump({"meta": {"ran_at": time.strftime("%Y-%m-%d %H:%M"), "model": "jev-latest",
                        "n": len(rows), "elapsed_s": round(time.time()-t0)},
               "rows": rows}, open(D / "result_subtext.json", "w"), ensure_ascii=False, indent=1)
    print(f"\n用时 {round(time.time()-t0)}s · 存 result_subtext.json")
