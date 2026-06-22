import os
import sys

# 把项目根目录加入 sys.path，使 `import src.xxx` 在 pytest 下可用
sys.path.insert(0, os.path.dirname(__file__))
