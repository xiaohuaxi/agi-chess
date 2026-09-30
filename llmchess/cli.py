"""命令行：模型对模型、模型对引擎 / 随机走子，下中国象棋或国际象棋。

    python3 -m llmchess play --game xiangqi --tag x1 --black random --max-plies 6
    python3 -m llmchess play --game chess --tag c1 --black engine:maia-1100 --memory notes
    python3 -m llmchess play --game chess --tag c2 --b effort=high --b memory=session   # 两方分设
    python3 -m llmchess play --game xiangqi --tag x2 --dry-run                          # 只打印提示，不调模型
    python3 -m llmchess play --game chess --tag c3 --black engine:maia-1500 --opening random:8 --opening-seed 1
    python3 -m llmchess resume runs/x1                                                  # 暂停后接着下
    python3 -m llmchess export runs/x1                                                  # 已结束的盘重新导出棋谱

协议 --protocol（默认 real）：real 是「模型就是真实棋手」（design.md 第九节）——每方一段连续会话（memory 默认 session），
  只给局面、轮到谁、对方上一步，不报将军、不给合法着法；默认请棋手在着法之前写出理由（reason=off 关掉）；
  非法着法只告诉它不合法、让它重选（每步最多 retries+1 次，用完判负；real 默认 3 次）；模型调用走 llm-chat（chat.py）。legacy 是改协议之前的提示和调用（claude -p 直调，memory 默认 stateless），
  用来续跑、复现旧实验；旧记录的 config 里没有 protocol，resume 自动按旧的走。
棋手：claude:<模型>（默认 claude:opus）/ codex:<GPT 模型，如 sol 或 gpt-6-sol> / deepseek:<模型，默认 deepseek-v4-pro>
  （后两种只在 real 下）/ engine:<引擎>[:参数] / random。
  国际象棋引擎 maia-1100 … maia-1900（lc0，go nodes 1）、stockfish[:elo=N|nodes=N|depth=N|movetime=毫秒]；
  中国象棋引擎 fsf[:nodes=N|depth=N|movetime=毫秒]（Fairy-Stockfish，默认 nodes=1000）。
模型相关变量（公共值用 --变量，一方单设用 --w / --b 变量=值，w 是先走的红方 / 白方）：
  effort medium|high|xhigh|max、memory stateless|notes|session、show、view（逗号分隔）、history（-1 全部 / 0 / N）、
  legal none|list、selfcheck on|off、recite on|off（只有中国象棋）、notes_keep N、session_view full|move、
  reason plain|brief|detailed|off（只在 real 下：着法之前用自己的话写出这步的理由，brief / detailed 在「写出」前加「简短」/「详细」，
  导出棋谱时进该步评注；off 只需给出着法）、
  drop_thinking on|off（只在 real、memory=session 下，只有 Claude 棋手能开，默认 off：续接时不带此前几轮的思考，
  llm-chat --drop-thinking）。reason 不给时一律 plain（不修饰，2026-09-30 定；之前的默认 brief 可选，和 plain 差别很小、
  数据合并）；detailed 已弃用（2026-09-30：opus 去掉思考 + 详细理由频繁被安全防护拦下），只为复现保留。
  例：--w drop_thinking=on 让白方去掉思考，双方都照默认写理由。
局面怎么呈现：show all|board|pieces|fen|boardpieces（boardpieces 只有中国象棋），和局面题的 --set show 同一套（棋种模块的
  SHOWS）。不给时用棋种默认给法：中国象棋 pieces（只给子力清单）、国际象棋 all（FEN + 字母棋盘），第 4P2 批定的；
  --show all 回到改默认之前的提示（中国象棋棋盘 + 清单 + FEN）。view 是自定义组合，和 show 二选一：同一层（公共 / 一方单设）
  两个都给报错，一方单设的覆盖公共的那个。每方实际用的 show 记在 config 的 sides 里（自定义 view 记 null）。
随机开局 --opening random:N：前 N 个半回合由程序替双方走（引擎浅搜 MultiPV 3、分差 ≤50 厘兵的着法按 --opening-seed 抽），
  开局写进 config、续跑照记录重放；模型只在着法历史里看到这几步。--dry-run 打印的是开局走完后模型方第一步的提示。
记录在 runs/<tag>/（不入库）：game.jsonl、record.txt，国际象棋另有 game.pgn。棋谱里每步带评注
  {[%emt 用时] [%think 思考 token] [%out 输出 token] …}（design.md 第四节）。
暂停（--on-limit pause 时撞额度、连续调不通、--stop-after、停止信号）退出码 3。
--timeout：单次 claude -p 调用的超时秒数（默认 3600），记进 config，resume 沿用（resume --timeout 只改这次续跑）；
  超时 / 调不通各记一条 call_fail。
--on-limit wait|pause：撞额度时在程序里等到解除接着下（默认，起止各记一条 limit_wait），或按旧行为暂停退出（退出码 3）。
  等待中 Ctrl-C / SIGTERM 马上写 pause 退出（退出码 3），resume 接着下；再按一次强退。
"""
import argparse, importlib, json, os, pathlib, random, subprocess, sys, tempfile, uuid

