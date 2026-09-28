#!/usr/bin/env python3
"""职场黑话翻译 · 最小版后端（零依赖，只用标准库）。

⚠️ API key 只在服务端读取，永不进前端。
   官方明确要求："Keep API credentials server-side in web apps."（typesafe-ai SKILL.md）

运行：
    set -a; . ~/.config/subtext.env; set +a; python3 server.py
    # 或已存进 Keyward 后：
    kw exec -f .env -- python3 server.py        # .env 内容：TYPESAFE_API_KEY=keyward://typesafe-api-key

打开 http://127.0.0.1:8765
"""
import json
import os
import subprocess
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).parent
URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"

# ── 判断设计：五个维度一次问完（官方：同一 state 上的独立问题并行求值，加问题几乎不增延迟）──
QUESTIONS = {
    # 主判断：卡片的主角，置信度取它
    "meaning": {
        "type": "choice",
        "instructions": (
            "这句话在职场上实际是什么意思。注意：中文职场里很多话字面意思不等于真实意思——"
            "「对齐」「同步」常常表示还没定；「后面再说」「再看看」常常表示不会推进；"
            "「你自己看着办」「你来定」常常是把责任推回给对方；"
            "「这个很简单」「很快就好了」常常是在压低你对工作量的预期。"
            "请读出真实意图，不要只读字面。"
        ),
        "criteria": {
            "literal":     "就是字面意思，没有言外之意",
            "undecided":   "这事还没定，需要再讨论",
            "deferred":    "含糊其辞，实际上不会推进",
            "declined":    "在委婉拒绝，只是没有直说",
            "pushed_back": "把决定或责任推回给你",
            "downplayed":  "在轻描淡写，实际没那么简单（低估了工作量或难度）",
        },
    },
    # 三个支撑维度
    "boilerplate": {
        "type": "score",
        "instructions": "这句话的「套话浓度」有多高——换一个人、换一个场合说，是否也完全成立",
        "criteria": ["具体到只可能指这件事", "基本具体但留有模糊", "一半是套话",
                     "大部分是套话", "换谁都能说"],
    },
    "has_commitment": {
        "type": "noul",
        "instructions": "这句话里包含具体、可验证的承诺吗（明确的交付物或时间点）",
    },
    "is_deflecting": {
        "type": "noul",
        "instructions": "这句话是在回避或转移话题，而不是给出一个明确结论吗",
    },
    "needs_me_to_act": {
        "type": "noul",
        "instructions": "这句话把下一步动作交给了你吗（需要你来推进或做决定）",
    },
}


def ask_jev(message: str, context: str = ""):
    """调 Jev。用 curl 而非 python urllib —— 代理会切掉 Python 的 TLS（本项目踩过）。"""
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key:
        raise RuntimeError("缺少 TYPESAFE_API_KEY 环境变量")

    state = {"message": message}
    if context.strip():
        state["context"] = context.strip()

    payload = {"state": state, "model": MODEL, "questions": QUESTIONS}
    r = subprocess.run(
        ["curl", "-s", "--max-time", "40", "-w", "\n%{http_code}", "-X", "POST", URL,
         "-H", f"Authorization: Bearer {key}",
         "-H", "Content-Type: application/json",
         "-d", json.dumps(payload, ensure_ascii=False)],
        capture_output=True, text=True)
    body, _, code = r.stdout.rpartition("\n")
    if code != "200":
        raise RuntimeError(f"上游返回 {code}：{body[:200]}")

    d = json.loads(body)
    a = d["answers"]
    return {
        "meaning": {
            "choice": a["meaning"]["choice"],
            "confidence": a["meaning"]["confidence"],
            "probabilities": a["meaning"]["probabilities"],
        },
        "boilerplate": {
            "score": a["boilerplate"]["score"],
            "confidence": a["boilerplate"]["confidence"],
            "legend": a["boilerplate"].get("legend", {}),
        },
        "has_commitment": {"noul": a["has_commitment"]["noul"]},
        "is_deflecting": {"noul": a["is_deflecting"]["noul"]},
        "needs_me_to_act": {"noul": a["needs_me_to_act"]["noul"]},
        "model": d.get("model", ""),
        "usage": d.get("usage", {}),
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s\n" % (fmt % args))

    def _json(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        if self.path != "/api/analyze":
            return self._json(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n) or b"{}")
            msg = (req.get("message") or "").strip()
            if not msg:
                return self._json(400, {"error": "请先写一句话"})
            if len(msg) > 600:
                return self._json(400, {"error": "太长了，控制在 600 字以内"})
            self._json(200, ask_jev(msg, req.get("context") or ""))
        except Exception as e:
            self._json(500, {"error": str(e)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8765))
    if not os.environ.get("TYPESAFE_API_KEY"):
        print("⚠️  没有 TYPESAFE_API_KEY —— 页面能打开，但判断会失败。")
        print("   先跑：set -a; . ~/.config/subtext.env; set +a")
    print(f"\n  ▸ http://127.0.0.1:{port}\n")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
