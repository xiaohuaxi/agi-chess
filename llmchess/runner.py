"""对局循环（两种棋共用一份）：轮到谁 → 棋种拼提示 → 调棋手（模型 / 引擎 / 随机，直接分支）→ 棋种解析判合法（含禁着）
→ 重试 / 判负 → 落子 → 棋种判终局 → 记录；暂停与续跑。

棋种模块 G 提供的函数见 design.md 第二节：start / turn / legal / banned / parse / push / ending / in_check /
render / last_move_text / system_prompt / recite_score / exports / engine_spec / to_engine / from_engine，常量 SIDES。
"""
import os, random, re, time, uuid

from . import chat, claude_cli, codex_cli, memory, opening, records
from .claude_cli import Paused, Refused, ToolAttempt
from .engine import Engine, EngineError

FORFEIT_NOTE = ('重试用完仍非法判负：替它随便走一步会把随机或引擎的着法混进它的棋里，判负最干净；'
                '实际很少触发，触发了也在记录里单列')
MAX_FLAGS = 2          # 一个半回合里正文为空的次数上限；明确拒答一次即终止
CAP_MARGIN = 300       # 有引擎一方的对局满半回合上限时，一方领先这么多厘兵判胜，否则判和（用户 2026-10-04 定，cli.cap_margin）


def other(side):
    return 'b' if side == 'w' else 'w'


def player_kind(spec):
    return spec.split(':', 1)[0]


MODEL_KINDS = chat.KINDS                     # 模型棋手：claude / codex（GPT）/ deepseek / gemini / agy
# 调用走哪条路看 config 的 backend：'llm-chat'（新开的整盘，chat.py）；缺省是旧路（claude -p 直调、codex exec 只支持无状态），
# 旧记录续跑和局面题都走旧路，逐字复现。


def new_ctx(G, cfg, run_dir):
    """一盘棋的运行状态。st 是棋种状态；stats 每个半回合一条；sessions / notes / seen_flags 按方存。"""
    # claude 的运行目录：仓库外的空临时目录（cli 建盘时定下、记进 config，续跑沿用同一路径，会话记录按它存），
    # 这样往上找不到本仓库的 CLAUDE.md / AGENTS.md 和项目记忆（design.md P7、P17）
    cwd = cfg.get('claude_cwd') or os.path.join(run_dir, 'cwd')
    return {'G': G, 'cfg': cfg, 'st': G.start(), 'dir': run_dir, 'log': os.path.join(run_dir, 'game.jsonl'),
            'cwd': cwd, 'stats': [], 'sessions': {}, 'notes': {'w': [], 'b': []}, 'seen_flags': {},
            'cost_total': {}, 'end': None, 'engines': {}}


def load(G, run_dir):
    """按记录重放到最后一步：局面（含完整历史，判重复用）、统计、会话 id、便条、已见过的拦截数、终局。"""
    recs = records.read(os.path.join(run_dir, 'game.jsonl'))
    assert recs and recs[0]['type'] == 'config', '记录第一行应是 config'
    cfg = recs[0]['cfg']
    ctx = new_ctx(G, cfg, run_dir)
    st = ctx['st']
    for r in recs[1:]:
        t = r['type']
        if t == 'move':
            assert r['ply'] == len(st['moves']) + 1, ('记录里的半回合号对不上', r['ply'], len(st['moves']))
            G.push(st, r['move'])
            ctx['stats'].append(r['stat'])
            if cfg['sides'][r['side']]['memory'] == 'notes':
                ctx['notes'][r['side']].append(r.get('note'))
        elif t == 'attempt' and r.get('session'):
            ctx['sessions'][r['side']] = r['session']
        elif t == 'session_start' and claude_cli.transcript_path(ctx['cwd'], r['session']).exists():
            ctx['sessions'][r['side']] = r['session']      # 第一次调用没成功回来，但会话已经建好
        elif t == 'flag' and r.get('source') == 'transcript':
            ctx['seen_flags'][r['session']] = r['count']
        elif t == 'forfeit':
            ctx['stats'].append(r['stat'])
            ctx['end'] = r['end']
        elif t == 'end':
            ctx['end'] = r['end']
    ctx['cost_total'] = records.attempt_costs(recs)[1]     # 各会话上一次调用的累计花费，续跑接着做差
    ctx['refusal'] = refusal_record(recs)
    ctx['tool_call'] = tool_record(recs)
    ctx['uncertain'] = uncertain_record(recs, cfg)
    ctx['pending'] = pending_ply(recs, len(st['moves']) + 1)
    return ctx


