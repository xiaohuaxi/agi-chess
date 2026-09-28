"""三种思考延续方式（design.md 第三节）：

  stateless  每步新开一次，看不到自己之前的任何东西。
  notes      每步回复末尾写一段「便条」给下一步的自己，程序原样转进下一步提示（默认只带最近 1 条）。
  session    每方一条连续会话（第一步 --session-id，之后 --resume），平台把之前每一轮的思考块带着。

两条硬约束：提示里不让它「回忆 / 复述上一轮的思考」（会被安全分类器拦，design.md P6）；
便条只说「写一段话，程序下一步给你看」，不列要写什么、不提思考（原因见 ASK_NOTES 上方）。
"""
import re

MODES = ('stateless', 'notes', 'session')

SYSTEM = {
    'stateless': '每一步都是单独提问，你看不到自己之前的思考和回答。',
    'notes': '每一步都是单独提问。每步回答里可以附一段便条，程序会原样放进下一步的提示里。',
    'session': '这是一段连续的对话，你前面几步的思考和回答都还在。',
}

ASK = '请走一步。最后一行只写「着法: 」加你的着法。'
# 便条措辞是刻意的例外，别改回「列内容」的写法：冒烟时（2026-09-25，opus medium）原版「留给下一步的自己，写当前意图、
# 预料对手怎么应、下一两步打算、要提防的坑」配系统提示「你看不到自己之前的思考」，国际象棋首步 2 次都被安全分类器以
# reasoning_extraction 拒答，只改系统提示或只改要求的三种写法又拒 3 次；下面这版（不列内容、系统提示不提思考）
# 两种棋 4 次全过，模型自己会写意图和计划。以后改措辞，先用几次真实调用核实不被拦。
ASK_NOTES = ('请走一步。回答的最后先写一段以「便条: 」开头的话（不超过约 150 字，写什么由你定），'
             '程序会在下一步的提示里原样给你看；然后最后一行只写「着法: 」加你的着法。')

# 冒号后可以跨行找着法（「着法：」换行再写着法也认），但跳过的空白（和 markdown 的 * ` > # - 之类）后面紧跟着
# 又一个「着法」就不算这一处：
# 第二批 B1 见过模型改口「……应当写皇后的着法：\n\n着法: g3e3」，旧写法 \s*(.+) 把「着法: g3e3」整段当成着法、判非法。
_MOVE = re.compile(r'着法[ \t]*[:：]\s*(?![\s*`>#_\-]*着法)(\S.*)')
_NOTE = re.compile(r'便条\s*[:：]\s*(.*?)(?=\n[\s*`>]*着法\s*[:：]|\Z)', re.S)


# 「模型就是真实棋手」协议（protocol=real，整盘默认；design.md 第九节）下的说法。旧说法（protocol 缺省 / legacy）一字不动，
# 局面题旧档和旧记录照旧复现。session 那句只说「同一段连续对话」，不提思考还在不在（不做保证，也不引安全分类器）。
SYSTEM_REAL = {
    'stateless': '每一步都是单独提问，你看不到自己之前的回答。每一步都会给你当前局面和对方上一步着法。',
    'notes': '每一步都是单独提问。每步回答里可以附一段便条，程序会原样放进下一步的提示里。'
             '每一步都会给你当前局面和对方上一步着法。',
    'session': '本盘在同一段连续对话中进行。每一步都会给你当前局面和对方上一步着法。',
}
ASK_REAL = '请走一步。'
ASK_NOTES_REAL = ('请走一步。回答的最后先写一段以「便条: 」开头的话（不超过约 150 字，写什么由你定），'
                  '程序会在下一步的提示里原样给你看；然后另起一行写「着法: 」加你的着法。')
# 非法后告诉棋手的话（astra 定，design.md 第九节）：纯写法问题照实说，和局面有关的一律只说「不合法」，
# 不点明被将、牵制、照面、长将长捉这类会泄露对方攻击关系的原因。完整原因只进记录（attempt.reason）。
FEEDBACK = {'no_move': '回答里没有找到着法', 'unreadable': '这步的写法认不出来',
            'ambiguous': '这步的写法对应不止一步棋，请写明起点和终点坐标', 'illegal': '这步不合法'}


def real(sc):
    return sc.get('protocol') == 'real'


def system_text(sc):
    return (SYSTEM_REAL if real(sc) else SYSTEM)[sc['memory']]


def ask(sc):
    if real(sc):
        return ASK_NOTES_REAL if sc['memory'] == 'notes' else ASK_REAL
    return ASK_NOTES if sc['memory'] == 'notes' else ASK


def notes_text(notes, keep):
    """上几步留的便条（最旧的在前）。没有便条返回空串。"""
    notes = [n for n in notes if n][-keep:] if keep > 0 else []
    if not notes:
        return ''
    if len(notes) == 1:
        return '你上一步写的便条：\n' + notes[0]
    return '你前几步写的便条（从早到晚）：\n' + '\n'.join('%d. %s' % (i + 1, n) for i, n in enumerate(notes))


_MOVE_EN = re.compile(r'(?i)\bmove[ \t]*[:：]\s*(\S.*)')
_BARE = re.compile(r'^[\s*`>#_\-]*(.*?)[\s*`。.]*$')


def extract_move(reply, loose=False):
    """回复里最后一处「着法: xxx」后面的文字；没有返回 None。
    loose（新协议）：没有「着法:」时再认英文「Move: xxx」，还没有就取最后一个非空行（不超过 30 个字符才算，
    去掉 markdown 记号）——棋手只给一行着法、或用英文作答也能读出来；读出的是不是着法由棋种的 parse 判。"""
    hits = _MOVE.findall(reply or '')
    if hits:
        return hits[-1].strip()
    if not loose:
        return None
    hits = _MOVE_EN.findall(reply or '')
    if hits:
        return hits[-1].strip()
    lines = [x for x in (reply or '').splitlines() if x.strip()]
    if lines:
        last = _BARE.match(lines[-1].strip())[1].strip()
        if last and len(last) <= 30:
            return last
    return None


def extract_note(reply):
    """回复里最后一段「便条: …」（到「着法:」那行为止）；没有返回 None。"""
    hits = _NOTE.findall(reply or '')
    if not hits:
        return None
    note = hits[-1].strip().strip('`*').strip()
    return note or None


def retry_prompt_real(sc, base, bad, left):
    """新协议的重选话术。bad 是 [(模型写的, 给棋手看的原因)]；session 只说刚才那步，其余把各次错着列回完整提示。"""
    tail = '本步还可重选 %d 次，用完判负。' % left
    if sc['memory'] == 'session':
        return '你刚才的着法「%s」：%s。请重新走一步（%s）' % (bad[-1][0], bad[-1][1], tail)
    return base + '\n\n你这一步前面给出的着法：\n' + '\n'.join('「%s」：%s' % x for x in bad) + '\n请重新走一步（%s）' % tail


def retry_prompt(sc, base, bad, left):
    """非法着法后的重试话术。session 只说一句「刚才那步不能走」（前文还在会话里）；其余把全部错着列回完整提示。
    bad 是 [(模型写的, 原因)]，left 是还剩几次机会。"""
    if sc['memory'] == 'session':
        return '你刚才的着法「%s」不能走：%s。请重新走一步（还剩 %d 次机会，用完判负）。最后一行只写「着法: 」加着法。' % (
            bad[-1][0], bad[-1][1], left)
    return base + '\n\n注意：你前面给出的这些着法不能走——\n' + '\n'.join('「%s」：%s' % x for x in bad) + \
        '\n请换一步（还剩 %d 次机会，用完判负）。' % left