from . import chat, claude_cli, memory, opening, records, runner

ROOT = pathlib.Path(__file__).resolve().parent.parent
RUNS = ROOT / 'runs'
GAMES = {'xiangqi': 'llmchess.xiangqi', 'chess': 'llmchess.chess_'}
EFFORTS = ('low', 'medium', 'high', 'xhigh', 'max')
SIDE_KEYS = {'effort': str, 'memory': str, 'show': str, 'view': str, 'history': int, 'legal': str, 'selfcheck': str,
             'recite': str, 'notes_keep': int, 'session_view': str, 'reason': str, 'drop_thinking': str}


def game_module(name):
    return importlib.import_module(GAMES[name])


def side_cfg(a, G, overrides, max_plies):
    sc = {k: getattr(a, k) for k in SIDE_KEYS}
    if sc['memory'] is None:
        sc['memory'] = 'session' if a.protocol == 'real' else 'stateless'
    if sc['show'] and sc['view']:
        raise SystemExit('--show 和 --view 二选一')
    own = set()
    for item in overrides or []:
        k, sep, v = item.partition('=')
        if not sep or k not in SIDE_KEYS:
            raise SystemExit('一方单设写成 变量=值，变量是 %s 之一：%r' % ('/'.join(SIDE_KEYS), item))
        sc[k] = SIDE_KEYS[k](v)
        own.add(k)
        if k in ('show', 'view'):                  # 一方单设的呈现方式覆盖公共的那个
            sc['view' if k == 'show' else 'show'] = None
    if {'show', 'view'} <= own:
        raise SystemExit('一方单设里 show 和 view 二选一')
    if not sc['view']:
        sc['show'] = sc['show'] or G.DEFAULT_SHOW
        if sc['show'] not in G.SHOWS:
            raise SystemExit('show 只能是 %s，收到 %r' % ('/'.join(G.SHOWS), sc['show']))
        sc['view'] = G.SHOWS[sc['show']]
    sc['view'] = sc['view'].split(',') if isinstance(sc['view'], str) else sc['view']
    for v in sc['view']:
        if v not in G.VIEWS:
            raise SystemExit('不认识的 view：%s（可选 %s）' % (v, ','.join(G.VIEWS)))
    checks = {'effort': EFFORTS, 'memory': memory.MODES, 'legal': ('none', 'list'), 'selfcheck': ('on', 'off'),
              'recite': ('on', 'off'), 'session_view': ('full', 'move')}
    for k, allowed in checks.items():
        if sc[k] not in allowed:
            raise SystemExit('%s 只能是 %s，收到 %r' % (k, '/'.join(allowed), sc[k]))
    if sc['recite'] == 'on' and not G.RECITE:
        raise SystemExit('这种棋还没有复述打分，recite 只能 off')
    sc['max_plies'] = max_plies
    if a.protocol == 'real':
        # 旧协议的 config 里没有这两项，保持逐字不变
        if sc['legal'] != 'none' or sc['session_view'] != 'full':
            raise SystemExit('real 协议下不给合法着法（legal=none）、每步都给完整局面（session_view=full）；要用请 --protocol legacy')
        sc['protocol'] = 'real'
        sc['retries'] = a.retries
        # 续接时去掉此前几轮的思考（llm-chat --drop-thinking），默认关；只有 Claude 棋手能开，在 build_cfg 里按棋手查
        sc['drop_thinking'] = sc['drop_thinking'] or 'off'
        if sc['drop_thinking'] not in ('on', 'off'):
            raise SystemExit('drop_thinking 只能是 on/off，收到 %r' % sc['drop_thinking'])
        if sc['drop_thinking'] == 'on' and sc['memory'] != 'session':
            raise SystemExit('drop_thinking=on 只对连续会话（memory=session）有意义，收到 memory=%s' % sc['memory'])
        # 着法之前写理由（用户 2026-09-29 定要写）；不给时一律「不修饰」plain（用户 2026-09-30 定，之前的默认 brief「简短」
        # 保留可选、两者不当变量）。detailed「详细」已弃用：opus 去掉此前思考 + 详细时频繁被安全防护拦下，
        # 用户定不改措辞绕，只为复现保留，显式给了照给的
        if sc['reason'] is None:
            sc['reason'] = 'plain'
        if sc['reason'] == 'on':
            raise SystemExit('reason 现在分 plain（不修饰）/ brief（简短）/ detailed（详细，已弃用）/ off，不再收 on；不给时 plain')
        if sc['reason'] not in memory.REASONS:
            raise SystemExit('reason 只能是 %s，收到 %r' % ('/'.join(memory.REASONS), sc['reason']))
    else:
        for k in ('reason', 'drop_thinking'):     # 旧协议的 config 里没有这两项，保持逐字不变
            if sc.pop(k) is not None:
                raise SystemExit('%s 只在 real 协议下可用' % k)
    return sc