def uncertain_record(recs, cfg):
    blockers = uncertain_records(recs, cfg)
    return next((r for r in blockers.values() if r['type'] == 'call_fail'),
                next(iter(blockers.values()), None))


def idle_retry_event(blockers):
    """只授权一个有明确 idle timeout 失败的调用；索引是解析后的记录序号（从 0 起）。"""
    starts = [(i, r) for i, r in blockers.items() if r['type'] == 'call_started']
    fails = [(i, r) for i, r in blockers.items() if r['type'] == 'call_fail']
    if len(starts) != 1 or len(fails) != 1:
        return None
    si, start = starts[0]
    fi, fail = fails[0]
    if (si >= fi or not start.get('call_id')
            or (start.get('side'), start.get('ply')) != (fail.get('side'), fail.get('ply'))
            or fail.get('call_id', start['call_id']) != start['call_id']):
        return None
    evidence = '\n'.join(str(fail.get(k) or '') for k in ('stdout', 'stderr'))
    if (not re.search(r'stream idle timeout \([0-9hms.]+\):\s*context deadline exceeded', evidence)
            or claude_cli.tool_error_text(evidence) or claude_cli.refusal_text(evidence)):
        return None
    return {'type': 'retry_idle_timeout', 'failed_record': fi, 'started_record': si,
            'call_id': start['call_id'], 'side': start['side'], 'ply': start['ply']}


def uncertain_records(recs, cfg):
    """保留每个未完成调用与失败；显式授权只能解除精确匹配的旧 idle failure。"""
    pending = {}
    failures = {}
    for i, r in enumerate(recs):
        side = r.get('side')
        agy = player_kind(cfg.get('players', {}).get(side, '')) in chat.AGY_KINDS
        if r['type'] == 'call_fail' and agy:
            failures[i] = r
        if r['type'] == 'call_started' and agy:
            pending[i] = r
        if r['type'] == 'attempt' and r.get('call_id'):
            # 合法答案直到 move 落盘才完成；否则崩溃后会把同一步再发一次。
            if not r.get('legal'):
                pending = {key: value for key, value in pending.items()
                           if value['call_id'] != r['call_id']}
        if r['type'] == 'move':
            pending = {key: value for key, value in pending.items()
                       if (value['ply'], value['side']) != (r['ply'], side)}
        if r['type'] == 'retry_idle_timeout':
            expected = idle_retry_event({**pending, **failures})
            if expected and all(r.get(k) == v for k, v in expected.items()):
                pending.pop(expected['started_record'])
                failures.pop(expected['failed_record'])
    return {**pending, **failures}


def authorize_idle_retry(ctx):
    recs = records.read(ctx['log'])
    if refusal_record(recs) or tool_record(recs):
        return False
    event = idle_retry_event(uncertain_records(recs, ctx['cfg']))
    if not event or event['ply'] != len(ctx['st']['moves']) + 1 or event['side'] != ctx['G'].turn(ctx['st']):
        return False
    # 用户显式接受这次超时可能已在后端执行的风险；不是成功回执，也不修改会话历史。
    log(ctx, event)
    ctx['uncertain'] = None
    return True


UNCERTAIN_MESSAGE = '会话调用结果待核验，禁止自动重发或续跑；保留原始记录，不能视为棋手输。'
TOOL_MESSAGE = '棋手出现工具调用或尝试，已暂停；先分析原因，禁止自动重试或续跑。'


