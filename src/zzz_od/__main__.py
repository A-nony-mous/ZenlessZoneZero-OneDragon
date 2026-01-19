import sys
import os

# 将 src 目录添加到 sys.path，以便可以导入兄弟包 (one_dragon 等)
# 假设结构为: src/zzz_od/__main__.py
# 我们需要 src/
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(current_dir)
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from zzz_od.gui.app import main

if __name__ == "__main__":
    main()
