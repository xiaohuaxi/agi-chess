"""离线单元测试：engine.py 的很薄的 UCI 收发（agi_chess/engine.py），用本机真引擎但把强度压到最低（nodes=1），
保证每个用例都很快。不判定"棋力"，只判定"收发协议和进程生命周期работает"。
"""
import os
import shutil
import stat
import tempfile
import unittest
from unittest import mock

from agi_chess import chess_ as C
from agi_chess import xiangqi as X
from agi_chess.engine import Engine, find_engine_binary, resolve_engine_cmd

FSF_MISSING = find_engine_binary('fairy-stockfish', 'FAIRY_STOCKFISH') is None
STOCKFISH_MISSING = find_engine_binary('stockfish', 'STOCKFISH') is None


class FindEngineBinary(unittest.TestCase):
    def test_env_var_and_fallback_dirs(self):
        with tempfile.TemporaryDirectory(prefix='agi-chess-eng-bin-') as tmp:
            fake_bin = os.path.join(tmp, 'my-stockfish')
            with open(fake_bin, 'w', encoding='utf-8') as f:
                f.write('#!/bin/sh\nexit 0\n')
            os.chmod(fake_bin, os.stat(fake_bin).st_mode | stat.S_IXUSR)

            with mock.patch.dict(os.environ, {'STOCKFISH': fake_bin}, clear=False):
                self.assertEqual(find_engine_binary('stockfish', 'STOCKFISH'), fake_bin)
                self.assertEqual(C.engine_spec('stockfish:nodes=1')['cmd'], [fake_bin])

            missing_bin = os.path.join(tmp, 'no-such-stockfish')
            with mock.patch.dict(os.environ, {'STOCKFISH': missing_bin}, clear=False):
                self.assertIsNone(find_engine_binary('stockfish', 'STOCKFISH'))
                self.assertEqual(resolve_engine_cmd('stockfish', 'STOCKFISH'), missing_bin)

            games_dir = os.path.join(tmp, 'usr-games')
            os.makedirs(games_dir)
            usr_games_sf = os.path.join(games_dir, 'stockfish')
            with open(usr_games_sf, 'w', encoding='utf-8') as f:
                f.write('#!/bin/sh\nexit 0\n')
            os.chmod(usr_games_sf, os.stat(usr_games_sf).st_mode | stat.S_IXUSR)
            with mock.patch.dict(os.environ, {'PATH': ''}, clear=False), \
                 mock.patch('agi_chess.engine.ENGINE_SEARCH_DIRS', (games_dir,)):
                os.environ.pop('STOCKFISH', None)
                self.assertEqual(find_engine_binary('stockfish', 'STOCKFISH'), usr_games_sf)


@unittest.skipIf(FSF_MISSING, '本机没有 fairy-stockfish')
class XiangqiEngine(unittest.TestCase):
    def test_start_best_close(self):
        spec = X.engine_spec('fsf:nodes=1')
        eng = Engine(spec, timeout=15).start()
        try:
            st = X.start()
            mv = eng.best(st['fens'][0], [], None)
            self.assertRegex(mv, r'^[a-i]\d+[a-i]\d+$')   # 引擎自己的坐标（1-based 横线）
        finally:
            eng.close()
        # close 之后进程句柄清空，close() 本身可重复调用不报错
        self.assertIsNone(eng.p)
        eng.close()

    def test_context_manager(self):
        spec = X.engine_spec('fsf:nodes=1')
        with Engine(spec, timeout=15) as eng:
            st = X.start()
            mv = eng.best(st['fens'][0], [], None)
            self.assertTrue(mv)

    def test_searchmoves_restricts_choice(self):
        spec = X.engine_spec('fsf:nodes=1')
        st = X.start()
        legal = X.legal(st)
        forced = [X.to_engine(legal[3])]
        with Engine(spec, timeout=15) as eng:
            mv = eng.best(st['fens'][0], [], forced)
        self.assertEqual(mv, forced[0])


@unittest.skipIf(STOCKFISH_MISSING, '本机没有 stockfish')
class ChessEngine(unittest.TestCase):
    def test_start_best_close(self):
        spec = C.engine_spec('stockfish:nodes=1')
        with Engine(spec, timeout=15) as eng:
            st = C.start()
            mv = eng.best(st['fens'][0], [], None)
            self.assertRegex(mv, r'^[a-h][1-8][a-h][1-8][qrbn]?$')


if __name__ == '__main__':
    unittest.main()