def tool_record(recs):
    return next((r for r in recs if (r['type'] == 'flag' and r.get('source') == 'tool_call')
                 or (r['type'] == 'call_fail' and any(claude_cli.tool_error_text(r.get(key))
                                                    for key in ('stdout', 'stderr')))), None)


def stop_tools(ctx, side, ply, session, evidence):
    rec = {'type': 'flag', 'source': 'tool_call', 'ply': ply, 'side': side,
           'session': session, 'evidence': evidence, **ctx.get('tags', {})}
    ctx['tool_call'] = rec
    log(ctx, rec)
    raise ToolAttempt(TOOL_MESSAGE)


def refusal_record(recs):
    """旧记录的 flag / flagged 也锁住续跑；历史已结束的盘仍可读取、导出。"""
    return next((r for r in recs if r['type'] == 'refusal'
                 or (r['type'] == 'flag' and r.get('source') in ('result', 'transcript'))
                 or (r['type'] == 'attempt' and r.get('flagged'))), None)


def pending_ply(recs, ply):
    """暂停时还没落子的那个半回合里模型已经用掉的尝试：续跑接着算重试次数、错着反馈和用量，不重新给满机会。"""
    p = {'ply': ply, 'bad': [], 'k': 0, 'flags': 0, 'blocks': 0, 'redo': False, 'stat': records.new_stat()}
    costs = records.attempt_costs(recs)[0]            # 旧记录里 session 档的 cost 是会话累计值，按会话做差
    for r in recs:
        if r['type'] != 'attempt' or r['ply'] != ply or player_kind(str(r.get('player', ''))) not in MODEL_KINDS:
            continue
        records.add_usage(p['stat'], dict(r.get('usage') or {}, cost=costs[id(r)]), r.get('elapsed') or 0)
        if r.get('recite'):
            p['stat'].setdefault('recite', []).append(r['recite'])
        if r.get('flagged') or r.get('empty'):
            p['flags'] += 1
            p['stat']['flags' if r.get('flagged') else 'empty'] += 1
            p['blocks'] += bool(r.get('flagged'))      # 保留旧记录的计数；拒答记录已在续跑入口锁住
            p['redo'] = True
            continue
        p['redo'] = False
        if not r.get('legal'):
            p['k'] += 1
            p['stat']['illegal'] += 1
            p['stat']['noparse'] += r.get('move_text') is None
            p['bad'].append((r.get('move_text') or '（没写）', r.get('reason'), r.get('feedback')))
    return p


def log(ctx, rec):
    records.write(ctx['log'], rec)


