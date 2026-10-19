# 项目约定

- 项目包含代码时必须使用 Git，并在代码修改后推送到远程仓库。
- 较大修改需要创建独立功能分支；用户确认分支效果后才能合并到 `main`。
- 用户提供的远程仓库：`https://github.com/XayahTheRebel/F2A.git`。
- 本应用仅在本机处理图片，不引入外部素材上传服务。
- 修改转换逻辑后运行 `python -m unittest discover -s tests -p "test_*.py" -v`。
- 修改界面后运行语法检查，并用 `python tests/run_browser.py` 验证实际操作。
