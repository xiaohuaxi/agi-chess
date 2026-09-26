"""对局循环（两种棋共用一份）：轮到谁 → 棋种拼提示 → 调棋手（模型 / 引擎 / 随机，直接分支）→ 棋种解析判合法（含禁着）
→ 重试 / 判负 → 落子 → 棋种判终局 → 记录；暂停与续跑。

棋种模块 G 提供的函数见 design.md 第二节：start / turn / legal / banned / parse / push / ending / in_check /
render / last_move_text / system_prompt / recite_score / exports / engine_spec / to_engine / from_engine，常量 SIDES。
"""
import os, random, time, uuid

from . import claude_cli, memory, records
from .claude_cli import Paused
from .engine import Engine, EngineError

FORFEIT_NOTE = ('重试用完仍非法判负：替它随便走一步会把随机或引擎的着法混进它的棋里，判负最干净；'
                '实际很少触发，触发了也在记录里单列')
MAX_FLAGS = 2          # 一个半回合里回复被安全分类器拦掉或正文为空的次数上限，超过就暂停，交给人看


def other(side):
    return 'b' if side == 'w' else 'w'


def player_kind(spec):
    return spec.split(':', 1)[0]


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
    ctx['pending'] = pending_ply(recs, len(st['moves']) + 1)
    return ctx


def pending_ply(recs, ply):
    """暂停时还没落子的那个半回合里模型已经用掉的尝试：续跑接着算重试次数、错着反馈和用量，不重新给满机会。"""
    p = {'ply': ply, 'bad': [], 'k': 0, 'flags': 0, 'redo': False, 'stat': records.new_stat()}
    costs = records.attempt_costs(recs)[0]            # 旧记录里 session 档的 cost 是会话累计值，按会话做差
    for r in recs:
        if r['type'] != 'attempt' or r['ply'] != ply or not str(r.get('player', '')).startswith('claude'):
            continue
        records.add_usage(p['stat'], dict(r.get('usage') or {}, cost=costs[id(r)]), r.get('elapsed') or 0)
        if r.get('recite'):
            p['stat'].setdefault('recite', []).append(r['recite'])
        if r.get('flagged') or r.get('empty'):
            p['flags'] += 1
            p['stat']['flags' if r.get('flagged') else 'empty'] += 1
            p['redo'] = True
            continue
        p['redo'] = False
        if not r.get('legal'):
            p['k'] += 1
            p['stat']['illegal'] += 1
            p['stat']['noparse'] += r.get('move_text') is None
            p['bad'].append((r.get('move_text') or '（没写）', r.get('reason')))
    return p


def log(ctx, rec):
    records.write(ctx['log'], rec)