def check_player(G, spec, protocol='legacy'):
    kind = runner.player_kind(spec)
    if kind == 'claude' and ':' in spec and spec.split(':', 1)[1]:
        return
    if kind in ('codex', 'deepseek') and protocol == 'real':
        return
    if kind == 'random' and spec == 'random':
        return
    if kind == 'engine' and ':' in spec:
        try:
            G.engine_spec(spec.split(':', 1)[1])    # 参数不对在这里报错
        except ValueError as e:
            raise SystemExit(str(e))
        return
    raise SystemExit('棋手写成 claude:<模型> / codex:<模型> / deepseek[:<模型>]（后两种只在 real 协议下）/ '
                     'engine:<引擎>[:参数] / random，收到 %r' % spec)


def commit():
    try:
        out = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True)
        dirty = subprocess.run(['git', '-C', str(ROOT), 'status', '--porcelain', '--', 'llmchess'],
                               capture_output=True, text=True).stdout.strip()
        return out.stdout.strip() + ('-dirty' if dirty else '')
    except Exception as e:                       # 只是记进 config
        return '? (%s)' % e


def default_retries(protocol):
    """一步里能重选几次（不含第一次）。real 下一手棋最多 3 次、第 3 次仍非法判负（用户 2026-09-29 定，本项目自定的赛制，
    不是任何正式规则）；legacy 保持改之前的 4 次，旧实验照旧复现。已开局的记录续跑按 config 里记的值，不受影响。"""
    return 2 if protocol == 'real' else 3