# ---------------------------------------------------------------- 三种棋手
def model_turn(ctx, side, moves, ban):
    """问模型走一步，返回 (着法或 None, 本步统计)。None 表示重试用完仍非法。"""
    G, cfg, st = ctx['G'], ctx['cfg'], ctx['st']
    if ctx.get('tool_call'):
        raise ToolAttempt(TOOL_MESSAGE)
    if ctx.get('uncertain'):
        raise Paused(UNCERTAIN_MESSAGE)
    sc = cfg['sides'][side]
    kind, model = cfg['players'][side].split(':', 1)
    system = cfg['system'][side]
    mem = sc['memory']
    via_chat = cfg.get('backend') == 'llm-chat'
    drop = via_chat and sc.get('drop_thinking') == 'on'     # 旧记录没有这一项，按关
    real = memory.real(sc)
    codex = kind in codex_cli.KINDS and not via_chat
    if codex and mem == 'session':
        raise SystemExit('%s 棋手只支持无状态（stateless / notes），不支持 session' % kind)
    ply = len(st['moves']) + 1
    if real:
        # 着法记录只在新会话的第一条给（session 档之后前文里都有）；stateless / notes 每步都是新会话
        body = G.render(st, sc, not (mem == 'session' and ctx['sessions'].get(side)))
    elif mem == 'session' and sc['session_view'] == 'move' and ctx['sessions'].get(side) and st['moves']:
        body = '对方刚走：%s。%s' % (G.last_move_text(st), '你现在正被将军！' if G.in_check(st) else '')
    else:
        body = G.render(st, sc)
    if mem == 'notes':
        nt = memory.notes_text(ctx['notes'][side], sc['notes_keep'])
        if nt:
            body += '\n\n' + nt
    base = body + '\n\n' + memory.ask(sc)
    bad, flags, blocks, k, redo = [], 0, 0, 0, False
    stat = records.new_stat()
    p = ctx.pop('pending', None)
    if p and p['ply'] == ply:                  # 续跑：接上暂停前这一步已经用掉的尝试
        bad, flags, blocks, k, redo, stat = p['bad'], p['flags'], p.get('blocks', 0), p['k'], p['redo'], p['stat']
    while k < cfg['retries'] + 1:
        if redo and mem == 'session' and ctx['sessions'].get(side):   # 上一条回复为空，前文已在会话里
            prompt = '请重新回答这一步。' + memory.ask(sc)
        elif bad and real:
            prompt = memory.retry_prompt_real(sc, base, [(t, memory.FEEDBACK[fb]) for t, _, fb in bad],
                                              cfg['retries'] + 1 - k)
        elif bad:
            prompt = memory.retry_prompt(sc, base, [(t, why) for t, why, _ in bad], cfg['retries'] + 1 - k)
        else:
            prompt = base
        if via_chat:
            new = False
            sid = ctx['sessions'].get(side) if mem == 'session' else None
            cmd = chat.command(cfg['models'][side], sc['effort'], None if sid else system, sid,
                               cfg.get('timeout') or claude_cli.TIMEOUT, drop_thinking=drop and not sid)
        elif codex:
            new, sid = False, None
            files = codex_cli.prepare(kind, model, sc['effort'], system, ctx['cwd'])
            cmd = codex_cli.command(kind, model, sc['effort'], *files, ctx['cwd'])
        elif mem == 'session':
            sid = ctx['sessions'].get(side)
            new = sid is None
            sid = sid or str(uuid.uuid4())
            cmd = claude_cli.command(model, sc['effort'], system, sid, new_session=new)
            if new:
                log(ctx, {'type': 'session_start', 'ply': ply, 'side': side, 'session': sid})
        else:
            new, sid, cmd = False, None, claude_cli.command(model, sc['effort'], system)
        rebuild = None
        if new:
            def rebuild(sid=sid):
                made = claude_cli.transcript_path(ctx['cwd'], sid).exists()
                return claude_cli.command(model, sc['effort'], system, sid, new_session=not made)
        def on_fail(info, k=k):
            # 超时 / 调不通落进这盘（这题）自己的记录；ctx['tags'] 是局面题的题号 / 档 / 遍
            log(ctx, dict({'type': 'call_fail', 'ply': ply, 'side': side, 'attempt': k + 1}, **extra, **ctx.get('tags', {}),
                          **info))
        def on_wait(info, k=k):
            # 撞额度在程序里等解除：开始、结束各一条，同样落进这盘（这题）自己的记录
            log(ctx, dict({'type': 'limit_wait', 'ply': ply, 'side': side, 'attempt': k + 1}, **ctx.get('tags', {}),
                          **info))
        def refusal_check(d):
            if kind != 'claude':
                return []
            checked_sid = (((d or {}).get('meta') or {}).get('session') or sid) if via_chat else sid
            hits = (claude_cli.transcript_flags_at(chat.claude_transcript(checked_sid)) if via_chat
                    else claude_cli.transcript_flags(ctx['cwd'], checked_sid)) if checked_sid else []
            return (hits or [])[ctx['seen_flags'].get(checked_sid, 0):]
        extra = {}
        call_options = {}
        if via_chat and kind in chat.AGY_KINDS:
            extra['call_id'] = str(uuid.uuid4())
            started = {'type': 'call_started', 'ply': ply, 'side': side, 'session': sid,
                       'call_id': extra['call_id'], 'provider': kind, 'outcome': 'uncertain'}
            def on_start():
                # 停止检查通过后先落盘再发送；写盘失败不得提交请求。
                log(ctx, started)
                ctx['uncertain'] = started
            call_options['on_start'] = on_start
        if via_chat:
            resumed = bool(sid)
            d, dt = chat.call(cmd, prompt, on_fail=on_fail, on_wait=on_wait, refusal_check=refusal_check,
                              **call_options)
            if claude_cli.tool_used(d):
                stop_tools(ctx, side, ply, sid, d.get('tool_evidence') or d)
            u = chat.usage(d, kind)
            if drop and d.get('meta') is not None:
                extra['thinking_dropped'] = d['meta'].get('thinking_dropped')
                if resumed and not extra['thinking_dropped']:
                    drop_warn(ctx, side, ply, k, sid, extra['thinking_dropped'])
                ctx.setdefault('last_think', {})[side] = u['think'] if d['meta'].get('reasoning_tokens') is not None else None
            if mem == 'session' and d.get('meta'):
                sid = ctx['sessions'][side] = d['meta']['session']
            if sid:
                # llm-chat 给的是这一轮自己的花费；照旧记一个会话累计值（records.attempt_costs 按会话做差还原）
                u['cost_total'] = ctx['cost_total'][sid] = (ctx['cost_total'].get(sid) or 0) + u['cost']
        else:
            try:
                d, dt = claude_cli.call(cmd, prompt, ctx['cwd'], rebuild=rebuild,
                                        timeout=cfg.get('timeout') or claude_cli.TIMEOUT, on_fail=on_fail, on_wait=on_wait,
                                        parse=codex_cli.parse if codex else None, refusal_check=refusal_check)
            except codex_cli.ToolUsed as e:
                stop_tools(ctx, side, ply, sid, {'error': str(e)})
            if claude_cli.tool_used(d):
                stop_tools(ctx, side, ply, sid, d.get('tool_evidence') or d)
            if mem == 'session':
                sid = ctx['sessions'][side] = d.get('session_id') or sid
            u = codex_cli.usage(d, model) if codex else claude_cli.usage(d)
        if via_chat and kind == 'codex' and d.get('meta'):
            used = chat.codex_tool_calls(d['meta'].get('session'))
            if used:
                stop_tools(ctx, side, ply, sid, {'count': used, 'text': d.get('result') or ''})
        reply = d.get('result') or ''
        if mem == 'session' and not via_chat:
            # --resume 返回的花费是整段会话的累计值：本次花费 = 累计值 − 同一会话上一次调用的累计值（被拦、空回复也算一次），
            # 原始累计值另存 cost_total 以便核对
            total = u['cost']
            u['cost'] = records.cost_delta(total, ctx['cost_total'].get(sid))
            u['cost_total'] = ctx['cost_total'][sid] = total
        records.add_usage(stat, u, dt)
        # 收到明确拒答就停止；transcript 可能表明 CLI 在本次调用内部已自动重试过。
        blocked = claude_cli.flagged(d)
        transcript = None
        hits = []
        if kind == 'claude':
            if via_chat:
                hits = claude_cli.transcript_flags_at(chat.claude_transcript(sid))
            elif sid:
                hits = claude_cli.transcript_flags(ctx['cwd'], sid)
            transcript = 'missing' if hits is None else len(hits)
        new_hits = (hits or [])[ctx['seen_flags'].get(sid, 0):]
        if new_hits:
            ctx['seen_flags'][sid] = len(hits)
            blocked = True
        empty = not blocked and not reply.strip()
        if blocked or empty:
            flags += 1
            stat['flags' if blocked else 'empty'] += 1
            log(ctx, {'type': 'attempt', 'ply': ply, 'side': side, 'try': k + 1, 'player': cfg['players'][side],
                      'session': sid, 'prompt': prompt, 'reply': reply, 'flagged': blocked, 'empty': empty,
                      'usage': u, 'elapsed': round(dt, 1), 'claude': d, **extra})
            if blocked:
                evidence = {'response': d, 'transcript': new_hits}
                rec = {'type': 'refusal', 'ply': ply, 'side': side, 'provider': kind,
                       'player': cfg['players'][side], 'session': sid, 'evidence': evidence}
                ctx['refusal'] = rec
                log(ctx, {'type': 'flag', 'ply': ply, 'side': side, 'source': 'transcript' if new_hits else 'result',
                          'session': sid, 'count': len(hits or []), 'text': new_hits[-1] if new_hits else reply})
                log(ctx, rec)
                raise Refused('第 %d 个半回合%s（%s）明确拒答或被安全防护拦截；已保存原始证据，禁止自动续跑' % (
                    ply, G.SIDES[side], kind))
            print('  ！%s 回复正文为空（本步第 %d 次，不扣重试次数）' % (G.SIDES[side], flags), flush=True)
            if flags > MAX_FLAGS:
                raise Paused('第 %d 个半回合%s的回复 %d 次为空' % (ply, G.SIDES[side], flags))
            redo = True
            continue
        redo = False
        text = memory.extract_move(reply, loose=real)
        mv, why = G.parse(st, text)
        if mv and not why and mv in ban:
            why = ban[mv]
        fb = G.feedback(text, why) if real and why else None      # 新协议下告诉棋手的原因类别（memory.FEEDBACK）
        note = memory.extract_note(reply) if mem == 'notes' else None
        rs = G.recite_score(st, reply) if sc['recite'] == 'on' else None
        if rs:
            stat.setdefault('recite', []).append(rs)
        log(ctx, {'type': 'attempt', 'ply': ply, 'side': side, 'try': k + 1, 'player': cfg['players'][side],
                  'session': sid, 'prompt': prompt, 'reply': reply, 'move_text': text, 'move': mv,
                  'legal': why is None, 'reason': why, 'feedback': fb, 'note': note, 'recite': rs, 'transcript_flags': transcript,
                  'usage': u, 'elapsed': round(dt, 1), 'claude': d, **extra})
        if extra.get('call_id'):
            ctx.pop('uncertain', None)
        print('  %s 第 %d 次：%s → %s%s（%.0fs，输出 %d tok，思考 %d，$%.3f）' % (
            G.SIDES[side], k + 1, text, mv, '' if why is None else ' 非法：' + why, dt, u['out'], u['think'],
            u['cost']), flush=True)
        if why is None:
            return mv, stat, note
        stat['illegal'] += 1
        stat['noparse'] += text is None
        bad.append((text or '（没写）', why, fb))
        k += 1
    return None, stat, None