# ---------------------------------------------------------------- 三种棋手
def model_turn(ctx, side, moves, ban):
    """问模型走一步，返回 (着法或 None, 本步统计)。None 表示重试用完仍非法。"""
    G, cfg, st = ctx['G'], ctx['cfg'], ctx['st']
    sc = cfg['sides'][side]
    model = cfg['players'][side].split(':', 1)[1]
    system = cfg['system'][side]
    mem = sc['memory']
    ply = len(st['moves']) + 1
    if mem == 'session' and sc['session_view'] == 'move' and ctx['sessions'].get(side) and st['moves']:
        body = '对方刚走：%s。%s' % (G.last_move_text(st), '你现在正被将军！' if G.in_check(st) else '')
    else:
        body = G.render(st, sc)
    if mem == 'notes':
        nt = memory.notes_text(ctx['notes'][side], sc['notes_keep'])
        if nt:
            body += '\n\n' + nt
    base = body + '\n\n' + memory.ask(sc)
    bad, flags, k, redo = [], 0, 0, False
    stat = records.new_stat()
    p = ctx.pop('pending', None)
    if p and p['ply'] == ply:                  # 续跑：接上暂停前这一步已经用掉的尝试
        bad, flags, k, redo, stat = p['bad'], p['flags'], p['k'], p['redo'], p['stat']
    while k < cfg['retries'] + 1:
        if redo and mem == 'session':           # 上一条回复被拦或为空，前文已在会话里
            prompt = '请重新回答这一步。' + memory.ask(sc)
        elif bad:
            prompt = memory.retry_prompt(sc, base, bad, cfg['retries'] + 1 - k)
        else:
            prompt = base
        if mem == 'session':
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
        d, dt = claude_cli.call(cmd, prompt, ctx['cwd'], rebuild=rebuild)
        if mem == 'session':
            sid = ctx['sessions'][side] = d.get('session_id') or sid
        reply = d.get('result') or ''
        u = claude_cli.usage(d)
        if mem == 'session':
            # --resume 返回的花费是整段会话的累计值：本次花费 = 累计值 − 同一会话上一次调用的累计值（被拦、空回复也算一次），
            # 原始累计值另存 cost_total 以便核对
            total = u['cost']
            u['cost'] = records.cost_delta(total, ctx['cost_total'].get(sid))
            u['cost_total'] = ctx['cost_total'][sid] = total
        records.add_usage(stat, u, dt)
        # 安全分类器：回复正文被拦（这次不算非法，另算次数）；session 下再看会话记录里 claude 自动插的那条消息
        blocked = claude_cli.flagged(d)
        transcript = None
        if mem == 'session':
            hits = claude_cli.transcript_flags(ctx['cwd'], sid)
            transcript = 'missing' if hits is None else len(hits)
            if hits and len(hits) > ctx['seen_flags'].get(sid, 0):
                ctx['seen_flags'][sid] = len(hits)
                stat['flags'] += 1
                log(ctx, {'type': 'flag', 'ply': ply, 'side': side, 'source': 'transcript', 'session': sid,
                          'count': len(hits), 'text': hits[-1]})
                print('  ！%s 会话里出现安全分类器拦截（这盘要标出来）' % G.SIDES[side], flush=True)
        # 回复被拦、或者正文是空的（冒烟里见过：end_turn、有思考、正文空）：都不是它下的棋，不扣重试次数，另记
        empty = not blocked and not reply.strip()
        if blocked or empty:
            flags += 1
            stat['flags' if blocked else 'empty'] += 1
            if blocked:
                log(ctx, {'type': 'flag', 'ply': ply, 'side': side, 'source': 'result', 'session': sid, 'text': reply[:500]})
            log(ctx, {'type': 'attempt', 'ply': ply, 'side': side, 'try': k + 1, 'player': cfg['players'][side],
                      'session': sid, 'prompt': prompt, 'reply': reply, 'flagged': blocked, 'empty': empty,
                      'usage': u, 'elapsed': round(dt, 1), 'claude': d})
            print('  ！%s 回复%s（本步第 %d 次，不扣重试次数）' % (
                G.SIDES[side], '被安全分类器拦下' if blocked else '正文为空', flags), flush=True)
            if flags > MAX_FLAGS:
                raise Paused('第 %d 个半回合%s的回复 %d 次被拦或为空' % (ply, G.SIDES[side], flags))
            redo = True
            continue
        redo = False
        text = memory.extract_move(reply)
        mv, why = G.parse(st, text)
        if mv and not why and mv in ban:
            why = ban[mv]
        note = memory.extract_note(reply) if mem == 'notes' else None
        rs = G.recite_score(st, reply) if sc['recite'] == 'on' else None
        if rs:
            stat.setdefault('recite', []).append(rs)
        log(ctx, {'type': 'attempt', 'ply': ply, 'side': side, 'try': k + 1, 'player': cfg['players'][side],
                  'session': sid, 'prompt': prompt, 'reply': reply, 'move_text': text, 'move': mv,
                  'legal': why is None, 'reason': why, 'note': note, 'recite': rs, 'transcript_flags': transcript,
                  'usage': u, 'elapsed': round(dt, 1), 'claude': d})
        print('  %s 第 %d 次：%s → %s%s（%.0fs，输出 %d tok，思考 %d，$%.3f）' % (
            G.SIDES[side], k + 1, text, mv, '' if why is None else ' 非法：' + why, dt, u['out'], u['think'],
            u['cost']), flush=True)
        if why is None:
            return mv, stat, note
        stat['illegal'] += 1
        stat['noparse'] += text is None
        bad.append((text or '（没写）', why))
        k += 1
    return None, stat, None


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


TURNS = {'claude': model_turn, 'engine': engine_turn, 'random': random_turn}


# ---------------------------------------------------------------- 一盘
def play(ctx, stop_after=None):
    """下到终局或暂停。返回终局 dict；暂停返回 None（已写 pause）。stop_after：本次最多再走几个半回合（冒烟测续跑用）。"""
    G, cfg, st = ctx['G'], ctx['cfg'], ctx['st']
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
                end = {'winner': None, 'reason': '满 %d 个半回合（研究设的上限），判和' % cfg['max_plies']}
            if end is not None:
                break
            if stop_after is not None and moved >= stop_after:
                raise Paused('按 --stop-after %d 停下' % stop_after)
            side = G.turn(st)
            moves = G.legal(st)
            ban = G.banned(st, moves)
            mv, stat, note = TURNS[player_kind(cfg['players'][side])](ctx, side, moves, ban)
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
            log(ctx, {'type': 'move', 'ply': len(st['moves']), 'side': side, 'move': mv, 'text': st['record'][-1],
                      'check': G.in_check(st), 'note': note, 'stat': stat})
            print('第 %d 步 %s %s（%s）' % (len(st['moves']), G.SIDES[side], st['record'][-1], mv), flush=True)
    except Paused as e:
        log(ctx, {'type': 'pause', 'ply': len(st['moves']), 'why': str(e)})
        print('停在第 %d 个半回合之后：%s\n接着下：python3 -m llmchess resume %s' % (len(st['moves']), e, ctx['dir']))
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
    files = G.exports(st, cfg, end, records.summary_lines(summ, G.SIDES))
    for name, text in files.items():
        path = os.path.join(ctx['dir'], name)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(text)
        os.replace(tmp, path)
    print(files.get('record.txt', ''))
