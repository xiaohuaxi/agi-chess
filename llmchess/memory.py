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

_MOVE = re.compile(r'着法\s*[:：]\s*(.+)')
_NOTE = re.compile(r'便条\s*[:：]\s*(.*?)(?=\n[\s*`>]*着法\s*[:：]|\Z)', re.S)


def system_text(sc):
    return SYSTEM[sc['memory']]


def ask(sc):
    return ASK_NOTES if sc['memory'] == 'notes' else ASK


def notes_text(notes, keep):
    """上几步留的便条（最旧的在前）。没有便条返回空串。"""
    notes = [n for n in notes if n][-keep:] if keep > 0 else []
    if not notes:
        return ''
    if len(notes) == 1:
        return '你上一步写的便条：\n' + notes[0]
    return '你前几步写的便条（从早到晚）：\n' + '\n'.join('%d. %s' % (i + 1, n) for i, n in enumerate(notes))


def extract_move(reply):
    """回复里最后一处「着法: xxx」后面的文字；没有返回 None。"""
    hits = _MOVE.findall(reply or '')
    return hits[-1].strip() if hits else None


def extract_note(reply):
    """回复里最后一段「便条: …」（到「着法:」那行为止）；没有返回 None。"""
    hits = _NOTE.findall(reply or '')
    if not hits:
        return None
    note = hits[-1].strip().strip('`*').strip()
    return note or None


def retry_prompt(sc, base, bad, left):
    """非法着法后的重试话术。session 只说一句「刚才那步不能走」（前文还在会话里）；其余把全部错着列回完整提示。
    bad 是 [(模型写的, 原因)]，left 是还剩几次机会。"""
    if sc['memory'] == 'session':
        return '你刚才的着法「%s」不能走：%s。请重新走一步（还剩 %d 次机会，用完判负）。最后一行只写「着法: 」加着法。' % (
            bad[-1][0], bad[-1][1], left)
    return base + '\n\n注意：你前面给出的这些着法不能走——\n' + '\n'.join('「%s」：%s' % x for x in bad) + \
        '\n请换一步（还剩 %d 次机会，用完判负）。' % left