def drop_warn(ctx, side, ply, k, sid, n):
    """开了去掉思考的一方，续接轮 llm-chat 报的 thinking_dropped 应该 ≥1（删掉了上一轮的思考）。拿到 0 或没给就告警：
    写一条 drop_warn、终端提示，不中断对局。可能的原因：上一轮本来没思考（prev_think 为 0 时多半是这个）、
    claude 升级后思考换了存法、llm-chat 没按开关走（blockR 最终回报）。prev_think 是本次运行里这方上一次调用的思考 token，
    续跑后的第一步不知道，记 None。"""
    prev = (ctx.get('last_think') or {}).get(side)
    log(ctx, {'type': 'drop_warn', 'ply': ply, 'side': side, 'attempt': k + 1, 'session': sid,
              'thinking_dropped': n, 'prev_think': prev})
    print('  ！%s 开了去掉思考，但这次续接 thinking_dropped=%s（上一轮思考 %s token%s），记下接着下' % (
        ctx['G'].SIDES[side], n, '?' if prev is None else prev, '，多半是上一轮没思考' if prev == 0 else ''), flush=True)


def engine_turn(ctx, side, moves, ban):
    G, st = ctx['G'], ctx['st']
    eng = ctx['engines'][side]
    search = [G.to_engine(m) for m in moves if m not in ban] if ban else None
    t0 = time.time()
    raw = eng.best(st['fens'][0], [G.to_engine(m) for m in st['moves']], search)
    dt = time.time() - t0
    mv = G.from_engine(raw)
    if mv not in moves or mv in ban:
        raise EngineError('引擎 %s 给出不能走的着法 %s（%s）' % (eng.spec['name'], raw, mv))
    stat = records.new_stat()
    stat['attempts'], stat['elapsed'] = 1, dt
    log(ctx, {'type': 'attempt', 'ply': len(st['moves']) + 1, 'side': side, 'try': 1,
              'player': ctx['cfg']['players'][side], 'move': mv, 'raw': raw, 'legal': True,
              'searchmoves': len(search) if search else None, 'elapsed': round(dt, 3)})
    return mv, stat, None


