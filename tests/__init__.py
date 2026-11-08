# 离线测试绝不能调到真模型：整盘默认走 llm-chat（chat.SCRIPT 在导入时读这个变量），这里先指到一个不存在的路径，
# 哪个用例漏了替身就会直接失败，而不是悄悄花额度。用假脚本的用例（test_chat）自己替换 chat.SCRIPT。
import os

for _var in ('AGI_CHESS_LLM_CHAT', 'AGICHESS_LLM_CHAT', 'LLMCHESS_LLM_CHAT'):
    os.environ[_var] = '/nonexistent/agi-chess-tests-must-not-call-llm-chat.py'
