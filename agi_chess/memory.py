"""三种思考延续方式（design.md 第三节）：

  stateless  每步新开一次，看不到自己之前的任何东西。
  notes      每步回复末尾写一段「便条」给下一步的自己，程序原样转进下一步提示（默认只带最近 1 条）。
  session    每方一条连续会话（第一步 --session-id，之后 --resume），平台把之前每一轮的思考块带着。

两条硬约束：提示里不让它「回忆 / 复述上一轮的思考」（会被安全分类器拦，design.md P6）；
便条只说「写一段话，程序下一步给你看」，不列要写什么、不提思考（原因见 ASK_NOTES 上方）。
"""
import re

MODES = ('stateless', 'notes', 'session')
LANGS = ('en', 'zh')

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
_NOTE = re.compile(r'便条\s*[:：][ \t]*(.*?)(?=\n[\s*`>]*着法\s*[:：]|\Z)', re.S)


# 「模型就是真实棋手」协议（protocol=real，整盘默认；design.md 第九节）下的说法。旧说法（protocol 缺省 / legacy）一字不动，
# 局面题旧档和旧记录照旧复现。session 那句只说「同一段连续对话」，不提思考还在不在（不做保证，也不引安全分类器）。
SYSTEM_REAL = {
    'stateless': '每一步都是单独提问，你看不到自己之前的回答。每一步都会给你当前局面和对方上一步着法。',
    'notes': '每一步都是单独提问。每步回答里可以附一段便条，程序会原样放进下一步的提示里。'
             '每一步都会给你当前局面和对方上一步着法。',
    'session': '本盘在同一段连续对话中进行。每一步都会给你当前局面和对方上一步着法。',
}
SYSTEM_REAL_EN = {
    'stateless': "Each turn is an independent prompt; you cannot see your previous responses. "
                 "On each turn you will be given the current position and your opponent's last move.",
    'notes': "Each turn is an independent prompt. You may include a short note in your response, "
             "which the program will show you verbatim in the next turn's prompt. "
             "On each turn you will be given the current position and your opponent's last move.",
    'session': "This game takes place in a single continuous conversation. "
               "On each turn you will be given the current position and your opponent's last move.",
}
ASK_REAL = '请走一步。'
ASK_REAL_EN = 'Please make your move.'
ASK_NOTES_REAL = ('请走一步。回答的最后先写一段以「便条: 」开头的话（不超过约 150 字，写什么由你定），'
                  '程序会在下一步的提示里原样给你看；然后另起一行写「着法: 」加你的着法。')
ASK_NOTES_REAL_EN = ('Please make your move. Before the move line, write a short note starting with "Note: " '
                     '(up to ~80 words, content up to you), which the program will show you verbatim in the next prompt; '
                     'then on a new line write "Move: " followed by your move.')
# 整盘写理由（用户 2026-09-29 定要写）：着法之前用自己的话写出这步的理由。plain「不修饰」是默认（2026-09-30 用户定：
#   不限长短，写多少由模型自己判断），所有棋手都用；brief「简短」是之前的默认，保留可选——两者差别很小（results/
#   missed-captures.md 3.5），不当变量、数据合并统计；detailed「详细」已弃用（2026-09-30 用户定：opus 去掉此前思考 + 详细时
#   频繁被安全防护拦下，不改措辞绕），只为复现保留、须显式给。三档只差「简短」「详细」这两个字（plain 就是删掉它们）。
# 只要回答正文里的可见文字，措辞不提「思考」「思路过程」（第一批这样写被安全分类器以 reasoning_extraction 拦过，见 ASK_NOTES
# 上方和 quiz.REASON_ASK），也不设栏目、不教它怎么想。off 时和改之前逐字相同（旧记录 config 里没有 reason，按 off 走）。
# 旧记录 config 里的 reason=on：9/29 到 9/30 上午是「简短」、5baf861 起是「详细」，续跑用 config 里存下的系统提示、不经这里；
# 这里把 on 按 5baf861 的「详细」解释，只为别处按 sc 重拼时不出错。改措辞先用真实调用核实不被拦。
# 英文 real（2026-11-15 默认 lang=en）：直译「用你自己的话写出理由」时 Claude 仍写出第一人称逐格试算与自我更正独白（假设这类类 CoT
#   语体抬高输出侧反套取安全分类器误报风险）；改为客观第三人称局面短评（1-3 句、不列清单）可消除第一人称自言自语，小样本实测未见棋力退化。
REASONS = ('plain', 'brief', 'detailed', 'off')
ANSWER_LEAD = {'off': '只需给出着法，写成一行「着法: 」加着法，',
               'plain': '先用你自己的话写出这步的理由（为什么这样走），怎么写由你定；然后另起一行写「着法: 」加着法，',
               'brief': '先用你自己的话简短写出这步的理由（为什么这样走），怎么写由你定；然后另起一行写「着法: 」加着法，',
               'detailed': '先用你自己的话详细写出这步的理由（为什么这样走），怎么写由你定；然后另起一行写「着法: 」加着法，'}