def random_turn(ctx, side, moves, ban):
    """随机走子：每个半回合用 (种子, 半回合号) 起一个随机数，续跑也能复现。"""
    ply = len(ctx['st']['moves']) + 1
    rng = random.Random('%s:%d' % (ctx['cfg']['seed'], ply))
    mv = rng.choice([m for m in moves if m not in ban])
    stat = records.new_stat()
    stat['attempts'] = 1
    log(ctx, {'type': 'attempt', 'ply': ply, 'side': side, 'try': 1, 'player': 'random', 'move': mv, 'legal': True})
    return mv, stat, None


def opening_turn(ctx, side, moves, ban):
    """随机开局：照 config 里记下的着法走（cli 建盘时生成，续跑照样重放、不重新抽）。不算哪方棋手的着法。"""
    ply = len(ctx['st']['moves']) + 1
    mv = opening.moves_of(ctx['cfg'])[ply - 1]
    if mv not in moves or mv in ban:
        raise RuntimeError('config 里的开局第 %d 个半回合 %s 不能走' % (ply, mv))
    stat = records.new_stat()
    stat['opening'] = True
    return mv, stat, None


TURNS = {**dict.fromkeys(MODEL_KINDS, model_turn), 'engine': engine_turn, 'random': random_turn}


# ---------------------------------------------------------------- 一盘
def play(ctx, stop_after=None, stop_file=None):
    """下到终局或暂停。返回终局 dict；暂停返回 None（已写 pause）。stop_after：本次最多再走几个半回合（冒烟测续跑用）；
    stop_file：每步走之前看一眼这个文件，在了就暂停（批量驱动用它让在跑的盘停在两步之间）。"""
    G, cfg, st = ctx['G'], ctx['cfg'], ctx['st']
    if ctx.get('refusal'):
        print('这盘已有拒答拦截记录，已终止；禁止自动续跑，请向用户回报。', flush=True)
        return None
    if ctx.get('tool_call'):
        print(TOOL_MESSAGE, flush=True)
        return None
    if ctx.get('uncertain'):
        print(UNCERTAIN_MESSAGE, flush=True)
        return None
    n_open = len(opening.moves_of(cfg))
    os.makedirs(ctx['cwd'], exist_ok=True)
    end, moved = ctx['end'], 0
    try:
        for side in 'wb':
            spec = cfg['players'][side]
            if player_kind(spec) == 'engine':
                ctx['engines'][side] = Engine(G.engine_spec(spec.split(':', 1)[1])).start()
        while end is None:
            end = G.ending(st)
            if end is None and len(st['moves']) >= cfg['max_plies']:
                if cfg.get('adjudicate'):
                    # 有引擎一方的对局到上限按引擎评分判（用户 2026-10-04 定）；旧记录没有这一项，照旧判和
                    from . import analyze       # analyze 导入 cli、cli 导入本模块，放在这里免得循环导入
                    end = analyze.adjudicate(G, cfg['game'], st, cfg['adjudicate']['margin'], cfg['max_plies'])
                else:
                    end = {'winner': None, 'reason': '满 %d 个半回合（研究设的上限），判和' % cfg['max_plies']}
            if end is not None:
                break
            if stop_after is not None and moved >= stop_after:
                raise Paused('按 --stop-after %d 停下' % stop_after)
            if stop_file and os.path.exists(stop_file):
                raise Paused('批量驱动要求停下（%s）' % stop_file)
            side = G.turn(st)
            moves = G.legal(st)
            ban = G.banned(st, moves)
            in_open = len(st['moves']) < n_open
            turn = opening_turn if in_open else TURNS[player_kind(cfg['players'][side])]
            mv, stat, note = turn(ctx, side, moves, ban)
            stat['side'] = side
            if mv is None:
                end = {'winner': other(side), 'reason': '%s连续 %d 次给出非法着法，判负' % (G.SIDES[side], cfg['retries'] + 1)}
                ctx['stats'].append(stat)
                log(ctx, {'type': 'forfeit', 'ply': len(st['moves']) + 1, 'side': side, 'stat': stat, 'end': end})
                break
            G.push(st, mv)
            ctx['stats'].append(stat)
            if cfg['sides'][side]['memory'] == 'notes':
                ctx['notes'][side].append(note)
            moved += 1
            rec = {'type': 'move', 'ply': len(st['moves']), 'side': side, 'move': mv, 'text': st['record'][-1],
                   'check': G.in_check(st), 'note': note, 'stat': stat}
            if in_open:
                rec['opening'] = True              # 这一步是随机开局程序替双方走的，不算棋手的着法
            log(ctx, rec)
            print('第 %d 步 %s %s（%s）%s' % (len(st['moves']), G.SIDES[side], st['record'][-1], mv,
                                           '　【随机开局】' if in_open else ''), flush=True)
    except Refused as e:
        print('对弈已终止：%s。请向用户回报。' % e, flush=True)
        return None
    except Paused as e:
        log(ctx, {'type': 'pause', 'ply': len(st['moves']), 'why': str(e)})
        hint = (TOOL_MESSAGE if ctx.get('tool_call') else UNCERTAIN_MESSAGE if ctx.get('uncertain')
                else '接着下：python3 -m llmchess resume %s' % ctx['dir'])
        print('停在第 %d 个半回合之后：%s\n%s' % (len(st['moves']), e, hint))
        return None
    finally:
        for eng in ctx['engines'].values():
            eng.close()
        ctx['engines'] = {}
    ctx['end'] = end
    finish(ctx)
    return end