def build_cfg(a):
    G = game_module(a.game)
    if a.retries is None:
        a.retries = default_retries(a.protocol)
    players = {'w': a.red or a.white or 'claude:opus', 'b': a.black or 'claude:opus'}
    for s in 'wb':
        if players[s] == 'deepseek':
            players[s] = 'deepseek:' + chat.DEEPSEEK_DEFAULT
        check_player(G, players[s], a.protocol)
    sides = {'w': side_cfg(a, G, a.w, a.max_plies), 'b': side_cfg(a, G, a.b, a.max_plies)}
    for s in 'wb':
        kind = runner.player_kind(players[s])
        # 去掉此前思考只有 Claude 路支持（llm-chat：GPT 一给就报错，DeepSeek 本来就不回传思考）；引擎、随机不看这一项
        if sides[s].get('drop_thinking') == 'on' and kind in runner.MODEL_KINDS and kind != 'claude':
            raise SystemExit('%s（%s）不能开 drop_thinking：只有 Claude 棋手支持去掉此前思考；只给一方开用 --w / --b '
                             'drop_thinking=on' % (G.SIDES[s], players[s]))
    cfg = {'game': a.game, 'tag': a.tag, 'players': players, 'sides': sides, 'retries': a.retries,
           'max_plies': a.max_plies, 'seed': a.seed if a.seed is not None else random.randrange(10 ** 9),
           'forfeit': runner.FORFEIT_NOTE, 'timeout': a.timeout}
    cfg['system'] = {s: G.system_prompt(s, sides[s], memory.system_text(sides[s])) for s in 'wb'}
    models = [s for s in 'wb' if runner.player_kind(players[s]) in runner.MODEL_KINDS]
    if a.protocol == 'real':
        cfg['protocol'] = 'real'
        cfg['backend'] = 'llm-chat'
        cfg['models'] = {}
        for s in models:
            kind, name = players[s].split(':', 1)
            if kind == 'deepseek' and sides[s]['effort'] not in chat.DEEPSEEK_EFFORTS:
                raise SystemExit('DeepSeek 只有 %s 三档思考，收到 %r' % ('/'.join(chat.DEEPSEEK_EFFORTS), sides[s]['effort']))
            cfg['models'][s] = chat.model_id(kind, name)
        cfg['llm_chat'] = chat.script_info()
        cfg['commands'] = {s: chat.shown(cfg['models'][s], sides[s]['effort'], sides[s]['drop_thinking'] == 'on')
                           for s in models}
    else:
        cfg['commands'] = {s: claude_cli.shown(claude_cli.command(players[s].split(':', 1)[1], sides[s]['effort'], '-'))
                           for s in models}
    cfg['engines'] = {s: G.engine_spec(players[s].split(':', 1)[1])
                      for s in 'wb' if runner.player_kind(players[s]) == 'engine'}
    return G, cfg


def play_stoppable(ctx, a):
    """下一盘：按 --on-limit 设撞额度的行为，装停止信号处理（等额度时 Ctrl-C / SIGTERM 能马上停下写 pause）。"""
    claude_cli.LIMIT_MODE = a.on_limit
    restore = claude_cli.install_stop_handlers()
    try:
        return 0 if runner.play(ctx, a.stop_after, a.stop_file) else 3
    finally:
        restore()


def add_opening(a, G, cfg):
    """--opening random:N：生成开局写进 config（生成一次，续跑不重抽）。"""
    try:
        n = opening.parse_mode(a.opening)
    except ValueError as e:
        raise SystemExit(str(e))
    if not n:
        return
    if n >= a.max_plies:
        raise SystemExit('开局半回合数 %d 要小于 --max-plies %d' % (n, a.max_plies))
    seed = a.opening_seed if a.opening_seed is not None else random.randrange(10 ** 9)
    cfg['opening'] = opening.generate(G, a.game, n, seed)


def dry_run_position(G, cfg, tmp):
    """--dry-run：走完随机开局；轮到的若不是模型、另一方是模型，就让这一方（引擎 / 随机）真走一步，
    好打印模型方真正的第一步提示。记录写在临时目录里，用完就删。返回 (要打印提示的那一方, ctx)。"""
    ctx = runner.new_ctx(G, cfg, tmp)
    st = ctx['st']
    for mv in opening.moves_of(cfg):
        G.push(st, mv)
    side = G.turn(st)
    kind = runner.player_kind(cfg['players'][side])
    if kind not in runner.MODEL_KINDS and runner.player_kind(cfg['players'][runner.other(side)]) in runner.MODEL_KINDS \
            and G.ending(st) is None:
        if kind == 'engine':
            ctx['engines'][side] = runner.Engine(G.engine_spec(cfg['players'][side].split(':', 1)[1])).start()
        try:
            moves = G.legal(st)
            mv = runner.TURNS[kind](ctx, side, moves, G.banned(st, moves))[0]
        finally:
            for eng in ctx['engines'].values():
                eng.close()
        G.push(st, mv)
        side = runner.other(side)
    return side, ctx


