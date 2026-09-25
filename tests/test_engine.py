"""离线单元测试：engine.py 的很薄的 UCI 收发（llmchess/engine.py），用本机真引擎但把强度压到最低（nodes=1），
保证每个用例都很快。不判定"棋力"，只判定"收发协议和进程生命周期работает"。
"""
import os
import shutil
import unittest

from llmchess import chess_ as C
from llmchess import xiangqi as X
from llmchess.engine import Engine

FSF_MISSING = shutil.which('fairy-stockfish') is None and not os.path.exists('/opt/homebrew/bin/fairy-stockfish')
STOCKFISH_MISSING = shutil.which('stockfish') is None and not os.path.exists('/opt/homebrew/bin/stockfish')


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