ANSWER_LEAD_EN = {
    'off': 'Output only a single line "Move: " followed by your move, with no explanation or other text, ',
    'plain': 'First write a brief objective note on the position (1-3 sentences, third-person summary, no bullet lists); '
             'then on a new line write "Move: " followed by your move, ',
    'brief': 'First write a one-sentence objective note on the position in third person; '
             'then on a new line write "Move: " followed by your move, ',
    'detailed': 'First write a detailed objective note on the position in third person; '
                'then on a new line write "Move: " followed by your move, ',
}
ANSWER_LEAD_NOTES_OFF_EN = (
    'Include no explanation other than your optional "Note: " line for the next turn; '
    'on the final line write "Move: " followed by your move, '
)


def en(sc):
    """是否使用英文 real 提示词。缺省（旧记录、局面题、未设 lang 的字典）一律返回 False，逐字保持历史中文提示。"""
    return bool(sc and sc.get('lang') == 'en')


def answer_lead(sc):
    """real 协议系统提示「回答格式：」/ 'Response format: ' 后面、着法写法说明前面那半句。"""
    r = sc.get('reason')
    key = 'detailed' if r == 'on' else r if r in ANSWER_LEAD else 'off'
    if en(sc):
        if key == 'off' and sc.get('memory') == 'notes':
            return ANSWER_LEAD_NOTES_OFF_EN
        return ANSWER_LEAD_EN[key]
    return ANSWER_LEAD[key]


def brief_format(system):
    """被拦兜底（用户 2026-10-02 定，runner.model_turn）用的「简短」写理由要求：取系统提示里「回答格式：」那一段，
    把不修饰 / 详细那半句换成 brief 的，其余一字不差，附在重问后面。按存下的系统提示判、不按 sc 的 reason 判：
    旧记录 reason=on 的措辞因开局日期而异，看原文最准。本来就是简短、off（不要理由，硬加理由反倒改了要求）、
    旧协议（没有这一段）都返回 None——兜底不改变什么，重问照旧。"""
    for head, leads in (('回答格式：', ANSWER_LEAD), ('Response format: ', ANSWER_LEAD_EN)):
        para = next((x for x in (system or '').split('\n\n') if x.startswith(head)), None)
        for r in ('plain', 'detailed'):
            if para and leads[r] in para:
                return para.replace(leads[r], leads['brief'])
    return None


# 非法后告诉棋手的话（astra 定，design.md 第九节）：纯写法问题照实说，和局面有关的一律只说「不合法」，
# 不点明被将、牵制、照面、长将长捉这类会泄露对方攻击关系的原因。完整原因只进记录（attempt.reason）。
FEEDBACK = {'no_move': '回答里没有找到着法', 'unreadable': '这步的写法认不出来',
            'ambiguous': '这步的写法对应不止一步棋，请写明起点和终点坐标', 'illegal': '这步不合法'}
FEEDBACK_EN = {
    'no_move': 'no move was found in your response',
    'unreadable': 'the move notation could not be parsed',
    'ambiguous': 'that notation matches more than one move; please specify origin and destination coordinates',
    'illegal': 'that move is illegal',
}


def feedback_text(sc, fb):
    return (FEEDBACK_EN if en(sc) else FEEDBACK)[fb]


def real(sc):
    return sc.get('protocol') == 'real'


def system_text(sc):
    if real(sc):
        return (SYSTEM_REAL_EN if en(sc) else SYSTEM_REAL)[sc['memory']]
    return SYSTEM[sc['memory']]