def cmd_play(a):
    G, cfg = build_cfg(a)
    add_opening(a, G, cfg)
    if a.dry_run:
        for s in 'wb':
            print('== 系统提示（%s，%s）==\n%s\n' % (G.SIDES[s], cfg['players'][s], cfg['system'][s]))
        with tempfile.TemporaryDirectory() as tmp:
            side, ctx = dry_run_position(G, cfg, tmp)
        sc = cfg['sides'][side]
        what = '随机开局 %d 个半回合之后' % len(cfg['opening']['moves']) if cfg.get('opening') else '开局'
        print('== %s，%s第一步的用户提示（%s）==\n%s' % (what, G.SIDES[side], cfg['players'][side],
                                               G.render(ctx['st'], sc) + '\n\n' + memory.ask(sc)))
        return 0
    if not a.tag:
        raise SystemExit('要 --tag')
    run_dir = (pathlib.Path(a.out) if a.out else RUNS) / a.tag
    if (run_dir / 'game.jsonl').exists():
        raise SystemExit('%s 已有记录，换个 --tag 或用 resume' % run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    cfg['claude_version'] = claude_cli.version()
    cfg['commit'] = commit()
    cfg['argv'] = sys.argv
    cfg['claude_cwd'] = os.path.join(os.path.realpath(tempfile.gettempdir()), 'llmchess-cwd',
                                     '%s-%s' % (a.tag, uuid.uuid4().hex[:8]))
    ctx = runner.new_ctx(G, cfg, str(run_dir))
    runner.log(ctx, {'type': 'config', 'cfg': cfg})
    return play_stoppable(ctx, a)


def cmd_resume(a):
    run_dir = pathlib.Path(a.dir)
    cfg = records.read(run_dir / 'game.jsonl')[0]['cfg']
    G = game_module(cfg['game'])
    ctx = runner.load(G, str(run_dir))
    if ctx['end']:
        raise SystemExit('这盘已经结束：%s' % json.dumps(ctx['end'], ensure_ascii=False))
    rec = {'type': 'resume', 'ply': len(ctx['st']['moves']), 'commit': commit()}
    if a.timeout is not None:                    # 只管这次续跑；下次不给就又沿用 config 里的值
        ctx['cfg']['timeout'] = rec['timeout'] = a.timeout
    runner.log(ctx, rec)
    print('接着下 %s：已走 %d 个半回合' % (cfg['tag'], len(ctx['st']['moves'])))
    return play_stoppable(ctx, a)


def cmd_export(a):
    """已结束的盘按记录重新导出棋谱（带每步元信息），不调模型、不写记录。"""
    run_dir = pathlib.Path(a.dir)
    cfg = records.read(run_dir / 'game.jsonl')[0]['cfg']
    ctx = runner.load(game_module(cfg['game']), str(run_dir))
    if not ctx['end']:
        raise SystemExit('%s 还没下完（已走 %d 个半回合），下完再导出' % (run_dir, len(ctx['st']['moves'])))
    files = runner.write_exports(ctx)
    print('已重新导出 %s：%s' % (run_dir, '、'.join(sorted(files))))
    return 0


LIMIT_HELP = ('撞额度时：wait（默认）在程序里等到解除再接着下，每次等待的起止记 limit_wait；'
              'pause 是旧行为，写 pause 后退出码 3')


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python3 -m llmchess', description=__doc__.split('\n')[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('play', help='开一盘')
    p.add_argument('--game', required=True, choices=sorted(GAMES))
    p.add_argument('--tag', help='这盘的名字，记录放在 runs/<tag>/')
    p.add_argument('--out', help='记录的上级目录，默认仓库里的 runs/')
    p.add_argument('--red', help='中国象棋红方（同 --white）')
    p.add_argument('--white', help='国际象棋白方（同 --red）')
    p.add_argument('--black')
    p.add_argument('--protocol', choices=('real', 'legacy'), default='real',
                   help='real（默认）：模型就是真实棋手、走 llm-chat；legacy：改协议之前的提示和 claude -p 直调')
    p.add_argument('--effort', default='medium')
    p.add_argument('--memory', default=None, help='stateless / notes / session；默认 real 下 session、legacy 下 stateless')
    p.add_argument('--show', default=None, help='局面怎么呈现，默认：中国象棋 pieces；国际象棋 all（fen,ascii）；和 --view 二选一')
    p.add_argument('--view', default=None, help='自定义呈现组合（逗号分隔），和 --show 二选一')
    p.add_argument('--history', type=int, default=-1)
    p.add_argument('--legal', default='none')
    p.add_argument('--selfcheck', default='off')
    p.add_argument('--recite', default='off')
    p.add_argument('--notes-keep', dest='notes_keep', type=int, default=1)
    p.add_argument('--session-view', dest='session_view', default='full')
    p.add_argument('--reason', default=None, help='plain（默认）：着法之前用自己的话写出这步的理由；brief：同上但请它「简短」写；'
                   'off：只需给出着法；detailed：写详细理由，已弃用（易被安全防护拦下），只为复现保留')
    p.add_argument('--drop-thinking', dest='drop_thinking', default=None,
                   help='on：续接时不带此前几轮的思考（llm-chat --drop-thinking，只有 Claude 棋手）；默认 off')
    p.add_argument('--w', action='append', metavar='变量=值', help='只改先走一方（红 / 白），可重复')
    p.add_argument('--b', action='append', metavar='变量=值', help='只改黑方，可重复')
    p.add_argument('--retries', type=int, default=None,
                   help='一步里还能重选几次（一步最多 retries+1 次，用完判负）；默认 real 2（一步最多 3 次）、legacy 3')
    p.add_argument('--max-plies', dest='max_plies', type=int, default=200)
    p.add_argument('--seed', type=int, help='随机走子的种子，默认随机取一个并记进 config')
    p.add_argument('--opening', help='random:N：前 N 个半回合由程序替双方走（随机开局），默认不用')
    p.add_argument('--opening-seed', dest='opening_seed', type=int, help='随机开局的种子，默认随机取一个并记进 config')
    p.add_argument('--stop-after', dest='stop_after', type=int, help='本次最多走几个半回合就暂停（测续跑用）')
    p.add_argument('--timeout', type=int, default=claude_cli.TIMEOUT, help='单次 claude -p 调用的超时秒数，默认 3600')
    p.add_argument('--on-limit', dest='on_limit', choices=('wait', 'pause'), default='wait', help=LIMIT_HELP)
    p.add_argument('--dry-run', action='store_true', help='只打印系统提示和第一步提示，不调模型')
    stop_help = '每步之前看这个文件在不在，在就暂停（批量驱动用）'
    p.add_argument('--stop-file', dest='stop_file', help=stop_help)
    r = sub.add_parser('resume', help='按记录接着下')
    r.add_argument('dir')
    r.add_argument('--stop-after', dest='stop_after', type=int)
    r.add_argument('--stop-file', dest='stop_file', help=stop_help)
    r.add_argument('--on-limit', dest='on_limit', choices=('wait', 'pause'), default='wait', help=LIMIT_HELP)
    r.add_argument('--timeout', type=int, help='这次续跑改用的 claude -p 超时秒数（记进 resume 记录），默认沿用 config')
    e = sub.add_parser('export', help='已结束的盘按记录重新导出棋谱（record.txt / game.pgn，带每步元信息）')
    e.add_argument('dir')
    a = ap.parse_args(argv)
    return {'play': cmd_play, 'resume': cmd_resume, 'export': cmd_export}[a.cmd](a)