def finish(ctx):
    G, cfg, st, end = ctx['G'], ctx['cfg'], ctx['st'], ctx['end']
    summ = records.summary(ctx['stats'], cfg['players'])
    log(ctx, {'type': 'end', 'end': end, 'plies': len(st['moves']), 'moves': st['moves'], 'record': st['record'],
              'summary': summ})
    print(write_exports(ctx).get('record.txt', ''))


def write_exports(ctx):
    """按记录写棋谱文件（record.txt、game.pgn），原子替换。终局时 finish 调；已结束的盘也可以
    用 `python3 -m llmchess export <目录>` 重新导出（load 重放后调这里，不写任何记录）。返回 {文件名: 内容}。"""
    files = render_exports(ctx)
    for name, text in files.items():
        path = os.path.join(ctx['dir'], name)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(text)
        os.replace(tmp, path)
    return files


def render_exports(ctx):
    """棋谱文件该写成什么样（{文件名: 内容}），不落盘。阅读器的回归测试拿它判断盘上的导出是不是现在的写法。"""
    G, cfg, st, end = ctx['G'], ctx['cfg'], ctx['st'], ctx['end']
    summ = records.summary(ctx['stats'], cfg['players'])
    lines = records.summary_lines(summ, G.SIDES)
    op = cfg.get('opening') or {}
    if op.get('moves'):
        lines.insert(0, '前 %d 个半回合是随机开局，由程序替双方走（种子 %s，不算棋手的着法）：%s' % (
            len(op['moves']), op.get('seed'), ' '.join(op.get('record') or op['moves'])))
    meta = records.move_meta(records.read(ctx['log']))
    return G.exports(st, cfg, end, lines, meta)