def ask(sc):
    if real(sc):
        if en(sc):
            return ASK_NOTES_REAL_EN if sc['memory'] == 'notes' else ASK_REAL_EN
        return ASK_NOTES_REAL if sc['memory'] == 'notes' else ASK_REAL
    return ASK_NOTES if sc['memory'] == 'notes' else ASK


def redo_prompt(sc):
    return ('Please answer this turn again. ' if en(sc) else '请重新回答这一步。') + ask(sc)


def notes_text(notes, keep, sc=None):
    """上几步留的便条（最旧的在前）。没有便条返回空串。"""
    notes = [n for n in notes if n][-keep:] if keep > 0 else []
    if not notes:
        return ''
    if en(sc):
        if len(notes) == 1:
            return 'Your note from the previous turn:\n' + notes[0]
        return 'Your notes from earlier turns (oldest to newest):\n' + '\n'.join(
            '%d. %s' % (i + 1, n) for i, n in enumerate(notes))
    if len(notes) == 1:
        return '你上一步写的便条：\n' + notes[0]
    return '你前几步写的便条（从早到晚）：\n' + '\n'.join('%d. %s' % (i + 1, n) for i, n in enumerate(notes))


_MOVE_EN = re.compile(r'(?im)^[ \t*`>#_\-]*move[ \t*`_]*[:：][ \t*`_]*\s*(?![\s*`>#_\-]*move[ \t*`_]*[:：])([^\s*`_].*)')
_NOTE_EN = re.compile(r'(?im)^[ \t*`>#_\-]*note[ \t*`_]*[:：][ \t*`_]*(.*?)(?=\n[ \t*`>#_\-]*move[ \t*`_]*[:：]|\Z)', re.S)
_BARE = re.compile(r'^[\s*`>#_\-]*(.*?)[\s*`。.]*$')
_EMPTY_LABEL = re.compile(r'(?i)^(?:move|note|着法|便条)[ \t*`_]*[:：]?$')


def extract_move(reply, loose=False):
    """回复里最后一处「着法: xxx」后面的文字；没有返回 None。
    loose（新协议）：没有「着法:」时再认英文行首「Move: xxx」，还没有就取最后一个非空行（不超过 30 个字符才算，
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
        if last and len(last) <= 30 and not _EMPTY_LABEL.match(last):
            return last
    return None


_TAIL = re.compile(r'[\s*`>#_\-]+\Z')


def extract_reason(reply):
    """回复里着法之外棋手自己写的说明（导出棋谱时放进评注）；没有返回 None。
    切点和 extract_move(loose=True) 找着法的次序一致：最后一处「着法:」、再英文「Move:」，优先取标记前面的文字；
    若标记在开头（前面为空，如先写 Move: 再写说明）则取该着法行之后的文字；都没有就去掉最后一个非空行。"""
    text = reply or ''
    cut, end = None, None
    for rx in (_MOVE, _MOVE_EN):
        hits = list(rx.finditer(text))
        if hits:
            cut, end = hits[-1].start(), hits[-1].end()
            break
    if cut is None:
        lines = text.rstrip().rsplit('\n', 1)
        cut = len(lines[0]) if len(lines) == 2 else 0
    why = _TAIL.sub('', text[:cut]).strip()
    if not why and end is not None:
        why = _TAIL.sub('', text[end:]).strip()
    return why or None


def extract_note(reply):
    """回复里最后一段「便条: …」或英文「Note: …」（到「着法:」/「Move:」那行为止）；没有返回 None。"""
    hits = _NOTE.findall(reply or '') or _NOTE_EN.findall(reply or '')
    if not hits:
        return None
    note = hits[-1].strip().strip('`*').strip()
    return note or None


def retry_prompt_real(sc, base, bad, left):
    """新协议的重选话术。bad 是 [(模型写的, 给棋手看的原因)]；session 只说刚才那步，其余把各次错着列回完整提示。"""
    if en(sc):
        norm = [('(none)' if m == '（没写）' else m, why) for m, why in bad]
        tail = '%d %s remaining on this turn before forfeit.' % (left, 'retry' if left == 1 else 'retries')
        if sc['memory'] == 'session':
            return 'Your previous move "%s": %s. Please make another move (%s)' % (norm[-1][0], norm[-1][1], tail)
        return (base + '\n\nMoves you already tried on this turn:\n'
                + '\n'.join('"%s": %s' % x for x in norm)
                + '\nPlease make another move (%s)' % tail)
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
